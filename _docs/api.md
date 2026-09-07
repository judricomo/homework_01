# Household chores API contract (v1)

This page is the source of truth for the API that is implemented in this
repository. It describes the current Django REST Framework behavior, not
future routes from the product plan. The API is frontend-agnostic and serves
one household per user.

## Base URL and conventions

The development base URL is `http://localhost:8000`. All routes below are
relative to it and use JSON unless stated otherwise. Timestamps are ISO 8601
timezone-aware values. The configured project timezone is `UTC`
(`TIME_ZONE` in `config/settings.py`); date calculations use that timezone.

Protected endpoints require:

```http
Authorization: Token <token>
Accept: application/json
Content-Type: application/json
```

`GET` requests do not need a body. `POST`, `PATCH`, and `PUT` bodies must be
JSON. The API uses DRF's standard error shape:

```json
{"detail": "A human-readable message."}
```

Field validation errors use a field-to-list/object shape, for example
`{"email": ["No existing user was found with this email."]}`. A malformed JSON
body returns `400` with `{"detail": "JSON parse error - ..."}`. Unsupported
methods return `405` with `{"detail": "Method \"...\" not allowed."}`.

## Authentication

`POST /api/auth/token/` is the token issuance route. It accepts form-encoded
or JSON `username` and `password` fields and returns `200`:

```json
{"token": "redacted-token"}
```

The token is reusable and issuing it again for the same user returns the
existing token. Missing credentials, unknown users, and invalid passwords
return `400` with the serializer error shape (normally
`{"non_field_errors": ["Unable to log in with provided credentials."]}`).
This route is the only authentication route; there is no signup or token
refresh/revocation API.

Missing, malformed, expired/deleted, or unknown tokens on a protected route
return `401` and do not execute the action:

```json
{"detail": "Authentication credentials were not provided."}
```

or:

```json
{"detail": "Invalid token."}
```

An authenticated user without an active membership receives `403` from
member routes. An authenticated regular member attempting an administrator
route receives `403`:

```json
{"detail": "Household administrator permissions are required."}
```

## Household isolation and permissions

Every protected query is scoped from the authenticated user's active
membership. Clients cannot select a household by supplying an ID. Users have
one membership, and inactive memberships cannot use the API. Objects from
another household, and unknown IDs, are deliberately indistinguishable:
detail lookups return `404` (`{"detail": "Not found."}`), without revealing
whether the identifier exists. This applies to chores, memberships,
assignments, occurrences, and completions.

Administrator means an active membership with role `admin`. Member means any
active membership; administrators also have member access. The API does not
expose a route to create users or choose a membership's household.

## Endpoint inventory

| Method and path | Auth / permission | Request | Success |
|---|---|---|---|
| `POST /api/auth/token/` | None | `username`, `password` | `200`, token |
| `GET /api/household/members/` | Active administrator | none | `200`, membership array |
| `POST /api/household/members/` | Active administrator | `email` | `201`, membership object |
| `GET /api/household/members/{id}/` | Active administrator | none | `200`, membership object |
| `PATCH /api/household/members/{id}/` | Active administrator | `role` | `200`, membership object |
| `PUT /api/household/members/{id}/` | Active administrator | `role` | `200`, membership object |
| `DELETE /api/household/members/{id}/` | Active administrator | none | `204`, empty body |
| `GET /api/household/chores/` | Active administrator | optional filters | `200`, paginated chore object |
| `POST /api/household/chores/` | Active administrator | chore fields | `201`, chore object |
| `GET /api/household/chores/{id}/` | Active administrator | none | `200`, chore object |
| `PUT/PATCH /api/household/chores/{id}/` | Active administrator | chore fields | `200`, chore object |
| `DELETE /api/household/chores/{id}/` | Active administrator | none | `204`, empty body |
| `GET /api/household/my-chores/` | Active member | optional filters, pagination | `200`, paginated work object |
| `GET /api/household/my-chores/{id}/` | Active member | none | `200`, work object |
| `POST /api/household/my-chores/{id}/claim/` | Active member | none | `201`, work object |
| `POST /api/household/my-chores/{id}/complete/` | Active member eligible for occurrence | `occurrence`, optional `chore` | `201`, completion |
| `GET /api/household/completions/` | Active member | none | `200`, completion array |
| `GET /api/household/completions/{id}/` | Active member | none | `200`, completion |
| `POST /api/household/completions/{id}/review/` | Active member other than submitter | `status` | `200`, completion |
| `GET /api/household/leaderboard/` | Active member | none | `200`, all-time leaderboard |
| `GET /api/household/leaderboard/all-time/` | Active member | none | `200`, all-time leaderboard |
| `GET /api/household/leaderboard/current-period/` | Active member | none | `200`, current calendar week |
| `GET /api/household/due-overdue/` | Active member | none | `200`, due surface |

The router also provides `HEAD` and `OPTIONS` where DRF permits them. No
assignment-management, streak, badge, points-ledger, notification, signup,
or arbitrary date-range endpoint is implemented.

### Common object shapes

Membership:

```json
{"id": 2, "user": {"id": 8, "username": "member", "email": "redacted@example.com"},
 "household": {"id": 1, "name": "Redacted household"}, "role": "member",
 "created_at": "2026-09-06T12:00:00Z", "updated_at": "2026-09-06T12:00:00Z"}
```

Chore fields are `id`, `name`, `difficulty` (`easy|medium|hard`), read-only
`points` (`1|3|5`), `assignment_mode` (`manual|rotation|claim`),
`recurrence_mode` (`fixed|flexible`), `fixed_recurrence`
(`daily|weekly|every_n_days|selected_weekdays`),
`recurrence_interval_days`, `selected_weekdays` (weekday integers 0–6),
`anchor_date`, read-only `recurrence`, and read-only `due_date`.
`POST` and updates cannot set `id`, `points`, `recurrence`, or `due_date`;
the household is always taken from the authenticated administrator.

`my-chores` adds `assignee` (`null` or `{membership_id, username}`),
`claimable`, `due_state` (`upcoming|due|overdue`), and `occurrence`.
Claim-pool chores are visible when available; assigned chores are visible only
to their assigned active member.

Completions contain `id`, `chore`, `assignment`, `occurrence`, `status`
(`pending|approved|rejected`), `submitted_at`, `submitter`,
`reviewer_detail` (nullable), and `reviewed_at` (nullable). All completion
fields are read-only in the list/detail serializer.

List endpoints for chores and my-chores use page-number pagination, page size
50, and return `count`, `next`, `previous`, and `results`. A page beyond the
last returns `404`. Membership and completion lists are unpaginated arrays.
Chore/work lists are deterministically ordered by ascending ID; completion
history is newest submission first.

### Membership management

`POST /members/` takes `{"email": "person@example.com"}`. Surrounding
whitespace is trimmed and matching is case-insensitive. The user must already
exist, have exactly one matching email, and not already belong to a household.
Validation failures are `400`; success is `201` and creates a regular member.
`PATCH`/`PUT` accept only `{"role": "admin"}` or `{"role": "member"}`.
The last administrator cannot be demoted or deleted (`400`):

```json
{"role": ["The household must retain at least one administrator."]}
```

Deletion of another membership succeeds with `204`; there is no soft-delete
through this endpoint.

### Chores and work

Only administrators can create, modify, or delete chores. Validation errors
are `400` and identify fields, including blank names, invalid choices,
non-positive intervals, invalid weekday lists, and incompatible recurrence
fields. Changing assignment mode while conflicting active assignments exist
is rejected with `400`.

`claim` is valid only for claim-mode chores available on their due date; a
successful first claim creates one active assignment and returns `201`.
Already claimed, future, or concurrent claims return `409`:

```json
{"detail": "This chore occurrence has already been claimed."}
```

The optional list filters are single-valued `assignment_mode`,
`recurrence_mode`, and `due_state`; invalid or repeated values return `400`.
Unknown query parameters are ignored.

`complete` requires a UUID `occurrence` and, if `chore` is supplied, it must
match the path. The caller must be the active assignee for that occurrence.
It creates a pending completion (`201`). Missing/invalid fields and
unavailable, ineligible, duplicate, or previously rejected submissions return
`400` with `detail` or field errors. Rejected history is immutable and
terminal for that submitter and occurrence: there is no retry route.

### Completion review and state machine

`pending -> approved` or `pending -> rejected` is the only transition.
Any active household member other than the submitter may review. The status
body is exactly `{"status": "approved"}` or `{"status": "rejected"}`.
Self-review, invalid status, unknown/cross-household ID, and review of an
already finalized completion return `400`, `404`, or field validation `400`
as applicable. A finalized record cannot be changed.

Approval deactivates the assignment and synchronously performs all effects:
one immutable points-ledger entry, one daily activity record/streak update,
and fixed badge evaluation. Rejection performs none of those effects and does
not advance recurrence. Pending records are visible in completion history and
remain due/overdue. Rejected records remain visible as immutable history.

### Recurrence, scoring, streaks, and badges

Difficulty points are fixed: easy `1`, medium `3`, hard `5`. Fixed recurrence
supports daily, weekly, every N days, and selected weekdays. Flexible
recurrence is N local days after the latest approved completion. The first due
date is `anchor_date`; only approved completions advance flexible recurrence.
Selected weekdays use Python weekday numbering (Monday `0` through Sunday `6`).
All local dates and local-midnight due timestamps use UTC in this project;
DST behavior therefore follows UTC (there are no local DST jumps).

The points ledger is append-only and one-to-one with an approved completion.
Calling the award operation repeatedly is idempotent and returns the existing
entry. Ledger entries and badge awards cannot be edited or deleted.
The fixed badge catalog is:

| Identifier | Threshold |
|---|---|
| `seven_day_streak` | current streak >= 7 local calendar days |
| `hundred_points` | approved points >= 100 |
| `fifty_completions` | approved completions >= 50 |

Each badge is awarded at most once and history is retained. There is no badge
API in v1; awards are persisted for future consumers.

### Leaderboards

All active members of the caller's household are included, including members
with zero points. Results are ordered by total points descending, then
membership ID ascending. Ties share the same rank using competition ranking
(for example 1, 1, 3). Inactive members are excluded.

The default and `/all-time/` views sum all approved-completion ledger entries.
`/current-period/` is the Monday-inclusive, seven-day calendar week in the
project timezone: `period_start <= awarded_at < period_end`. It returns
`period_type: "calendar_week"`, `period_start`, `period_end`, and the server
`reference_time`; boundaries are timezone-aware and stable across UTC
midnight/DST rules. Period rollover does not delete ledger history. Custom
periods and arbitrary date ranges are deferred.

### Due and overdue surface

`GET /due-overdue/` is read-only and returns:

```json
{"timezone": "UTC", "as_of": "2026-09-06T12:00:00Z",
 "due": [], "overdue": []}
```

Each item contains a minimal `chore` (`id`, `name`), nullable `occurrence`,
nullable assigned member, `claimable`, `due_date`, midnight `due_at`,
`due_state` (`due|overdue`), and recurrence context. The current local date
equal to `due_date` is `due`; a later date is `overdue`; future dates are
omitted. Approved completion removes that occurrence, while pending or
rejected completion leaves it visible. Only the caller's active assignments
and currently available claim-pool chores are returned, ordered by chore ID.
Empty collections are valid. The endpoint sends no email, push, chat, webhook,
or other external notification.

## Verification and open items

The contract was checked against `config/urls.py`, `chores/urls.py`,
serializers, permissions, views, models, and the focused API/model tests in
`chores/tests.py`; run `python manage.py check` and `python manage.py test`
after changes. Examples use redacted values and the actual serializer fields.
There are no documentation-specific tests currently in the repository.

The following are intentionally not silently specified: exact production
deployment host, token expiry/revocation policy, user provisioning, and
frontend presentation. They require implementation/product decisions.

## v1 exclusions and follow-ups

V1 excludes multi-tenancy, self-service signup or invite links/codes, photo
verification, email/push/chat notifications, administrator-defined custom
badges, per-chore on-time streaks, custom leaderboard periods, and arbitrary
date ranges. The frontend consumer is [#18](https://github.com/judricomo/homework_01/issues/18);
custom periods are [#19](https://github.com/judricomo/homework_01/issues/19);
self-service signup/invites are [#20](https://github.com/judricomo/homework_01/issues/20);
custom badges are [#21](https://github.com/judricomo/homework_01/issues/21).
The fixed badge implementation is tracked in [#13](https://github.com/judricomo/homework_01/issues/13).
See the product scope in [`_docs/plan.md`](_docs/plan.md).
