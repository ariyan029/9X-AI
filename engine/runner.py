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
from utils.data_tracker import BettingDataTracker


class OrchestratorRunner:
    """
    Main async event loop that ties all subsystems together.
    
    Continuously polls the DOM observer, feeds events to the
    state machine, and dispatches bet orders through the executor
    when timing and safety conditions are met.
    
    Includes network interruption resilience: if WiFi drops or the
    connection is temporarily lost, the engine enters a recovery mode
    with exponential backoff instead of immediately HALT-ing.
    """

    # Network recovery constants
    _RECOVERY_BACKOFF_BASE: float = 2.0      # Initial backoff seconds
    _RECOVERY_BACKOFF_MAX: float = 30.0      # Maximum backoff seconds
    _RECOVERY_MAX_ATTEMPTS: int = 120        # ~10+ minutes of retries before HALT
    _RECOVERY_PAGE_RELOAD_AFTER: int = 10    # Reload page after this many failures

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
        self.data_tracker = BettingDataTracker()

        # Configure timing window from settings
        TimingGatekeeper.configure(
            settings.MIN_TIMING_WINDOW_SEC,
            settings.MAX_TIMING_WINDOW_SEC,
        )

        # Pending bet order from state machine
        self._pending_order: Optional[BetOrder] = None
        self._last_snapshot_round_id: Optional[str] = None
        self._last_bet_round_id: Optional[str] = None

        # Network and DOM recovery state
        self._consecutive_dom_misses: int = 0
        self._consecutive_network_failures: int = 0
        self._in_recovery_mode: bool = False

    async def _dismiss_popups_if_any(self, page) -> bool:
        """Dismiss any announcement, notification, or modal dialogs that might block the UI."""
        if not page:
            return False
        dialog_selectors = (
            "button.announcement-dialog__button, "
            ".reward-amount-dialog__button, "
            ".dialog-queue-host button, "
            ".dialog-queue-host .van-icon-cross, "
            ".van-dialog__confirm, "
            "[class*='dialog'] button.close, "
            "[class*='dialog'] [class*='close']"
        )
        try:
            btn = await page.query_selector(dialog_selectors)
            if btn:
                await btn.click(force=True)
                logger.info("Dismissed an overlay dialog.")
                return True
        except Exception:
            pass
        return False

    async def _attempt_network_recovery(self, page) -> bool:
        """
        Attempt to recover from a connection or page disruption.
        
        Checks if the live API is reachable. If reachable, recovers
        missing round history via API and restores DOM responsiveness
        (reloading page if necessary).
        If API is also unreachable, enters network recovery mode with
        exponential backoff.
        
        Returns:
            True if API or DOM is functional, False if offline.
        """
        # Strategy 1: Try direct API fetch (bypasses browser DOM)
        api_results = None
        try:
            api_results = await self.observer.fetch_live_history()
        except Exception as e:
            logger.debug(f"API recovery check failed: {e}")

        if api_results:
            # Internet is active! Feed results into network interceptor
            for r in api_results:
                self.observer.network_interceptor.record_resolution(r)

            if self._in_recovery_mode:
                logger.success("✅ Network connectivity verified via API! Resuming tracking.")
                self._in_recovery_mode = False
            self._consecutive_network_failures = 0

            # If DOM has been continuously missing for >= 10 attempts, reload page to restore UI
            if self._consecutive_dom_misses >= 10:
                logger.info(
                    f"DOM unresponsive ({self._consecutive_dom_misses} misses). Reloading page to restore UI..."
                )
                try:
                    is_closed = getattr(page, "is_closed", lambda: False)()
                    if not is_closed:
                        await page.reload(wait_until="domcontentloaded", timeout=15000)
                        await asyncio.sleep(2.0)
                        try:
                            await self.observer.attach_network(page)
                        except Exception:
                            pass
                        await self._dismiss_popups_if_any(page)
                        logger.info("Page reloaded. Verifying DOM response...")
                except Exception as e:
                    logger.debug(f"Page reload failed: {e}")
            return True

        # Strategy 2: If API is unreachable, this is a TRUE network outage
        self._consecutive_network_failures += 1
        failures = self._consecutive_network_failures

        # Calculate exponential backoff: 2s, 4s, 8s, 16s, 30s, 30s, ...
        backoff = min(
            self._RECOVERY_BACKOFF_BASE * (2 ** min(failures - 1, 4)),
            self._RECOVERY_BACKOFF_MAX,
        )

        if not self._in_recovery_mode:
            self._in_recovery_mode = True
            logger.warning(
                "🌐 Network interruption detected! Entering recovery mode. "
                "The engine will keep retrying until connectivity is restored."
            )

        logger.info(
            f"🔄 Recovery attempt #{failures}/{self._RECOVERY_MAX_ATTEMPTS} "
            f"— waiting {backoff:.0f}s before retry..."
        )

        await asyncio.sleep(backoff)
        return False

    async def run(self, page):
        """
        Main orchestration loop.
        
        Runs continuously until HALT, kill switch, or SIGINT.
        Includes network interruption resilience with automatic recovery.
        
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

                # Step 2: Check for desync / network interruption
                if snapshot.round_id is None and snapshot.countdown_seconds is None:
                    self._consecutive_dom_misses += 1

                    # Transient misses (< 3 ticks, ~0.75s) are normal during round transitions / animations
                    if self._consecutive_dom_misses < 3:
                        if snapshot.history:
                            await self._process_history(snapshot)
                        await asyncio.sleep(self.settings.poll_interval_seconds)
                        continue

                    # Dismiss any overlay dialogs if present
                    if page:
                        await self._dismiss_popups_if_any(page)

                    # Check network/DOM recovery
                    if self._consecutive_network_failures < self._RECOVERY_MAX_ATTEMPTS:
                        recovered = await self._attempt_network_recovery(page)
                        if recovered:
                            # Recovery succeeded — take a fresh snapshot and continue
                            snapshot = await self.observer.take_snapshot(page)
                            if snapshot.round_id is not None or snapshot.countdown_seconds is not None:
                                self._consecutive_dom_misses = 0
                                self.desync_breaker.record_success()
                            else:
                                if snapshot.history:
                                    await self._process_history(snapshot)
                                await asyncio.sleep(self.settings.poll_interval_seconds)
                                continue
                        else:
                            # Still offline — don't count towards desync HALT yet
                            continue
                    else:
                        # Exhausted all recovery attempts
                        logger.critical(
                            f"🚫 Network recovery failed after {self._RECOVERY_MAX_ATTEMPTS} attempts "
                            f"(~{self._RECOVERY_MAX_ATTEMPTS * self._RECOVERY_BACKOFF_MAX / 60:.0f} min). "
                            "Triggering HALT."
                        )
                        self.state_machine.trigger_halt(
                            f"Sustained network failure: {self._RECOVERY_MAX_ATTEMPTS} "
                            "consecutive recovery attempts exhausted"
                        )
                        break
                else:
                    # Successful DOM read — reset all recovery state
                    self._consecutive_dom_misses = 0
                    if self._in_recovery_mode:
                        logger.success(
                            "✅ DOM connection fully restored! Resuming normal operation."
                        )
                        self._in_recovery_mode = False
                    self._consecutive_network_failures = 0
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
                err_str = str(e).lower()
                # Network-related errors should trigger recovery, not HALT
                is_network_error = any(keyword in err_str for keyword in [
                    "net::", "err_internet", "err_network", "timeout",
                    "connection", "unreachable", "dns", "socket",
                    "target closed", "session closed", "page closed",
                    "execution context", "navigating",
                ])
                if is_network_error and self._consecutive_network_failures < self._RECOVERY_MAX_ATTEMPTS:
                    logger.warning(f"Network-related error caught: {e}")
                    await self._attempt_network_recovery(page)
                else:
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
                # Feed to data tracker
                self.data_tracker.process_outcome(resolution.outcome)

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
                    # Day-boundary rollover: re-target bet to the current active round
                    # instead of discarding, so the ladder recovery cycle continues.
                    logger.warning(
                        f"Target round {order.round_id} has already passed (active: {active_round_id}). "
                        "Re-targeting pending bet to current active round."
                    )
                    self._pending_order = BetOrder(
                        round_id=active_round_id,
                        target=order.target,
                        amount=order.amount,
                        ladder_index=order.ladder_index,
                    )
                    order = self._pending_order
                    # Continue execution with the re-targeted order
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
            # Pre-check: verify browser is still alive before executing
            try:
                is_closed = getattr(page, 'is_closed', lambda: False)()
                if is_closed:
                    logger.warning(
                        f"Browser closed before bet execution. "
                        f"Re-queuing order for {order.target.value} x{order.amount}."
                    )
                    self._pending_order = order
                    return
            except Exception:
                pass

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
        except TimeoutError as e:
            # Check if failure was due to browser closure
            try:
                is_closed = getattr(page, 'is_closed', lambda: False)()
            except Exception:
                is_closed = True
            if is_closed:
                logger.warning(
                    f"Bet execution interrupted — browser was closed. "
                    f"Order: {order.target.value} x{order.amount} (ladder step {order.ladder_index})"
                )
            else:
                logger.error(f"Bet execution FAILED: {e}")
                # Re-queue the order so the ladder cycle can retry on the next round.
                # Without this, a popup failure would silently kill the entire cycle.
                self._pending_order = order
                self._last_bet_round_id = None  # Allow retry on next round
                logger.info(
                    f"Re-queued bet order: {order.target.value} x{order.amount} "
                    f"(ladder step {order.ladder_index}) for retry on next round."
                )
        except Exception as e:
            logger.error(f"Bet execution FAILED: {e}")
