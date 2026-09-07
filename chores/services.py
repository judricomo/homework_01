from .models import ChoreAssignment, Completion, PointsLedger


def schedule_rotation(chore, occurrence):
    """Schedule one identified due occurrence for a rotation chore."""
    return ChoreAssignment.schedule_rotation(chore, occurrence)


def calculate_next_due_date(chore, prior_due_date=None, completions=()):
    """Calculate a chore's next due local date."""
    return chore.next_due_date(prior_due_date, completions)


def submit_completion(*, membership, chore, occurrence):
    return Completion.submit(
        membership=membership, chore=chore, occurrence=occurrence
    )


def review_completion(*, completion_id, reviewer, status):
    return Completion.review(
        completion_id=completion_id, reviewer=reviewer, status=status
    )



def award_points_for_completion(completion):
    return PointsLedger.award_for_completion(completion)


def award_completion_points(completion):
    return PointsLedger.award_for_completion(completion)


def score_for_member(member):
    return PointsLedger.total_for_member(member)
