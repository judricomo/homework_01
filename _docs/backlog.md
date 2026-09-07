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
Status: Groomed in [#2](https://github.com/judricomo/homework_01/issues/2)
Goal: Represent one household and its members with explicit roles.
Description: Create the Household and Membership models needed for a single-household v1 system. Support administrator and regular-member roles, enforce valid user membership, and include the relationships needed by later features.
Acceptance criteria:
- [ ] A household has a required non-blank name and managed timestamps.
- [ ] Each membership links exactly one built-in Django user to exactly one household.
- [ ] Membership roles accept only administrator or regular-member values.
- [ ] Duplicate user memberships in one household and memberships across multiple households are rejected.
- [ ] Deletion behavior leaves no orphaned memberships.
- [ ] Migrations apply cleanly and focused model tests cover valid and invalid cases.

## 3. Configure token authentication and API access
Status: Groomed in [#3](https://github.com/judricomo/homework_01/issues/3)
Goal: Enable existing Django users to authenticate through Django REST Framework token authentication and use authenticated API resources.
Description: Add the documented token endpoint and centrally configured token authentication and permissions. Keep account creation, membership management, and household authorization outside this task.
Acceptance criteria:
- [ ] `POST /api/auth/token/` accepts valid existing-user credentials and returns HTTP 200 with a reusable DRF token.
- [ ] Repeating issuance for the same user returns the existing token rather than creating duplicate active tokens.
- [ ] A protected request with `Authorization: Token <valid-token>` is authenticated as the token owner.
- [ ] Protected requests without authorization, with malformed or unknown tokens, or with deleted/revoked tokens return HTTP 401 and do not execute the action.
- [ ] Invalid credentials cannot obtain a token and do not reveal whether the username exists.
- [ ] Central API settings require authentication by default while allowing explicit public opt-out.
- [ ] Token authentication does not imply household membership; household-scoped resources enforce their own authorization.
- [ ] No endpoint in this task creates, updates, or deletes users, households, or memberships.
- [ ] Focused tests cover issuance, reuse, authenticated access, missing/malformed/unknown/revoked tokens, invalid credentials, and the no-signup boundary.
Out of scope:
- Administrator membership changes: [#4](https://github.com/judricomo/homework_01/issues/4)
- Household and membership models: [#2](https://github.com/judricomo/homework_01/issues/2)
- Chore endpoints and domain permissions: [#5](https://github.com/judricomo/homework_01/issues/5) and [#9](https://github.com/judricomo/homework_01/issues/9)
- Self-service signup and invite links/codes: [#20](https://github.com/judricomo/homework_01/issues/20)
- JWT, third-party identity providers, password reset/email verification, and external notification delivery remain outside the v1 authentication contract.
Constraints:
- Use DRF's built-in `TokenAuthentication` and token model; do not add JWT or a custom user model.
- Use the documented endpoint and `Authorization: Token` format; do not add an undocumented bearer alias.
- Limit changes to project settings, token-auth URL/view wiring, required token migrations, and focused API tests.
- Preserve Django password authentication and keep credentials and token values out of logs and error messages.
- Keep authentication separate from household authorization so a valid token cannot grant access to another household's data.

## 4. Implement administrator membership management
Status: Groomed in [#4](https://github.com/judricomo/homework_01/issues/4)
Goal: Let a household administrator add, view, update, and remove members in the single v1 household.
Description: Build the authenticated membership-management API on top of the Household and Membership models. An administrator can add an existing user by email, list members, change member roles, and remove members while preserving household isolation and at least one administrator. Unknown users are rejected; signup and invitation flows remain separate.
Acceptance criteria:
- [ ] An authenticated administrator can add exactly one existing user by email, defaulting the new membership to regular member, and the response identifies the user, household, role, and membership.
- [ ] Email lookup trims surrounding whitespace and is case-insensitive; an unknown email returns a clear validation error without creating a user or membership.
- [ ] A user already belonging to the household, including an email that differs only by case or whitespace, returns a clear conflict or validation error without creating a duplicate membership.
- [ ] If email lookup matches more than one existing user, the request fails clearly and makes no membership change.
- [ ] An administrator can list all and retrieve individual members for only their household; another household's members are never returned or addressable.
- [ ] An administrator can change a member between regular-member and administrator roles.
- [ ] Removing or demoting the last household administrator is rejected; removing a different member succeeds.
- [ ] A member cannot remove or demote themself when doing so would leave the household without an administrator.
- [ ] Regular members receive HTTP 403 for add, list, role-change, and remove operations; unauthenticated requests receive HTTP 401 according to the configured API policy.
- [ ] Failed validation, authorization, and cross-household requests are side-effect free.
- [ ] Focused API tests cover add, list, retrieve, role changes, remove, normalization, unknown/duplicate/ambiguous emails, last-admin protection, self-demotion/removal, authentication, authorization, and household scoping.
Out of scope:
- User creation, open signup, invitations, invite links/codes, and onboarding for unknown emails: [#20](https://github.com/judricomo/homework_01/issues/20)
- Token issuance and token lifecycle: [#3](https://github.com/judricomo/homework_01/issues/3)
- Frontend member-management screens: [#18](https://github.com/judricomo/homework_01/issues/18)
Constraints:
- Use the Household and Membership models from [#2](https://github.com/judricomo/homework_01/issues/2) and existing-user records; do not create a custom user model.
- Enforce administrator permissions server-side and scope every read/write by the authenticated administrator's household.
- Preserve at least one administrator for every household, including on role changes and deletion.
- Keep API routes, serializers, permissions, and focused tests within the chores domain unless project URL wiring is required.

## 5. Define chore and difficulty point models
Status: Groomed in [#5](https://github.com/judricomo/homework_01/issues/5)
Goal: Define the foundational Chore model with a controlled difficulty and deterministic, difficulty-derived points.
Description: Create the Chore model associated with exactly one household. Require a trimmed non-blank name and one of the `easy`, `medium`, or `hard` difficulty choices, using the canonical mapping `easy = 1`, `medium = 3`, and `hard = 5`. Keep point derivation in one reusable domain location and reject conflicting client or model values.
Acceptance criteria:
- [ ] A chore requires exactly one household and a name that is non-blank after surrounding whitespace is trimmed.
- [ ] Difficulty is required and accepts only `easy`, `medium`, or `hard`; invalid values cannot be persisted.
- [ ] The canonical mapping is `easy = 1`, `medium = 3`, and `hard = 5`, defined once in the chores domain.
- [ ] Creation and difficulty changes derive and store the matching points value.
- [ ] Conflicting point values cannot be persisted, including through direct model updates.
- [ ] Failed validation leaves an existing chore and its points unchanged.
- [ ] Migrations apply cleanly and focused model tests cover valid/invalid values, derivation, tamper resistance, side-effect-free failures, and required household relationships.
Out of scope:
- Chore CRUD endpoints, household-scoped API querysets, and administrator/member API permissions: [#9](https://github.com/judricomo/homework_01/issues/9)
- Assignment modes and assignment records: [#6](https://github.com/judricomo/homework_01/issues/6)
- Rotation scheduling: [#7](https://github.com/judricomo/homework_01/issues/7)
- Recurrence and due-date calculation: [#8](https://github.com/judricomo/homework_01/issues/8)
- Completion approval and historical points awards: [#10](https://github.com/judricomo/homework_01/issues/10) and [#11](https://github.com/judricomo/homework_01/issues/11)
Constraints:
- Keep changes in `chores/models.py` and `chores/migrations/`; do not implement API endpoints in this task.
- Use Django validation and database constraints where supported, with one reusable difficulty/points mapping.
- Use the Household relationship from [#2](https://github.com/judricomo/homework_01/issues/2) and preserve the household boundary for downstream work.

## 6. Add chore assignment modes and assignments
Status: Groomed in [#6](https://github.com/judricomo/homework_01/issues/6)
Goal: Extend each chore with one assignment mode and provide household-scoped assignment records for manual responsibility and claim-pool responsibility.
Description: Add the assignment-mode and assignment data needed by later APIs and rotation scheduling. Implement validated manual assignment and transaction-safe claim behavior in the domain layer, while keeping scheduling and HTTP endpoint work in their dedicated issues.
Acceptance criteria:
- [ ] Every chore stores exactly one assignment mode: `manual`, `rotation`, or `claim`; missing, unknown, or multiple values cannot be persisted.
- [ ] A manual assignment references exactly one active member of the chore’s household, and an assignment for another household, a non-member, or an inactive member is rejected without saving.
- [ ] A claim-mode chore with no active claim has an explicitly unclaimed state; a valid household member can claim it once, and the successful claim identifies that member.
- [ ] A claim cannot be created for a chore in `manual` or `rotation` mode, and a manual assignment cannot be created for a chore in `claim` or `rotation` mode; each rejected operation returns a clear validation error and has no side effects.
- [ ] At most one active assignment exists for a chore occurrence: repeated claims by the same member and claims by different members are rejected after the first successful claim, including when requests race concurrently.
- [ ] Assignment and claim writes are transaction-safe and enforce uniqueness at the database level where supported, so retrying a failed claim cannot replace or duplicate the winning assignment.
- [ ] Changing a chore’s mode is validated: it cannot leave active assignments contradictory to the new mode, and a failed transition leaves the mode and assignments unchanged.
- [ ] Rotation-mode chores retain the household/member and ordering data required by [#7](https://github.com/judricomo/homework_01/issues/7), without advancing the rotation or creating scheduler side effects in this task.
- [ ] Focused model/service tests cover each mode, missing and invalid modes, active/inactive and cross-household members, duplicate and concurrent claims, mode transitions, database constraints, and side-effect-free failures.
Out of scope:
- Rotation ordering, advancement, skipped/removed-member behavior, and scheduling execution: [#7](https://github.com/judricomo/homework_01/issues/7)
- Fixed/flexible recurrence, occurrence generation, and due-date calculation: [#8](https://github.com/judricomo/homework_01/issues/8)
- Chore and assignment HTTP endpoints, request authentication, administrator/member API permissions, and claim responses: [#9](https://github.com/judricomo/homework_01/issues/9)
- Completion submission, approval, and clearing or recreating assignments after an approved occurrence: [#10](https://github.com/judricomo/homework_01/issues/10)
- Chore CRUD, difficulty validation, and point derivation: [#5](https://github.com/judricomo/homework_01/issues/5)
Constraints:
- Use the Household and Membership boundary from [#2](https://github.com/judricomo/homework_01/issues/2); every assignment query and write must be household-scoped.
- Keep implementation in the chores domain models/services and migrations, with focused tests; do not add HTTP routes or serializers here.
- Use database constraints and transactions for active-assignment uniqueness and claim races; do not rely on an application-only pre-check.
- Preserve assignment history needed by later completion and leaderboard work; do not silently overwrite the winning claimant.
- Keep rotation scheduling policy and recurrence policy out of this task; expose only the data and invariants their follow-up issues require.

## 7. Implement rotation scheduling
Status: Groomed in [#7](https://github.com/judricomo/homework_01/issues/7)
Goal: Automatically assign rotation chores to household members in sequence.
Description: Add the scheduling data and domain service for assigning each due rotation-chore occurrence to the next eligible household member. Preserve a deterministic order and cursor so retries, membership changes, and empty eligibility do not produce duplicate or surprising assignments.
Acceptance criteria:
- [x] A rotation chore stores an explicit ordered sequence of household members and the rotation state needed to identify the next position; the sequence rejects members from another household and preserves a stable order when read back.
- [x] Scheduling accepts one identified due occurrence and selects the first active, eligible member at or after the stored position, wrapping to the beginning when necessary; the same inputs always select the same member.
- [x] A successful scheduling call creates exactly one active assignment for that occurrence and advances the rotation position exactly once, to the position after the assigned member.
- [x] Repeating scheduling for the same chore occurrence is idempotent: it returns or reuses the existing active assignment, does not create another assignment, and does not advance the position again.
- [x] Members who are removed, inactive, or otherwise ineligible when an occurrence is scheduled are skipped without being assigned; the next eligible member receives the assignment and becomes the new rotation position.
- [x] A one-member rotation assigns that member for each otherwise-eligible occurrence and leaves the position stable after each successful assignment.
- [x] If no sequence member is eligible, scheduling creates no assignment, reports a no-eligible-member outcome, and leaves the rotation position unchanged so a later retry can succeed after membership changes.
- [x] Concurrent or retried scheduling cannot create duplicate active assignments for one occurrence or skip an additional member; assignment uniqueness and the position update are transaction-safe.
- [x] Focused tests cover normal cycling and wraparound, one-member rotations, removed/inactive members, sequence changes, repeated and concurrent scheduling, and no eligible members.
Out of scope:
- Full recurrence-rule storage, due-date calculation, timezone policy, and occurrence generation: [#8](https://github.com/judricomo/homework_01/issues/8)
- Household and membership model invariants: [#2](https://github.com/judricomo/homework_01/issues/2)
- Chore/assignment HTTP endpoints, authentication, API permissions, and claim responses: [#9](https://github.com/judricomo/homework_01/issues/9)
- Completion submission, approval, rejection, and assignment lifecycle after completion: [#10](https://github.com/judricomo/homework_01/issues/10)
- Pending/rejected completion state behavior and focused tests proving those states do not advance rotation or award completion-related credit: [#10](https://github.com/judricomo/homework_01/issues/10)
- Points ledger, streak tracking, and milestone badges: [#11](https://github.com/judricomo/homework_01/issues/11), [#12](https://github.com/judricomo/homework_01/issues/12), and [#13](https://github.com/judricomo/homework_01/issues/13)
- Manual assignment and claim-mode behavior: [#6](https://github.com/judricomo/homework_01/issues/6)
Constraints:
- Use the household membership boundary from [#2](https://github.com/judricomo/homework_01/issues/2) and the rotation assignment invariants from [#6](https://github.com/judricomo/homework_01/issues/6); every read and write must remain household-scoped.
- Keep rotation ordering, cursor updates, and idempotency in a transaction-safe chores domain service or task module. Do not add an external scheduler, HTTP endpoint, or recurrence engine in this task.
- Treat the due occurrence identifier as the idempotency key; do not infer a new occurrence or silently overwrite an existing assignment.
- Make ordering and eligibility rules explicit and deterministic, and preserve assignment history needed by completion and leaderboard follow-ups.

## 8. Add fixed and flexible recurrence rules
Status: Groomed in [#8](https://github.com/judricomo/homework_01/issues/8)
Goal: Calculate the next due local date for a chore from its configured recurrence rule and anchor date. The result must be deterministic, timezone-aware, and based on approved completion history only where the flexible rule requires it.
Description: Support fixed/calendar recurrence (daily, weekly, every N days, or selected weekdays) and flexible recurrence (N days after the most recent approved completion). Use the project timezone and explicit local-date semantics so engineers and API consumers get the same answer at date boundaries and daylight-saving transitions.
Acceptance criteria:
- [x] A chore represents exactly one recurrence mode: fixed/calendar or flexible; fixed rules represent daily, weekly, every-N-days, or selected weekdays, and flexible rules store a positive whole-day interval.
- [x] Every chore has an explicit local-date anchor; when there is no prior approved completion, the first due date is the anchor date for both fixed and flexible rules.
- [x] Daily recurrence advances one local calendar day, weekly recurrence advances seven local calendar days, and every-N-days recurrence advances exactly N local calendar days from the prior due occurrence.
- [x] Selected-weekday recurrence stores at least one valid weekday, returns the next selected weekday after the prior due date, and wraps across the end of the week.
- [x] Flexible recurrence returns the anchor date when there is no approved completion and otherwise returns the most recent approved completion's local date plus the configured interval.
- [x] Pending and rejected completions, completions from another chore or household, and completions lacking approval do not affect a flexible next due date.
- [x] Missing, zero, negative, fractional, non-integer, or contradictory recurrence values are rejected before persistence; selected weekdays reject invalid values and an empty set.
- [x] A recurrence calculation is deterministic for the same rule, anchor, completion history, and project timezone, including at local midnight and across daylight-saving transitions.
- [x] Due-date calculations use local calendar dates rather than elapsed 24-hour durations; the documented project timezone is applied consistently when converting completion timestamps.
- [x] Focused tests cover every recurrence mode, first due date, weekday wraparound, approved versus pending/rejected history, invalid values, date boundaries, and daylight-saving transitions.

Out of scope:
- Rotation assignment advancement: [#7](https://github.com/judricomo/homework_01/issues/7).
- Chore CRUD, recurrence configuration endpoints, and member-visible due/overdue responses: [#9](https://github.com/judricomo/homework_01/issues/9).
- Completion submission, approval/rejection transitions, and the definition of an approved completion record: [#10](https://github.com/judricomo/homework_01/issues/10).
- In-app due/overdue notification surfaces and their treatment of pending completions: [#15](https://github.com/judricomo/homework_01/issues/15).

Constraints:
- Keep recurrence data and calculations in the chores domain and use timezone-aware values with the project's configured timezone.
- Do not infer due dates from unapproved activity, and do not award points, update streaks, or trigger badges here.
- Treat a local calendar date as the recurrence unit; do not define recurrence by elapsed seconds or silently use the server's system timezone.
- Keep this task independent of HTTP/API, assignment, completion-review, notification, and gamification workflows; integrate through their documented follow-up contracts.

## 9. Implement chore listing and assignment APIs
Status: Groomed in [#9](https://github.com/judricomo/homework_01/issues/9)
Goal: Give household members a secure, household-scoped API for managing and viewing chore occurrences.
Description: Expose Django REST Framework endpoints for administrator chore CRUD and member work queues. Members may see only their assigned chores or currently claimable claim-pool occurrences; responses include assignment, recurrence, difficulty, derived points, and local due-state context. Claiming must remain transaction-safe and all visibility must be explicitly scoped to the member's household.
Acceptance criteria:
- [ ] Authenticated administrators can create, retrieve, update, list, and delete only chores in their household; requests enforce the Chore model's name, difficulty, derived-point, assignment-mode, and recurrence validation.
- [ ] Authenticated regular members can list and retrieve only current occurrences assigned to them or currently available in their household's claim pool; unrelated manual, rotation, and claimed occurrences are excluded.
- [ ] Responses expose a stable documented shape containing chore identity/name, difficulty, derived points, assignment mode, current assignee or claimability, recurrence summary, occurrence/due local date, and a documented due state.
- [ ] Claim-pool results contain only currently available occurrences and exclude already claimed, submitted, approved, or otherwise completed occurrences; concurrent claims cannot assign one occurrence to two members.
- [ ] Assignment and recurrence filters accept only documented values, reject malformed or contradictory combinations with field-level client errors, and do not broaden member visibility.
- [ ] Unknown identifiers, inactive/unavailable claim-pool items, non-member access, and member attempts at administrator-only operations return documented errors without revealing another household's object.
- [ ] List endpoints implement deterministic ordering, pagination or another explicit bounded-result rule, and a documented empty response shape.
- [ ] Due-state calculations use the recurrence service's project-timezone local-date semantics, including date-boundary and daylight-saving cases; unapproved or rejected activity does not advance recurrence or mark an occurrence completed.
- [ ] Focused API tests cover administrator CRUD and validation, member visibility for manual/rotation/claim modes, claim availability and duplicate/concurrent handling, filters and pagination, due-state variants, invalid identifiers, permissions, and household isolation.

Out of scope:
- Token authentication and token issuance: [#3](https://github.com/judricomo/homework_01/issues/3).
- Household/membership models and role-management behavior: [#2](https://github.com/judricomo/homework_01/issues/2) and [#4](https://github.com/judricomo/homework_01/issues/4).
- Chore/difficulty models: [#5](https://github.com/judricomo/homework_01/issues/5).
- Assignment-mode models, manual assignment rules, and rotation scheduling: [#6](https://github.com/judricomo/homework_01/issues/6) and [#7](https://github.com/judricomo/homework_01/issues/7).
- Recurrence calculation: [#8](https://github.com/judricomo/homework_01/issues/8).
- Completion submission and approval/rejection transitions: [#10](https://github.com/judricomo/homework_01/issues/10).
- Dedicated due/overdue notification surfaces: [#15](https://github.com/judricomo/homework_01/issues/15).
- Points, streaks, badges, leaderboards, frontend views, and API-wide documentation: [#11](https://github.com/judricomo/homework_01/issues/11), [#12](https://github.com/judricomo/homework_01/issues/12), [#13](https://github.com/judricomo/homework_01/issues/13), [#14](https://github.com/judricomo/homework_01/issues/14), [#18](https://github.com/judricomo/homework_01/issues/18), and [#16](https://github.com/judricomo/homework_01/issues/16).

Constraints:
- Use Django REST Framework serializers, viewsets/routes, and reusable permission classes; keep household-scoped querysets explicit on every read and write path.
- Consume the domain contracts from [#5](https://github.com/judricomo/homework_01/issues/5)–[#8](https://github.com/judricomo/homework_01/issues/8) and [#10](https://github.com/judricomo/homework_01/issues/10) rather than duplicating point, assignment, recurrence, or approval rules.
- Keep claim operations transaction-safe and idempotent under concurrent requests; never expose or mutate another household's data through IDs, filters, ordering, or errors.
- Keep the API frontend-agnostic and document routes, methods, fields, status codes, error shapes, ordering, pagination, and due-state definitions in [#16](https://github.com/judricomo/homework_01/issues/16).
- Do not add multi-tenancy, self-service signup, external notifications, photo verification, custom badges, or per-chore streaks.

## 10. Implement completion submission and verification
Status: Groomed in [#10](https://github.com/judricomo/homework_01/issues/10)
Goal: Require approval before a chore earns credit.
Description: Create Completion records and endpoints for members to report chores as done. Add pending, approved, and rejected states, require another household member to review a completion, and prevent self-approval.
Acceptance criteria:
- [ ] An eligible member can submit one pending completion for a chore occurrence.
- [ ] Completion records identify member, chore, occurrence, submission time, and state.
- [ ] Another household member can approve or reject; the submitter cannot review their own completion.
- [ ] Duplicate active submissions are rejected.
- [ ] Approved/rejected terminal states cannot be changed by repeated review requests.
- [ ] Pending and rejected completions trigger no gamification effects.
- [ ] Focused tests cover submission, review, state transitions, duplicates, and permissions.

## 11. Build the points ledger and scoring updates
Status: Groomed in [#11](https://github.com/judricomo/homework_01/issues/11)
Goal: Record immutable point awards for approved completions.
Description: Add a PointsLedger model and transaction-safe logic that awards the chore's difficulty points exactly once when a completion is approved. Preserve historical entries so totals remain auditable.
Acceptance criteria:
- [ ] Approval creates one ledger entry linked to member, chore, completion, points, and award time.
- [ ] The entry preserves the difficulty point value used at approval.
- [ ] Pending and rejected completions create no entries.
- [ ] Repeated awards are idempotent and ledger entries cannot be edited normally.
- [ ] All-time totals equal the sum of ledger history.
- [ ] Focused tests cover values, idempotency, immutability, totals, and rollback.

## 12. Implement streak tracking
Status: Groomed in [#12](https://github.com/judricomo/homework_01/issues/12)
Goal: Track each member's consecutive days with approved activity.
Description: Calculate per-person daily streaks from approved completions only. Update streak state when a completion is approved and define behavior for same-day activity, missed days, and timezone boundaries.
Acceptance criteria:
- [ ] An approved completion counts as activity for one local calendar day.
- [ ] Multiple approvals on one day do not inflate the streak.
- [ ] Consecutive activity days extend the current streak.
- [ ] A missed day resets the current streak and preserves the best streak.
- [ ] Pending and rejected completions never affect streaks.
- [ ] Reprocessing approval is idempotent.
- [ ] Focused tests cover same-day, consecutive-day, missed-day, replay, and timezone cases.

## 13. Define and award milestone badges
Status: Groomed in [#13](https://github.com/judricomo/homework_01/issues/13)
Goal: Automatically award the fixed v1 badge set.
Description: Define the predefined badge catalog and award member badges when approved activity crosses configured thresholds. Badge awards must be durable and idempotent.
Acceptance criteria:
- [ ] The fixed catalog includes 7-day streak, 100 points, and 50 approved chores milestones.
- [ ] Each badge has a stable identifier, name, description, and threshold rule.
- [ ] Awards occur only after approved activity updates the relevant metric.
- [ ] Pending and rejected activity never awards badges.
- [ ] Each member receives each badge at most once and awards remain durable.
- [ ] Focused tests cover below, at, and above threshold plus repeated checks.

## 14. Add all-time and current-period leaderboards
Status: Groomed in [#14](https://github.com/judricomo/homework_01/issues/14)
Goal: Expose historical and current-period rankings by approved points.
Description: Build leaderboard endpoints for all-time totals and a current week or month view. Preserve historical ledger data across period boundaries and document the selected period and timezone rules.
Acceptance criteria:
- [ ] All-time rankings sum approved ledger points for household members.
- [ ] Current-period rankings include only points inside the documented calendar period.
- [ ] The period type, boundaries, and timezone are documented and exposed.
- [ ] Pending and rejected completions are excluded.
- [ ] Ties use stable documented ordering.
- [ ] Period boundaries do not delete or reset all-time ledger history.
- [ ] Focused tests cover boundaries, ties, zero points, and household isolation.
Follow-ups:
- Custom reporting periods and date ranges: [#19](https://github.com/judricomo/homework_01/issues/19)
- Frontend leaderboard views: [#18](https://github.com/judricomo/homework_01/issues/18)

## 15. Add in-app due and overdue notification surfaces
Status: Groomed in [#15](https://github.com/judricomo/homework_01/issues/15)
Goal: Show members which chores need attention without external notifications.
Description: Provide API or dashboard data that identifies chores due soon and overdue for the requesting member. Keep v1 notifications entirely in-app with no email, push, or chat integration.
Acceptance criteria:
- [ ] An authenticated member can retrieve their due chores.
- [ ] Overdue results use the same recurrence and timezone rules as chore listings.
- [ ] Responses include chore, assignment, due-state, and recurrence context.
- [ ] Approved, pending, and rejected occurrences follow documented due-state behavior.
- [ ] Members cannot see another household's due/overdue data.
- [ ] Empty results have a documented successful response shape.
- [ ] No external notification side effect is introduced.
- [ ] Focused API tests cover due, overdue, completion states, empty, and inaccessible cases.
Follow-up:
- Frontend dashboard rendering: [#18](https://github.com/judricomo/homework_01/issues/18)

## 16. Document API behavior and v1 scope
Status: Groomed in [#16](https://github.com/judricomo/homework_01/issues/16)
Goal: Make the implemented API understandable to contributors and frontend developers.
Description: Document authentication, endpoints, request and response shapes, roles, state transitions, recurrence rules, scoring values, badge thresholds, and leaderboard period rules. Record explicit v1 exclusions so later work does not silently expand scope.
Acceptance criteria:
- [ ] Authentication, endpoints, fields, permissions, and error responses are documented.
- [ ] Household scoping and administrator/member permissions are documented.
- [ ] Difficulty points, assignments, recurrence, due states, and completion transitions are documented.
- [ ] Approval effects, badge thresholds, leaderboard periods, and timezone behavior are documented.
- [ ] Examples include authenticated success and validation-error responses.
- [ ] Documentation matches implemented behavior and identifies unresolved decisions.
- [ ] v1 exclusions link to relevant follow-up issues where applicable.
Follow-up:
- Frontend dashboard and leaderboard documentation consumer: [#18](https://github.com/judricomo/homework_01/issues/18)
