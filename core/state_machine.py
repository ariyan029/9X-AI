"""
core/state_machine.py — Deterministic Finite State Machine for 9X-AI.

Pure domain logic with zero I/O dependencies. The state machine receives
typed events (RoundResolution) and produces state transitions and optional
BetOrder directives. All decisions are deterministic and fully unit-testable.

State Transitions:
    IDLE_OBSERVING    →  ACTIVE_BETTING     (streak threshold reached)
    ACTIVE_BETTING    →  COOLDOWN           (bet won)
    ACTIVE_BETTING    →  ACTIVE_BETTING     (bet lost, escalate ladder)
    ACTIVE_BETTING    →  HALT               (bet lost, ladder exhausted)
    COOLDOWN          →  IDLE_OBSERVING     (wait one round)
    ANY               →  HALT               (fatal error)
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
STREAK_TRIGGER_THRESHOLD: int = 2


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
    - Ladder progression follows the fixed 6-step sequence.
    - Exhaustion at final step returns to IDLE_OBSERVING.
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

        if self.state == EngineState.HALT:
            return TransitionResult(
                new_state=EngineState.HALT,
                message="Engine is HALTED. Manual reset required.",
            )

        # Record this round
        self.last_processed_round_id = resolution.round_id
        self.history.append(resolution)
        self.streak.update(resolution.outcome)

        if self.state == EngineState.ACTIVE_BETTING:
            if self.cycle is None:
                self.state = EngineState.HALT
                return self._transition_to_halt("ACTIVE_BETTING but no cycle context.")

            if resolution.outcome == self.cycle.target:
                # Win
                self._reset_cycle()
                self.streak.reset()
                self.streak.update(resolution.outcome)
                self.state = EngineState.IDLE_OBSERVING
                return TransitionResult(
                    new_state=EngineState.IDLE_OBSERVING,
                    message="Bet won. Resetting streak and returning to IDLE_OBSERVING."
                )
            else:
                # Loss
                if self.cycle.is_exhausted:
                    # Ladder exhausted
                    self._reset_cycle()
                    self.streak.reset()
                    self.streak.update(resolution.outcome)
                    self.state = EngineState.IDLE_OBSERVING
                    return TransitionResult(
                        new_state=EngineState.IDLE_OBSERVING,
                        message="Ladder exhausted. Resetting streak and returning to IDLE_OBSERVING."
                    )
                else:
                    self.cycle.ladder_index += 1
                    target_round = (
                        str(int(resolution.round_id) + 1).zfill(len(resolution.round_id))
                        if resolution.round_id.isdigit()
                        else ""
                    )
                    bet_order = BetOrder(
                        round_id=target_round,
                        target=self.cycle.target,
                        amount=BetLadder.get_stake(self.cycle.ladder_index),
                        ladder_index=self.cycle.ladder_index,
                    )
                    return TransitionResult(
                        new_state=EngineState.ACTIVE_BETTING,
                        bet_order=bet_order,
                        message=f"Bet lost. Escalating to ladder step {self.cycle.ladder_index}."
                    )

        # IDLE_OBSERVING
        if self.streak.count >= STREAK_TRIGGER_THRESHOLD:
            # Trigger!
            target = resolution.outcome.opposite
            self.cycle = CycleContext(
                target=target,
                ladder_index=0,
                streak_origin=resolution.outcome,
                cycle_start_round_id=resolution.round_id,
            )
            self.state = EngineState.ACTIVE_BETTING
            
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
                message=f"Streak of {self.streak.count} {resolution.outcome.value} detected. Targeting {target.value} at step 0."
            )
        else:
            return TransitionResult(
                new_state=EngineState.IDLE_OBSERVING,
                message=f"Observing. Current streak: {self.streak.count} {resolution.outcome.value}."
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
        """
        return self._transition_to_halt(reason)

    def reset(self):
        """
        Full engine reset. Returns to IDLE_OBSERVING with clean state.
        """
        self.state = EngineState.IDLE_OBSERVING
        self.streak.reset()
        self.cycle = None
        self.last_processed_round_id = None
        self.last_bet_round_id = None
        self.cooldown_round_id = None
        self.history.clear()
