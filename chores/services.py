from .models import ChoreAssignment


def schedule_rotation(chore, occurrence):
    """Schedule one identified due occurrence for a rotation chore."""
    return ChoreAssignment.schedule_rotation(chore, occurrence)
