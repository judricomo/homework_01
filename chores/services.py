from .models import ChoreAssignment


def schedule_rotation(chore, occurrence):
    """Schedule one identified due occurrence for a rotation chore."""
    return ChoreAssignment.schedule_rotation(chore, occurrence)


def calculate_next_due_date(chore, prior_due_date=None, completions=()):
    """Calculate a chore's next due local date."""
    return chore.next_due_date(prior_due_date, completions)
