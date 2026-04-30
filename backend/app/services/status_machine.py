"""
Status machine for Application.

Defines which transitions are allowed and enforces them. Prevents
invalid moves like "from CANCELLED back to ACTIVE".

To add a new valid transition: add it to ALLOWED_TRANSITIONS below.
"""

from app.models import Application, ApplicationStatus

S = ApplicationStatus


class InvalidTransition(Exception):
    pass


# (from_status, to_status) — list of valid transitions
ALLOWED_TRANSITIONS: set[tuple[ApplicationStatus, ApplicationStatus]] = {
    # Linear forward path
    (S.DRAFT, S.AWAITING_DATA),
    (S.AWAITING_DATA, S.READY_TO_ASSIGN),
    (S.READY_TO_ASSIGN, S.ASSIGNED),
    (S.ASSIGNED, S.DRAFTS_GENERATED),
    (S.DRAFTS_GENERATED, S.AT_TRANSLATOR),
    (S.AT_TRANSLATOR, S.AWAITING_SCANS),
    (S.AWAITING_SCANS, S.AWAITING_DIGITAL_SIGN),
    (S.AWAITING_DIGITAL_SIGN, S.SUBMITTED),
    (S.SUBMITTED, S.APPROVED),
    (S.SUBMITTED, S.REJECTED),
    (S.SUBMITTED, S.NEEDS_FOLLOWUP),
    (S.NEEDS_FOLLOWUP, S.SUBMITTED),  # после доподачи

    # Hold/cancel from anywhere active
    (S.AWAITING_DATA, S.HOLD),
    (S.READY_TO_ASSIGN, S.HOLD),
    (S.ASSIGNED, S.HOLD),
    (S.DRAFTS_GENERATED, S.HOLD),
    (S.AT_TRANSLATOR, S.HOLD),
    (S.AWAITING_SCANS, S.HOLD),
    (S.AWAITING_DIGITAL_SIGN, S.HOLD),
    (S.HOLD, S.AWAITING_DATA),  # resume

    # Cancel — terminal
    (S.AWAITING_DATA, S.CANCELLED),
    (S.READY_TO_ASSIGN, S.CANCELLED),
    (S.ASSIGNED, S.CANCELLED),
    (S.DRAFTS_GENERATED, S.CANCELLED),
    (S.AT_TRANSLATOR, S.CANCELLED),
    (S.AWAITING_SCANS, S.CANCELLED),
    (S.AWAITING_DIGITAL_SIGN, S.CANCELLED),
    (S.HOLD, S.CANCELLED),

    # Backwards moves (manager wants to fix something)
    (S.READY_TO_ASSIGN, S.AWAITING_DATA),
    (S.ASSIGNED, S.READY_TO_ASSIGN),
    (S.DRAFTS_GENERATED, S.ASSIGNED),  # regenerate
}


def can_transition(from_status: ApplicationStatus, to_status: ApplicationStatus) -> bool:
    """Pure function — useful in tests and UI for showing/hiding buttons."""
    return (from_status, to_status) in ALLOWED_TRANSITIONS


def transition(application: Application, new_status: ApplicationStatus) -> None:
    """
    Move application to new status. Raises InvalidTransition if not allowed.
    Mutates the passed application — caller must commit the session.
    """
    if not can_transition(application.status, new_status):
        raise InvalidTransition(
            f"Cannot transition from {application.status.value} to {new_status.value}"
        )
    application.status = new_status


def allowed_next_statuses(from_status: ApplicationStatus) -> list[ApplicationStatus]:
    """For UI: which buttons to show on the application detail screen."""
    return [to for (frm, to) in ALLOWED_TRANSITIONS if frm == from_status]
