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
