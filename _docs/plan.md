# Household Chores Tool — Project Scope

**Stack**: Django + Django REST Framework (API-first, frontend-agnostic). Token authentication (DRF built-in).

## Users & Households

- Single household with multiple members (not multi-tenant for v1).
- An admin adds members by email — no open self-signup.
- Admin permissions: create/edit/delete chores, manage household membership.
- Regular members: complete chores, approve/reject each other's completions.

## Chores

Each chore has:

- A **difficulty tag** (easy / medium / hard) that auto-derives its point value.
- An **assignment mode**, set per chore:
  - Rotation — automatically cycles between members on a schedule.
  - Manual — someone assigns it each time.
  - Claim — sits in a shared pool until a member claims it.
- A **recurrence rule**, either:
  - Fixed/calendar-based (daily, weekly, every N days, specific weekdays), or
  - Flexible (reappears N days after the last completion, regardless of calendar date).

## Completion & Verification

1. A member marks a chore done (self-reported, no photo proof).
2. The completion sits as **pending**.
3. Another household member must **approve** it.
4. Only on approval do points, streaks, and badge checks apply.

Rejected completion records are immutable history. In v1, rejection is
terminal for that submitter and occurrence: the submitter cannot retry it and
the API does not create a replacement completion route. Rejection leaves the
assignment active for the assignment lifecycle, but it awards no
points/streaks/badges and does not advance recurrence.

## Gamification

- **Points**: auto-calculated from each chore's difficulty tag.
- **Leaderboard**: shows both an all-time total and a current period (week/month) view; history is preserved across period resets.
- **Streaks**: per-person, based on daily activity (consecutive days with at least one approved completion).
- **Badges**: a predefined, fixed set of milestone badges (e.g. "7-day streak", "100 points", "50 chores completed"), auto-awarded when thresholds are crossed.

## Notifications

- In-app only for v1 (dashboard/API surfaces due and overdue chores).
- No email or push notifications in this phase.

## Explicitly Out of Scope (v1)

- Multiple households / multi-tenancy.
- Self-service signup or invite links/codes.
- Photo-proof verification.
- Email or push/chat notifications.
- Admin-defined custom badges (using a fixed predefined set instead).
- Per-chore on-time completion streaks (only per-person daily streaks for now).

## Open Items for Next Pass

- Data models (Household, Membership, Chore, ChoreAssignment, Completion, Streak, Badge, PointsLedger).
- API endpoint list and permissions per role.
- Exact point values per difficulty tier.
- Exact badge thresholds.
- Period boundaries for the leaderboard reset (calendar week vs. rolling, timezone handling).
