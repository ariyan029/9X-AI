"""
core/state_machine.py — Deterministic Finite State Machine for 9X-AI.

Pure domain logic with zero I/O dependencies. The state machine receives
typed events (RoundResolution) and produces state transitions and optional
BetOrder directives. All decisions are deterministic and fully unit-testable.

State Transitions:
    IDLE_OBSERVING  →  ACTIVE_BETTING   (3 consecutive identical outcomes)
    ACTIVE_BETTING  →  IDLE_OBSERVING   (win: target outcome hit)
    ACTIVE_BETTING  →  ACTIVE_BETTING   (loss: ladder_index < 9)
    ACTIVE_BETTING  →  COOLDOWN         (loss at step 9: ladder exhausted)
    ACTIVE_BETTING  →  HALT             (insufficient balance)
    COOLDOWN        →  IDLE_OBSERVING   (1 clean round observed)
    ANY             →  HALT             (fatal error)
"""

from dataclasses import dataclass, field
from typing import Optional, List, Tuple

from core.models import (
    GameOutcome,
    EngineState,
    RoundResolution,
    BetOrder,
    CycleContext,
    StreakTracker,
)
from core.ladder import BetLadder, MAX_LADDER_INDEX


# Minimum consecutive identical outcomes required to trigger betting
STREAK_TRIGGER_THRESHOLD: int = 3


@dataclass
class TransitionResult:
    """
    The output of a state machine transition.
    
    Attributes:
        new_state: The state after the transition.
        bet_order: Optional bet order to execute (only in ACTIVE_BETTING).
        message: Human-readable description of the transition.
    """
    new_state: EngineState
    bet_order: Optional[BetOrder] = None
    message: str = ""


class DeterministicStateMachine:
    """
    Pure deterministic state engine for the 9X-AI betting bot.
    
    Evaluates incoming RoundResolution events and produces state transitions
    with optional BetOrder directives. Guarantees:
    - At most one bet per round (idempotency via round_id tracking).
    - Streak detection requires exactly N consecutive identical outcomes.
    - Ladder progression follows the fixed 10-step sequence.
    - Exhaustion at step 9 triggers cooldown, not further betting.
    """

    def __init__(self):
        self.state: EngineState = EngineState.IDLE_OBSERVING
        self.streak: StreakTracker = StreakTracker()
        self.cycle: Optional[CycleContext] = None
        self.last_processed_round_id: Optional[str] = None
        self.last_bet_round_id: Optional[str] = None
        self.cooldown_round_id: Optional[str] = None
        self.history: List[RoundResolution] = []

    def on_round_resolved(
        self, resolution: RoundResolution
    ) -> TransitionResult:
        """
        Process a completed round and produce a state transition.
        
        This is the single entry point for all state machine evaluation.
        
        Args:
            resolution: The immutable record of the round's result.
            
        Returns:
            TransitionResult containing the new state and optional bet order.
        """
        # Idempotency guard: reject duplicate or stale rounds
        is_stale = False
        if self.last_processed_round_id is not None:
            if resolution.round_id == self.last_processed_round_id:
                is_stale = True
            elif resolution.round_id.isdigit() and self.last_processed_round_id.isdigit():
                is_stale = int(resolution.round_id) <= int(self.last_processed_round_id)
            else:
                is_stale = resolution.round_id <= self.last_processed_round_id

        if is_stale:
            return TransitionResult(
                new_state=self.state,
                message=f"Duplicate or stale round {resolution.round_id} ignored.",
            )

        # Record this round
        self.last_processed_round_id = resolution.round_id
        self.history.append(resolution)

        # Dispatch to state-specific handler
        if self.state == EngineState.IDLE_OBSERVING:
            return self._handle_idle(resolution)
        elif self.state == EngineState.ACTIVE_BETTING:
            return self._handle_active_betting(resolution)
        elif self.state == EngineState.COOLDOWN:
            return self._handle_cooldown(resolution)
        elif self.state == EngineState.HALT:
            return TransitionResult(
                new_state=EngineState.HALT,
                message="Engine is HALTED. Manual reset required.",
            )
        else:
            return self._transition_to_halt(
                f"Unknown state: {self.state}"
            )

    def _handle_idle(self, resolution: RoundResolution) -> TransitionResult:
        """
        IDLE_OBSERVING state handler.
        
        Updates streak tracker. If streak reaches the trigger threshold,
        transitions to ACTIVE_BETTING with target = opposite of streak.
        """
        streak_length = self.streak.update(resolution.outcome)

        if streak_length >= STREAK_TRIGGER_THRESHOLD:
            # Trigger betting on the opposite outcome
            target = resolution.outcome.opposite
            self.cycle = CycleContext(
                target=target,
                ladder_index=0,
                streak_origin=resolution.outcome,
                cycle_start_round_id=resolution.round_id,
            )
            self.state = EngineState.ACTIVE_BETTING

            # Generate the first bet order for the NEXT round
            target_round = (
                str(int(resolution.round_id) + 1).zfill(len(resolution.round_id))
                if resolution.round_id.isdigit()
                else ""
            )
            bet_order = BetOrder(
                round_id=target_round,
                target=target,
                amount=BetLadder.get_stake(0),
                ladder_index=0,
            )

            return TransitionResult(
                new_state=EngineState.ACTIVE_BETTING,
                bet_order=bet_order,
                message=(
                    f"Streak of {streak_length} {resolution.outcome.value} detected. "
                    f"Entering ACTIVE_BETTING targeting {target.value} at ladder step 0 "
                    f"(stake: {BetLadder.get_stake(0)})."
                ),
            )

        return TransitionResult(
            new_state=EngineState.IDLE_OBSERVING,
            message=(
                f"Round {resolution.round_id}: {resolution.outcome.value} "
                f"(streak: {streak_length}/{STREAK_TRIGGER_THRESHOLD})."
            ),
        )

    def _handle_active_betting(
        self, resolution: RoundResolution
    ) -> TransitionResult:
        """
        ACTIVE_BETTING state handler.
        
        Evaluates whether the round result is a WIN or LOSS for the
        active cycle, and produces the appropriate transition.
        """
        if self.cycle is None:
            return self._transition_to_halt("ACTIVE_BETTING with no cycle context.")

        if resolution.outcome == self.cycle.target:
            # === WIN ===
            profit = BetLadder.get_net_profit_on_win(self.cycle.ladder_index)
            step = self.cycle.ladder_index
            self._reset_cycle()
            self.state = EngineState.IDLE_OBSERVING
            # Reset streak with the new outcome
            self.streak.update(resolution.outcome)

            return TransitionResult(
                new_state=EngineState.IDLE_OBSERVING,
                message=(
                    f"WIN at ladder step {step}! "
                    f"Net profit: {profit:+d} units. "
                    f"Resetting to IDLE_OBSERVING."
                ),
            )
        else:
            # === LOSS ===
            current_step = self.cycle.ladder_index

            if current_step >= MAX_LADDER_INDEX:
                # Hard Cycle Abort: final loss at step 9 (ladder exhausted)
                total_loss = BetLadder.get_cumulative_risk(MAX_LADDER_INDEX)
                self.cooldown_round_id = resolution.round_id
                self._reset_cycle()
                self.state = EngineState.COOLDOWN
                # Reset streak with the new outcome
                self.streak.update(resolution.outcome)

                return TransitionResult(
                    new_state=EngineState.COOLDOWN,
                    message=(
                        f"HARD CYCLE ABORT: Lost at step {current_step} (final step). "
                        f"Total cycle loss: {total_loss} units. "
                        f"Entering COOLDOWN for 1 round."
                    ),
                )
            else:
                # Increment ladder, maintain target
                self.cycle.ladder_index += 1
                next_step = self.cycle.ladder_index
                next_stake = BetLadder.get_stake(next_step)

                target_round = (
                    str(int(resolution.round_id) + 1).zfill(len(resolution.round_id))
                    if resolution.round_id.isdigit()
                    else ""
                )
                bet_order = BetOrder(
                    round_id=target_round,
                    target=self.cycle.target,
                    amount=next_stake,
                    ladder_index=next_step,
                )

                return TransitionResult(
                    new_state=EngineState.ACTIVE_BETTING,
                    bet_order=bet_order,
                    message=(
                        f"LOSS at step {current_step}. "
                        f"Advancing to step {next_step} "
                        f"(stake: {next_stake}). "
                        f"Target remains: {self.cycle.target.value}."
                    ),
                )

    def _handle_cooldown(
        self, resolution: RoundResolution
    ) -> TransitionResult:
        """
        COOLDOWN state handler.
        
        Observes one clean round, then returns to IDLE_OBSERVING
        with a fresh streak counter based on the observed outcome.
        """
        self.state = EngineState.IDLE_OBSERVING
        self.cooldown_round_id = None
        # Seed the streak tracker with this round's outcome
        self.streak = StreakTracker()
        self.streak.update(resolution.outcome)

        return TransitionResult(
            new_state=EngineState.IDLE_OBSERVING,
            message=(
                f"COOLDOWN complete. Observed round {resolution.round_id}. "
                f"Resuming IDLE_OBSERVING."
            ),
        )

    def _transition_to_halt(self, reason: str) -> TransitionResult:
        """Transition to HALT state with a diagnostic message."""
        self.state = EngineState.HALT
        return TransitionResult(
            new_state=EngineState.HALT,
            message=f"HALT triggered: {reason}",
        )

    def _reset_cycle(self):
        """Clear the active betting cycle context."""
        self.cycle = None

    def trigger_halt(self, reason: str) -> TransitionResult:
        """
        External trigger to force the engine into HALT state.
        
        Used by circuit breakers (balance watchdog, desync detector).
        
        Args:
            reason: Human-readable reason for the halt.
        """
        return self._transition_to_halt(reason)

    def reset(self):
        """
        Full engine reset. Returns to IDLE_OBSERVING with clean state.
        
        Used for manual operator recovery after HALT, or test setup.
        """
        self.state = EngineState.IDLE_OBSERVING
        self.streak = StreakTracker()
        self.cycle = None
        self.last_processed_round_id = None
        self.last_bet_round_id = None
        self.cooldown_round_id = None
        self.history.clear()
