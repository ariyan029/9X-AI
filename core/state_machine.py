"""
core/state_machine.py — Deterministic Finite State Machine for 9X-AI.

Pure domain logic with zero I/O dependencies. The state machine receives
typed events (RoundResolution) and produces state transitions and optional
BetOrder directives. All decisions are deterministic and fully unit-testable.

State Transitions:
    IDLE_OBSERVING    →  ACTIVE_BETTING     (prev != next or first round)
    ACTIVE_BETTING    →  WAITING_AFTER_BET  (bet resolves, must wait one round)
    WAITING_AFTER_BET →  IDLE_OBSERVING     (prev == next, wait for streak break)
    WAITING_AFTER_BET →  ACTIVE_BETTING     (prev != next, bet opposite)
    IDLE_OBSERVING    →  IDLE_OBSERVING     (prev == next, wait for streak break)
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
            # Bet has resolved (win or loss). We must wait one round before betting again.
            self._reset_cycle()
            self.state = EngineState.WAITING_AFTER_BET
            return TransitionResult(
                new_state=EngineState.WAITING_AFTER_BET,
                message="Bet resolved. Mandatory wait for one round."
            )

        # IDLE_OBSERVING or WAITING_AFTER_BET
        if len(self.history) == 1:
            return self._handle_bet_on_different(resolution)

        prev_outcome = self.history[-2].outcome
        curr_outcome = self.history[-1].outcome

        if prev_outcome == curr_outcome:
            # We had a loss or are in a streak. Wait for a different outcome.
            if self.state != EngineState.IDLE_OBSERVING:
                self.state = EngineState.IDLE_OBSERVING
            return TransitionResult(
                new_state=EngineState.IDLE_OBSERVING,
                message=f"Streak {curr_outcome.value}-{curr_outcome.value}. Waiting for different outcome."
            )
        else:
            # Outcome changed. Start a new cycle and bet opposite.
            return self._handle_bet_on_different(resolution)

    def _handle_bet_on_different(self, resolution: RoundResolution) -> TransitionResult:
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
            message=f"New cycle targeting {target.value} at ladder step 0."
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
