"""Sets a maintenance task's last-completed date and the next-due date that follows from it."""
from app.maintenance_calc import compute_next_due


def set_last_completed(task, completed_at):
    """Record completed_at as the task's last completion and reschedule its next due date."""
    task.last_completed_at = completed_at
    task.next_due_at = compute_next_due(completed_at, task.frequency_value, task.frequency_unit.value)


def start_schedule(task, created_on):
    """Assume a new task's maintenance is current as of created_on, so it surfaces one interval out.

    Without this a new task has no due date and never shows up in reminders until
    someone marks it done once; the user can correct the assumed date afterward.
    """
    set_last_completed(task, created_on)
