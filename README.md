# Household Chores Tool

API-first Django project for managing household chores.

## Setup

This project uses `uv` and requires Python 3.12 or newer.

```bash
uv sync
source .venv/bin/activate
```

## Run the project

```bash
python manage.py migrate
python manage.py runserver
```

## Run tests and checks

```bash
python manage.py check
python manage.py test
```

## Chore API contract

Authenticated administrators use `/api/household/chores/` for household-scoped
CRUD. Active household members use `/api/household/my-chores/` for their current
manual and rotation assignments plus available claim-pool chores; `POST
/api/household/my-chores/<id>/claim/` claims a currently available pool chore.
All list responses use DRF's page-number shape: `{count, next, previous,
results}`. Results are ordered by chore ID and pages contain at most 50 items;
an empty list is returned as `"results": []`. Invalid page numbers return 404.

The supported list filters are `assignment_mode=manual|rotation|claim`,
`recurrence_mode=fixed|flexible`, and `due_state=upcoming|due|overdue`.
Each filter accepts one value; unknown or contradictory values return HTTP 400
with a field-level error. Member filtering is applied after household and
assignment visibility checks.

Member result objects expose `id`, `name`, `difficulty`, `points`,
`assignment_mode`, recurrence fields and summary, `due_date`, `due_state`,
`assignee`, `claimable`, and `occurrence`. `due_state` is exactly one of
`upcoming`, `due`, or `overdue`; completion states (`pending`, `approved`,
`rejected`, and `completed`) are not part of this API and belong to issue #10.
Due dates are consumed from the recurrence model contract (issue #8).

## Completion API contract

`POST /api/household/my-chores/<chore-id>/complete/` submits the assigned
occurrence as `pending`. Household members can retrieve household-scoped
completions at `/api/household/completions/` and review another member's
pending completion with `POST /api/household/completions/<id>/review/`,
passing `{"status": "approved"}` or `{"status": "rejected"}`. Review is
single-use: a completion may transition from pending exactly once, and the
reviewer and timestamp are retained. Approval deactivates the assignment;
rejection leaves the assignment active but preserves the rejected record.
Rejected occurrences are terminal for the submitting member in v1: the same
member cannot resubmit that occurrence, and there is no retry endpoint.
Pending or rejected completions have no points, streak, badge, or leaderboard
side effects.

## Leaderboard API contract

Active household members can read the all-time leaderboard at
`/api/household/leaderboard/` (also available at
`/api/household/leaderboard/all-time/`) and the current calendar-week
leaderboard at `/api/household/leaderboard/current-period/`. Responses contain
`view`, project `timezone`, and `members`; each member has `member_id`,
`username`, `total_points`, and a deterministic competition `rank` (ties share
a rank and the next rank skips accordingly). Only active members of the
requester's household are included, with zero totals preserved. Scores come
only from the immutable points ledger.

The current-period response additionally contains `period_type` (always
`calendar_week`), `period_start` (inclusive), `period_end` (exclusive), and
the server `reference_time`. The period is Monday 00:00 through the following
Monday 00:00 in the configured project timezone. Requests are authenticated
and read-only; unauthenticated requests receive HTTP 401 and inactive members
receive HTTP 403.
