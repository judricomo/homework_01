# Household Chores Tool Backlog

## 1. Set up an empty Django project with a passing test
Status: Completed in PR #17
Goal: Establish a runnable Django and Django REST Framework project baseline.
Description: Configure the project structure, dependencies, settings, and test runner without implementing household or chore behavior. Add one minimal test that proves the empty project loads successfully.
Acceptance criteria:
- [x] The project starts with the documented development command.
- [x] Django system checks pass.
- [x] The test suite runs successfully with at least one passing test.
- [x] The project dependencies and local environment setup are documented.
Implementation:
- Created the `config` Django project and `chores` app.
- Added uv project metadata and a lockfile with Django and Django REST Framework dependencies.
- Registered Django REST Framework and the chores app in project settings.
- Added a project-loading test for the admin login page.
- Documented setup, run, check, and test commands in `README.md`.

## 2. Define household and membership data models
Goal: Represent one household and its members with explicit roles.
Description: Create the Household and Membership models needed for a single-household v1 system. Support administrator and regular-member roles, enforce valid user membership, and include the relationships needed by later features.
Acceptance criteria:
- A household can have multiple members.
- Each membership belongs to exactly one user and household.
- Membership roles distinguish administrators from regular members.
- Database migrations are generated and apply successfully.
- Model tests cover creation and invalid relationship or role cases.

## 3. Configure token authentication and API access
Goal: Allow registered household users to authenticate through the API.
Description: Add Django REST Framework and its built-in token authentication. Configure authenticated API access while keeping self-service signup disabled.
Acceptance criteria:
- A valid user can obtain and use an authentication token.
- Protected API requests reject missing or invalid tokens.
- Authentication configuration is enabled in the project settings.
- No public endpoint creates a new account or household membership.
- Tests cover successful authentication and rejected unauthenticated access.

## 4. Implement administrator membership management
Goal: Let a household administrator add, view, update, and remove members by email.
Description: Build the membership management API for the single household. Adding a member should locate an existing user by email or return a clear validation error, and only administrators may change membership.
Acceptance criteria:
- An administrator can add an existing user by email.
- An administrator can list and remove household members.
- Regular members cannot manage membership.
- A user cannot be added to the same household twice.
- Requests for users outside the household cannot expose unrelated membership data.
- API and permission tests cover the supported and rejected operations.

## 5. Define chore and difficulty point models
Goal: Store chores with the difficulty and point values required for scoring.
Description: Create the Chore model and the difficulty choices easy, medium, and hard. Centralize the configured point values and ensure a chore's points are derived from its difficulty rather than entered independently.
Acceptance criteria:
- A chore belongs to the household that owns it.
- Difficulty accepts only easy, medium, or hard.
- Point values are assigned consistently for each difficulty.
- Clients cannot set a conflicting point value directly.
- Administrators can create, edit, and delete chores.
- Model and API tests cover valid and invalid difficulty values.

## 6. Add chore assignment modes and assignments
Goal: Support rotation, manual, and claim-based chore assignment.
Description: Extend chores with an assignment mode and create the assignment records needed to track responsibility. Implement manual assignment and claim behavior first, including the rules that prevent conflicting claims.
Acceptance criteria:
- Each chore uses exactly one of rotation, manual, or claim modes.
- A manually assigned chore identifies its responsible household member.
- A claim-mode chore can be claimed by at most one eligible member at a time.
- Members cannot claim chores outside their household.
- Invalid assignment-mode changes or duplicate claims return clear errors.
- Tests cover each mode's validation and permission behavior.

## 7. Implement rotation scheduling
Goal: Automatically assign rotation chores to household members in sequence.
Description: Add the scheduling data and service logic for cycling a rotation chore through eligible household members. Define deterministic behavior when members are added, removed, or skipped.
Acceptance criteria:
- A rotation chore has a defined schedule and ordered member sequence.
- The next eligible member is selected deterministically.
- Completing or advancing a rotation moves responsibility to the next member.
- Removed or inactive members are skipped safely.
- Rotation does not assign a chore to a member outside the household.
- Tests cover normal cycles and membership changes.

## 8. Add fixed and flexible recurrence rules
Goal: Calculate when chores become due again.
Description: Support calendar-based recurrence for daily, weekly, every-N-days, and selected weekdays. Also support flexible recurrence based on N days after the last approved completion, with explicit timezone-aware date handling.
Acceptance criteria:
- A chore can represent each supported fixed recurrence type.
- A flexible recurrence stores a positive day interval.
- Invalid or contradictory recurrence parameters are rejected.
- The next due date is calculated correctly for each recurrence type.
- Flexible recurrence uses the last approved completion rather than a pending or rejected one.
- Tests cover boundary dates, weekdays, and timezone behavior.

## 9. Implement chore listing and assignment APIs
Goal: Give household members a secure API for viewing their available chores.
Description: Expose endpoints for administrators to manage chores and for members to view chores assigned to them or available in the claim pool. Include due, overdue, assignment, recurrence, difficulty, and point information.
Acceptance criteria:
- Administrators can create, update, list, and delete household chores.
- Members can list only chores relevant to their household and assignment state.
- Claim-pool chores are visible to eligible members.
- Due and overdue status is calculated consistently.
- Non-members cannot read or modify household chores.
- API tests cover filtering, visibility, and role permissions.

## 10. Implement completion submission and verification
Goal: Require approval before a chore earns credit.
Description: Create Completion records and endpoints for members to report chores as done. Add pending, approved, and rejected states, require another household member to review a completion, and prevent self-approval.
Acceptance criteria:
- A member can submit a valid completion for an eligible chore.
- New completions start in pending status.
- Another household member can approve or reject the completion.
- The submitting member cannot approve their own completion.
- Duplicate active completions for the same chore occurrence are prevented.
- Rejected completions do not award points or update gamification data.
- Tests cover submission, review, state transitions, and permissions.

## 11. Build the points ledger and scoring updates
Goal: Record immutable point awards for approved completions.
Description: Add a PointsLedger model and transaction-safe logic that awards the chore's difficulty points exactly once when a completion is approved. Preserve historical entries so totals remain auditable.
Acceptance criteria:
- Approval creates one ledger entry with the correct point value.
- Pending and rejected completions create no point entries.
- Repeated approval requests do not award points twice.
- Ledger entries identify the member, chore, completion, and award time.
- All-time totals can be calculated from ledger history.
- Tests cover idempotency, rollback behavior, and point calculations.

## 12. Implement streak tracking
Goal: Track each member's consecutive days with approved activity.
Description: Calculate per-person daily streaks from approved completions only. Update streak state when a completion is approved and define behavior for same-day activity, missed days, and timezone boundaries.
Acceptance criteria:
- An approved completion counts as activity for its local calendar day.
- Multiple approvals on one day do not inflate the streak.
- Consecutive activity days extend the streak.
- A missed day resets the current streak while preserving the historical best if tracked.
- Pending and rejected completions never affect streaks.
- Tests cover same-day, consecutive-day, missed-day, and timezone cases.

## 13. Define and award milestone badges
Goal: Automatically award the fixed v1 badge set.
Description: Define the predefined badge catalog and award member badges when approved activity crosses configured thresholds. Badge awards must be durable and idempotent.
Acceptance criteria:
- The predefined badges and their threshold rules are stored or configured centrally.
- Supported examples include a 7-day streak, 100 points, and 50 completed chores.
- Badge checks run only after an approved completion updates the relevant metric.
- A member receives each badge at most once.
- Badge awards remain visible after later activity changes.
- Tests cover threshold crossing, below-threshold activity, and duplicate checks.

## 14. Add all-time and current-period leaderboards
Goal: Expose historical and current-period rankings by approved points.
Description: Build leaderboard endpoints for all-time totals and a current week or month view. Preserve historical ledger data across period boundaries and document the selected period and timezone rules.
Acceptance criteria:
- The all-time leaderboard includes approved points across all historical periods.
- The current-period leaderboard includes only points in the configured period.
- Pending and rejected completions are excluded.
- Ties use a documented deterministic ordering.
- Period boundaries use the documented calendar and timezone behavior.
- Tests cover period transitions, ties, and historical preservation.

## 15. Add in-app due and overdue notification surfaces
Goal: Show members which chores need attention without external notifications.
Description: Provide API or dashboard data that identifies chores due soon and overdue for the requesting member. Keep v1 notifications entirely in-app with no email, push, or chat integration.
Acceptance criteria:
- An authenticated member can retrieve their due chores.
- Overdue chores are identified using the same recurrence and timezone rules as chore listings.
- The response includes enough assignment and due-date information for a frontend to render it.
- Members cannot see another household's notification data.
- No email, push, or chat notification provider is introduced.
- API tests cover due, overdue, completed, and inaccessible chores.

## 16. Document API behavior and v1 scope
Goal: Make the implemented API understandable to contributors and frontend developers.
Description: Document authentication, endpoints, request and response shapes, roles, state transitions, recurrence rules, scoring values, badge thresholds, and leaderboard period rules. Record explicit v1 exclusions so later work does not silently expand scope.
Acceptance criteria:
- API endpoints and required permissions are documented.
- Difficulty point values and badge thresholds are documented.
- Completion state transitions are documented.
- Leaderboard period and timezone behavior is documented.
- Out-of-scope features from the project plan are clearly listed.
- Documentation matches the implemented behavior.
