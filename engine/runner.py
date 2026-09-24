"""
engine/runner.py — Asynchronous orchestration loop for 9X-AI.

Links the Observer, DeterministicStateMachine, and ActionExecutor
into a continuous 30-second cycle event loop. Manages the full
round lifecycle: Ingest → Evaluate → Gatekeep → Execute → Confirm.
"""

import asyncio
from typing import Optional

from loguru import logger

from core.models import GameOutcome, EngineState, RoundResolution, BetOrder
from core.state_machine import DeterministicStateMachine
from core.ladder import BetLadder
from browser.observer import DomObserver, ObserverSnapshot
from browser.executor import ActionExecutor, TimingGatekeeper
from config.settings import Settings
from config.selectors import AppSelectors
from utils.circuit_breaker import (
    BalanceCircuitBreaker,
    DesyncCircuitBreaker,
    EmergencyKillSwitch,
)
from utils.logger import log_round_event


class OrchestratorRunner:
    """
    Main async event loop that ties all subsystems together.
    
    Continuously polls the DOM observer, feeds events to the
    state machine, and dispatches bet orders through the executor
    when timing and safety conditions are met.
    """

    def __init__(
        self,
        settings: Settings,
        selectors: AppSelectors,
        dry_run: bool = False,
    ):
        self.settings = settings
        self.selectors = selectors
        self.dry_run = dry_run

        # Subsystems
        self.state_machine = DeterministicStateMachine()
        self.observer = DomObserver(selectors)
        self.executor = ActionExecutor(selectors, settings)
        self.balance_breaker = BalanceCircuitBreaker(settings.STOP_LOSS_BALANCE)
        self.desync_breaker = DesyncCircuitBreaker(
            max_retries=settings.MAX_DESYNC_RETRIES
        )
        self.kill_switch = EmergencyKillSwitch()

        # Configure timing window from settings
        TimingGatekeeper.configure(
            settings.MIN_TIMING_WINDOW_SEC,
            settings.MAX_TIMING_WINDOW_SEC,
        )

        # Pending bet order from state machine
        self._pending_order: Optional[BetOrder] = None
        self._last_snapshot_round_id: Optional[str] = None
        self._last_bet_round_id: Optional[str] = None

    async def run(self, page):
        """
        Main orchestration loop.
        
        Runs continuously until HALT, kill switch, or SIGINT.
        
        Args:
            page: Playwright page instance connected to the target app.
        """
        logger.info(
            f"Orchestrator started. Mode: {'DRY-RUN' if self.dry_run else 'LIVE'}. "
            f"Timing window: [{TimingGatekeeper.MIN_SECONDS}s, {TimingGatekeeper.MAX_SECONDS}s]."
        )

        # Attach zero-latency network interceptor to capture API round outcomes
        try:
            await self.observer.attach_network(page)
        except Exception as e:
            logger.debug(f"Could not attach network interceptor: {e}")

        while not self.kill_switch.is_triggered:
            try:
                # Check if browser window was closed by user
                is_closed = False
                try:
                    res = getattr(page, "is_closed", None)
                    if callable(res):
                        val = res()
                        if asyncio.iscoroutine(val):
                            val.close()
                        else:
                            is_closed = bool(val)
                except Exception:
                    pass

                if is_closed:
                    logger.info("Browser window was closed. Exiting orchestrator cleanly...")
                    break

                # Check for HALT state
                if self.state_machine.state == EngineState.HALT:
                    logger.critical("Engine is in HALT state. Stopping loop.")
                    break

                # Step 1: Take DOM snapshot
                snapshot = await self.observer.take_snapshot(page)

                # Step 2: Check for desync
                if snapshot.round_id is None and snapshot.countdown_seconds is None:
                    self.desync_breaker.record_error("No round ID or countdown found")
                    if self.desync_breaker.is_tripped():
                        await self.desync_breaker.capture_diagnostics(page)
                        self.state_machine.trigger_halt(
                            f"DOM desync: {self.desync_breaker.error_count} consecutive failures"
                        )
                        break
                else:
                    self.desync_breaker.record_success()

                # Step 3: Process new round resolutions from history
                await self._process_history(snapshot)

                # Step 4: Execute pending bet if conditions are met
                if self._pending_order and snapshot.countdown_seconds is not None:
                    await self._try_execute_bet(page, snapshot)

                # Step 5: Wait before next poll
                await asyncio.sleep(self.settings.poll_interval_seconds)

            except asyncio.CancelledError:
                logger.info("Orchestrator loop cancelled.")
                break
            except Exception as e:
                logger.error(f"Orchestrator error: {e}")
                self.desync_breaker.record_error(str(e))
                if self.desync_breaker.is_tripped():
                    self.state_machine.trigger_halt(f"Unrecoverable error: {e}")
                    break
                await asyncio.sleep(1.0)

        logger.info("Orchestrator loop ended.")

    async def _process_history(self, snapshot: ObserverSnapshot):
        """
        Process new round resolutions from the observed history.
        
        Finds rounds in the history that haven't been processed yet
        and feeds them to the state machine.
        """
        if not snapshot.history:
            return

        for resolution in reversed(snapshot.history):
            if self.observer.is_new_round(resolution.round_id):
                # Feed to state machine
                result = self.state_machine.on_round_resolved(resolution)
                self.observer.mark_processed(resolution.round_id)

                # Log the transition
                log_round_event(
                    round_id=resolution.round_id,
                    state=result.new_state.value,
                    target=(
                        self.state_machine.cycle.target.value
                        if self.state_machine.cycle
                        else ""
                    ),
                    ladder_index=(
                        self.state_machine.cycle.ladder_index
                        if self.state_machine.cycle
                        else -1
                    ),
                    outcome=resolution.outcome.value,
                    message=result.message,
                )

                # Always synchronize pending bet order with the latest state machine result
                if result.bet_order:
                    # If round_id was not populated, infer from resolution
                    if not result.bet_order.round_id and resolution.round_id and resolution.round_id.isdigit():
                        inferred_round = str(int(resolution.round_id) + 1).zfill(len(resolution.round_id))
                        self._pending_order = BetOrder(
                            round_id=inferred_round,
                            target=result.bet_order.target,
                            amount=result.bet_order.amount,
                            ladder_index=result.bet_order.ladder_index,
                        )
                    else:
                        self._pending_order = result.bet_order

                    target_info = (
                        f" targeting round {self._pending_order.round_id}"
                        if self._pending_order.round_id
                        else ""
                    )
                    logger.info(
                        f"Pending bet: {self._pending_order.target.value} "
                        f"x{self._pending_order.amount} at ladder step "
                        f"{self._pending_order.ladder_index}{target_info}"
                    )
                else:
                    self._pending_order = None

    async def _try_execute_bet(self, page, snapshot: ObserverSnapshot):
        """
        Attempt to execute a pending bet order if all conditions are met.
        
        Conditions:
        1. Target round alignment (do not bet on previous round or discard before target begins)
        2. Historical settlement check (do not bet on already completed round)
        3. Idempotency (prevent duplicate bet on same round)
        4. Timing window is valid (10s ≤ T ≤ 25s)
        5. History desync guard (await settlement of round N-1 before betting on round N)
        6. Balance is sufficient (or warning logged in dry-run)
        7. Execute bet order
        """
        if not self._pending_order:
            return

        order = self._pending_order
        countdown = snapshot.countdown_seconds
        active_round_id = snapshot.round_id

        # 1. Target round alignment:
        # If the order targets a specific round ID, verify whether the active round has reached it.
        # Often a round resolves in history at T=0s or 1s while the DOM header still displays
        # the previous round ID. We must NOT bet on the previous round or discard the order
        # for timing lockout before the target round has even begun!
        if order.round_id:
            if active_round_id and active_round_id.isdigit() and order.round_id.isdigit():
                active_num = int(active_round_id)
                target_num = int(order.round_id)
                if active_num < target_num:
                    logger.debug(
                        f"Target round {order.round_id} has not started yet "
                        f"(active: {active_round_id}, T={countdown}s). Awaiting next round."
                    )
                    return
                elif active_num > target_num:
                    logger.warning(
                        f"Target round {order.round_id} has already passed (active: {active_round_id}). "
                        "Discarding stale pending order."
                    )
                    self._pending_order = None
                    return
            elif active_round_id and active_round_id != order.round_id:
                logger.debug(
                    f"Awaiting target round {order.round_id} (active: {active_round_id})."
                )
                return

        # 2. Historical settlement check:
        # If the active round is already present in the history list (e.g. lag == 0),
        # that round is already finished. Do NOT place a bet or lockout on a finished round.
        if (
            active_round_id
            and snapshot.history
            and snapshot.history[0].round_id == active_round_id
        ):
            logger.debug(
                f"Active round {active_round_id} is already settled in history. Awaiting transition to next round."
            )
            return

        # 3. Idempotency guard: prevent double-betting on the same round
        if active_round_id and self._last_bet_round_id == active_round_id:
            logger.debug(
                f"Bet already placed on round {active_round_id}. Suppressing duplicate."
            )
            self._pending_order = None
            return

        # 4. Check timing window (10s <= T <= 25s)
        if not TimingGatekeeper.is_within_window(countdown):
            if countdown is not None and countdown < TimingGatekeeper.MIN_SECONDS:
                logger.warning(
                    f"Timing lockout: T={countdown}s < {TimingGatekeeper.MIN_SECONDS}s. "
                    f"Missed betting window for round {active_round_id or 'active'}. "
                    "Discarding stale pending order."
                )
                self._pending_order = None
            return

        # 5. History desync guard: ensure we are not betting on a cycle with missing outcome data
        if (
            active_round_id
            and active_round_id.isdigit()
            and snapshot.history
            and snapshot.history[0].round_id.isdigit()
        ):
            lag = int(active_round_id) - int(snapshot.history[0].round_id)
            if 2 <= lag <= 10:
                logger.warning(
                    f"History desync guard: Active round is {active_round_id}, "
                    f"but newest history is {snapshot.history[0].round_id} (lag={lag}). "
                    f"Awaiting settlement of round {int(active_round_id) - 1} before betting."
                )
                if page is not None:
                    await self.observer.trigger_history_refresh(page)
                return

        # 6. Check balance
        balance = await self.executor.get_wallet_balance(page)
        if balance is not None:
            if not self.balance_breaker.can_afford(balance, self._pending_order.amount):
                if self.dry_run:
                    logger.warning(
                        f"[DRY-RUN] Low balance: {balance:.2f} < {self._pending_order.amount}. "
                        "Continuing dry-run simulation without HALT."
                    )
                else:
                    self.state_machine.trigger_halt(
                        f"Insufficient balance: {balance:.2f} < {self._pending_order.amount}"
                    )
                    self._pending_order = None
                    return

        # 7. Execute or simulate
        order = self._pending_order
        self._pending_order = None
        if active_round_id:
            self._last_bet_round_id = active_round_id

        if self.dry_run:
            logger.info(
                f"[DRY-RUN] Would place bet: {order.target.value} "
                f"x{order.amount} (ladder step {order.ladder_index}) on round {active_round_id or 'unknown'} (T={countdown}s)"
            )
            return

        # Live execution
        try:
            logger.info(
                f"Executing bet: {order.target.value} x{order.amount} "
                f"(ladder step {order.ladder_index}, round {active_round_id}, T={countdown}s)"
            )
            confirmed = await self.executor.execute_bet_order(page, order)
            if confirmed:
                logger.success(
                    f"Bet CONFIRMED: {order.target.value} x{order.amount} for round {active_round_id}"
                )
            else:
                logger.warning(
                    f"Bet confirmation UNCERTAIN: {order.target.value} x{order.amount} for round {active_round_id}"
                )
        except Exception as e:
            logger.error(f"Bet execution FAILED: {e}")
