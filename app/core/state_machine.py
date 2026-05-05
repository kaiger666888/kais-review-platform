"""4-state checkpoint state machine with optimistic locking for review lifecycle."""

from sqlalchemy import update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import append_audit
from app.models.schema import Review
from app.models.schemas import ReviewState, Disposition


# --- Exceptions ---


class StateMachineError(Exception):
    """Base exception for state machine errors."""
    pass


class InvalidTransitionError(StateMachineError):
    """Raised when a state transition is not allowed."""
    pass


class StateConflictError(StateMachineError):
    """Raised when optimistic locking detects a concurrent modification."""
    pass


class TerminalStateError(StateMachineError):
    """Raised when attempting to transition from a terminal state."""
    pass


# --- Transition Map ---

VALID_TRANSITIONS: dict[ReviewState, set[ReviewState]] = {
    ReviewState.PENDING: {ReviewState.POLICY_EVAL},
    ReviewState.POLICY_EVAL: {ReviewState.APPROVING, ReviewState.COMPLETE},
    ReviewState.APPROVING: {ReviewState.COMPLETE, ReviewState.PENDING, ReviewState.POLICY_EVAL},
    ReviewState.COMPLETE: set(),  # Terminal state
}


# --- Helper Functions ---


def validate_transition(from_state: ReviewState, to_state: ReviewState) -> bool:
    """Check if a transition from from_state to to_state is valid."""
    return to_state in VALID_TRANSITIONS.get(from_state, set())


def get_allowed_transitions(state: ReviewState) -> set[ReviewState]:
    """Return the set of states that can be reached from the given state."""
    return VALID_TRANSITIONS.get(state, set()).copy()


def is_terminal(state: ReviewState) -> bool:
    """Return True if the given state is terminal (COMPLETE)."""
    return state == ReviewState.COMPLETE


# --- Core Transition Function ---


async def transition_state(
    session: AsyncSession,
    review_id: int,
    from_state: ReviewState,
    to_state: ReviewState,
    expected_version: int,
    actor: str,
    action: str | None = None,
    payload: dict | None = None,
) -> Review:
    """Execute a state transition with optimistic locking.

    Args:
        session: Async database session.
        review_id: ID of the review to transition.
        from_state: Current state of the review.
        to_state: Target state for the review.
        expected_version: Expected version for optimistic locking.
        actor: Identity of the entity performing the transition.
        action: Optional action label for the audit log.
        payload: Optional extra data for the audit log.

    Returns:
        The updated Review object.

    Raises:
        InvalidTransitionError: If the transition is not in the valid map.
        TerminalStateError: If from_state is COMPLETE.
        StateConflictError: If optimistic locking detects a version mismatch.
    """
    # Validate transition is in the allowed map
    if not validate_transition(from_state, to_state):
        raise InvalidTransitionError(
            f"Invalid transition: {from_state.value} -> {to_state.value}"
        )

    # Check terminal state
    if from_state == ReviewState.COMPLETE:
        raise TerminalStateError("Cannot transition from terminal state COMPLETE")

    # Execute optimistic locking UPDATE
    stmt = (
        update(Review)
        .where(
            Review.id == review_id,
            Review.version == expected_version,
            Review.state == from_state.value,
        )
        .values(
            state=to_state.value,
            version=expected_version + 1,
            updated_at=func.now(),
        )
    )
    result = await session.execute(stmt)

    if result.rowcount == 0:
        raise StateConflictError(
            "State conflict: review was modified by another request or version mismatch"
        )

    await session.commit()

    # Append audit entry
    await append_audit(
        session,
        review_id=review_id,
        action=action or "transition",
        actor=actor,
        from_state=from_state.value,
        to_state=to_state.value,
        payload=payload,
    )

    # Emit state change event (SSE + webhook)
    from app.core.events import emit_state_change

    review = await session.get(Review, review_id)
    await emit_state_change(
        review_id=review_id,
        old_state=from_state.value,
        new_state=to_state.value,
        source_system=review.source_system,
    )

    # Refresh and return the updated review
    await session.flush()
    await session.refresh(await session.get(Review, review_id))
    return await session.get(Review, review_id)
