# Household Chores Tool Backlog

## 1. Set up an empty Django project with a passing test
Status: Completed in [#1](https://github.com/judricomo/homework_01/issues/1) and PR [#17](https://github.com/judricomo/homework_01/pull/17)
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
Status: Completed in [#2](https://github.com/judricomo/homework_01/issues/2) ([QA: PASS](https://github.com/judricomo/homework_01/issues/2#issuecomment-5563622890))
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
Status: Completed in [#3](https://github.com/judricomo/homework_01/issues/3) ([QA: PASS](https://github.com/judricomo/homework_01/issues/3#issuecomment-5563824827))
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
Status: Completed in [#4](https://github.com/judricomo/homework_01/issues/4) ([QA: PASS](https://github.com/judricomo/homework_01/issues/4#issuecomment-5563853771))
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
Status: Completed in [#5](https://github.com/judricomo/homework_01/issues/5) ([QA: PASS](https://github.com/judricomo/homework_01/issues/5#issuecomment-5563881911))
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
Status: Completed in [#6](https://github.com/judricomo/homework_01/issues/6) ([QA: PASS](https://github.com/judricomo/homework_01/issues/6#issuecomment-5563932494))
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
Status: Completed in [#7](https://github.com/judricomo/homework_01/issues/7) ([QA: PASS](https://github.com/judricomo/homework_01/issues/7#issuecomment-5563966452))
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
Status: Completed in [#8](https://github.com/judricomo/homework_01/issues/8) ([QA: PASS](https://github.com/judricomo/homework_01/issues/8#issuecomment-5564000278))
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
Status: Completed in [#9](https://github.com/judricomo/homework_01/issues/9) ([QA: PASS](https://github.com/judricomo/homework_01/issues/9#issuecomment-5564097600))
Goal: Give household members a secure, household-scoped API for managing chores and viewing currently assignable work.
Description: Expose Django REST Framework endpoints for administrator chore CRUD and member work queues. Members may see only their assigned chores or currently claimable claim-pool chores; responses include assignment, recurrence, difficulty, derived points, occurrence identity, and local due-state context. Claiming must remain transaction-safe and all visibility must be explicitly scoped to the member's household. This issue consumes assignment and recurrence domain contracts; it does not define completion lifecycle or recurrence-calendar calculation.
Acceptance criteria:
- [ ] Authenticated administrators can create, retrieve, update, list, and delete only chores in their household; requests enforce the Chore model's name, difficulty, derived-point, assignment-mode, and recurrence validation.
- [ ] Authenticated regular members can list and retrieve only their active manual or rotation assignments and currently available claim-pool chores in their household; unrelated chores and claim-pool chores already assigned to another member are excluded.
- [ ] Responses expose a stable shape containing chore identity/name, difficulty, derived points, assignment mode, current assignee or claimability, recurrence summary, occurrence identifier when assigned, due local date, and exactly one current due state: `upcoming`, `due`, or `overdue`.
- [ ] Claim-pool results contain only chores currently available under the assignment contract; duplicate or concurrent claims cannot assign one chore occurrence to two members.
- [ ] List endpoints explicitly support the documented filters `assignment_mode=manual|rotation|claim`, `recurrence_mode=fixed|flexible`, and `due_state=upcoming|due|overdue` (where applicable); unknown values and contradictory combinations return field-level client errors and never broaden member visibility.
- [ ] Unknown chore or occurrence identifiers, inactive/unavailable claim-pool items, non-member access, and member attempts at administrator-only operations return documented errors without revealing another household's object.
- [ ] List endpoints implement deterministic ordering, pagination or another explicit bounded-result rule, and a documented empty response shape.
- [ ] The API passes through the recurrence service's returned due date and labels only the currently possible `upcoming`, `due`, or `overdue` states; recurrence calendar arithmetic, project-timezone boundary/DST correctness, and next-date rules remain owned by [#8](https://github.com/judricomo/homework_01/issues/8).
- [ ] Focused API tests cover administrator CRUD and validation, member visibility for manual/rotation/claim modes, claim availability and duplicate/concurrent handling, documented filters and pagination, the three available due states, invalid identifiers, permissions, and household isolation.

Out of scope:
- Token authentication and token issuance: [#3](https://github.com/judricomo/homework_01/issues/3).
- Household/membership models and role-management behavior: [#2](https://github.com/judricomo/homework_01/issues/2) and [#4](https://github.com/judricomo/homework_01/issues/4).
- Chore/difficulty models: [#5](https://github.com/judricomo/homework_01/issues/5).
- Assignment-mode models, manual assignment rules, and rotation scheduling: [#6](https://github.com/judricomo/homework_01/issues/6) and [#7](https://github.com/judricomo/homework_01/issues/7).
- Recurrence calendar arithmetic, occurrence generation, timezone boundary/DST correctness, and flexible next-date semantics: [#8](https://github.com/judricomo/homework_01/issues/8).
- Completion submission, pending/review/approved/rejected transitions, completed-occurrence behavior, and completion effects: [#10](https://github.com/judricomo/homework_01/issues/10).
- Dedicated due/overdue notification surfaces: [#15](https://github.com/judricomo/homework_01/issues/15).
- Points, streaks, badges, leaderboards, frontend views, and API-wide documentation: [#11](https://github.com/judricomo/homework_01/issues/11), [#12](https://github.com/judricomo/homework_01/issues/12), [#13](https://github.com/judricomo/homework_01/issues/13), [#14](https://github.com/judricomo/homework_01/issues/14), [#18](https://github.com/judricomo/homework_01/issues/18), and [#16](https://github.com/judricomo/homework_01/issues/16).

Constraints:
- Use Django REST Framework serializers, viewsets/routes, and reusable permission classes; keep household-scoped querysets explicit on every read and write path.
- Consume the domain contracts from [#5](https://github.com/judricomo/homework_01/issues/5)–[#8](https://github.com/judricomo/homework_01/issues/8) and [#10](https://github.com/judricomo/homework_01/issues/10) rather than duplicating point, assignment, recurrence, or approval rules; do not implement completion state transitions or their effects here.
- Keep claim operations transaction-safe and idempotent under concurrent requests; never expose or mutate another household's data through IDs, filters, ordering, or errors.
- Keep the API frontend-agnostic and document routes, methods, fields, status codes, error shapes, ordering, pagination, and due-state definitions in [#16](https://github.com/judricomo/homework_01/issues/16).
- Do not add multi-tenancy, self-service signup, external notifications, photo verification, custom badges, or per-chore streaks.

## 10. Implement completion submission and verification
Status: Completed in [#10](https://github.com/judricomo/homework_01/issues/10) ([QA: PASS](https://github.com/judricomo/homework_01/issues/10#issuecomment-5564172642))
Goal: Require approval before a chore earns credit.
Description: Let an active, eligible household member submit one self-reported completion for a stable chore occurrence, then let a different household member approve or reject it. Preserve immutable review history, enforce household and assignment boundaries, and make approval the only state consumable by gamification follow-ups.
Acceptance criteria:
- [ ] An authenticated, active household member can submit exactly one completion for a valid occurrence to which they are eligible; it starts as `pending`.
- [ ] A completion records submitting membership, chore, stable occurrence identifier, submitted-at timestamp, review state, and immutable reviewer/reviewed-at data when finalized.
- [ ] Missing, unknown, already-finalized, inactive, cross-household, and ineligible occurrences are rejected without side effects.
- [ ] Repeating a submission for the same member, chore, and occurrence is rejected (or returns the existing pending record under one documented idempotency response); no second active completion is created.
- [ ] A different active member of the same household can approve or reject a pending completion; self-review, unauthenticated review, and unauthorized review are denied.
- [ ] Server-side transitions are limited to `pending -> approved` and `pending -> rejected`, are transaction-safe, and are protected against concurrent/replayed review.
- [ ] Approved and rejected states are terminal; repeated or contradictory review requests are side-effect-free and return documented errors.
- [ ] Approval does not implement points, streaks, badges, or leaderboards, but exposes the state/linkage contracts required by [#11](https://github.com/judricomo/homework_01/issues/11), [#12](https://github.com/judricomo/homework_01/issues/12), and [#13](https://github.com/judricomo/homework_01/issues/13); pending/rejected records are ignored by those consumers.
- [ ] An approved occurrence cannot be completed again; assignment clearing/recreation, if required, is explicit and never overwrites completion history.
- [ ] Rejected occurrences remain historical; any retry policy is documented and uses a new completion rather than mutating the rejected record.
- [ ] Focused tests cover valid submission, eligibility and household isolation, inactive members, duplicate submission, pending retrieval, approval, rejection, self-review denial, permissions, concurrency/replay, terminal states, assignment lifecycle, and absent gamification side effects.
Out of scope:
- Point ledger creation and award idempotency: [#11](https://github.com/judricomo/homework_01/issues/11).
- Streak calculations: [#12](https://github.com/judricomo/homework_01/issues/12).
- Badge definitions and awards: [#13](https://github.com/judricomo/homework_01/issues/13).
- Leaderboard aggregation: [#14](https://github.com/judricomo/homework_01/issues/14).
- Chore/assignment CRUD and member work-queue APIs beyond minimum completion/review routes: [#9](https://github.com/judricomo/homework_01/issues/9).
- Dedicated due/overdue surfaces: [#15](https://github.com/judricomo/homework_01/issues/15).
- Frontend screens, external notifications, photo verification, custom badges, per-chore streaks, self-service signup, and multi-tenancy.
Constraints:
- Use the household and active-membership boundary from [#2](https://github.com/judricomo/homework_01/issues/2); scope every completion read and write through the authenticated member's household.
- Consume chore, assignment, occurrence, recurrence, and eligibility contracts from [#5](https://github.com/judricomo/homework_01/issues/5)–[#9](https://github.com/judricomo/homework_01/issues/9); do not duplicate recurrence, claim, or rotation rules.
- Use explicit states, database uniqueness where supported, and transactions/locking for submission and review races.
- Preserve immutable review history and never silently overwrite completions, occurrences, assignments, or claims.
- Do not accept or store photos or other proof artifacts; v1 is self-reported.
- Document routes, fields, status codes, transition errors, retry/idempotency behavior, and rejected-occurrence policy in [#16](https://github.com/judricomo/homework_01/issues/16).

## 11. Build the points ledger and scoring updates
Status: Completed in [#11](https://github.com/judricomo/homework_01/issues/11) ([QA: PASS](https://github.com/judricomo/homework_01/issues/11#issuecomment-5564251523))
Goal: Record an immutable, auditable point award for each approved chore completion, exactly once. A member's score must be reproducible from the ledger, while preserving the point value and award timestamp that applied when approval was processed.
Description: Add a dedicated PointsLedger model and transaction-safe, reusable award service. Consume the approved-completion contract from [#10](https://github.com/judricomo/homework_01/issues/10), snapshot the chore's persisted difficulty-derived points at award time, and make replayed or concurrent processing idempotent. Preserve ledger history so totals remain auditable and household-scoped.
Acceptance criteria:
- [ ] Processing an approved completion creates exactly one ledger entry containing the completion, submitting member, chore, awarded points, and a timezone-aware award timestamp.
- [ ] The awarded points are copied from the chore's persisted difficulty-derived point value at award time; changing the chore's difficulty or configured points later does not change the historical ledger entry.
- [ ] A pending or rejected completion is refused by the award operation and creates no ledger entry; an unknown, missing, cross-household, or otherwise invalid completion is also side-effect free.
- [ ] An approved completion can be processed repeatedly or concurrently without creating more than one ledger entry; database-backed uniqueness protects the completion-to-award relationship, and retries return or reuse the original award.
- [ ] A ledger entry is append-only through normal application behavior: no endpoint, service, admin action, or model save path can change its member, chore, completion, points, or award timestamp, and deletion is prevented or explicitly handled without rewriting history.
- [ ] All-time member totals equal the sum of that member's ledger entries, include zero for a member with no awards, and exclude pending or rejected completions.
- [ ] Ledger reads and totals are household-scoped; a member or request cannot retrieve, aggregate, or award points for another household through an object ID or filter.
- [ ] If approval-effect processing or ledger persistence fails, the transaction leaves no partial award and does not leave completion/award state inconsistent; a safe retry can complete the award.
- [ ] Focused tests cover approved awards, point snapshots after chore edits, pending/rejected/invalid exclusions, duplicate and concurrent retries, append-only protections, totals including zero, household isolation, and rollback behavior.
Out of scope:
- Completion submission, review-state transitions, and the approval event contract that triggers this award: [#10](https://github.com/judricomo/homework_01/issues/10)
- Per-member daily streak calculation and updates: [#12](https://github.com/judricomo/homework_01/issues/12)
- Fixed milestone badge definitions and awards: [#13](https://github.com/judricomo/homework_01/issues/13)
- All-time/current-period leaderboard queries and ranking rules: [#14](https://github.com/judricomo/homework_01/issues/14)
- API-wide route, response, authentication, and scoring documentation: [#16](https://github.com/judricomo/homework_01/issues/16)
- Frontend score, leaderboard, or history views: [#18](https://github.com/judricomo/homework_01/issues/18)
Constraints:
- Use a dedicated ledger model plus a transaction-safe, reusable award service; do not derive totals from mutable completion or chore fields.
- Consume the approved-completion and chore point contracts from [#5](https://github.com/judricomo/homework_01/issues/5) and [#10](https://github.com/judricomo/homework_01/issues/10); do not reimplement completion state transitions here.
- Enforce one award per completion with a database constraint and handle replay/concurrency safely with Django transactions and locking where supported.
- Preserve historical point values and timestamps; use Django timezone-aware timestamps and protect ledger history with restrictive relationships or an equivalent explicit deletion policy.
- Keep household scoping explicit on every ledger read, total, and award path. Limit changes to the chores domain, migrations, focused tests, and any required integration wiring; do not add unrelated gamification or frontend behavior.

## 12. Implement streak tracking
Status: Completed in [#12](https://github.com/judricomo/homework_01/issues/12) ([QA: PASS](https://github.com/judricomo/homework_01/issues/12#issuecomment-5564297356))
Goal: Track one household member's daily approved-completion activity as a durable current streak and historical best streak.
Description: Derive per-person daily streaks from approved completions only. Use the completion's submitted timestamp converted to the configured project timezone as the activity date, preserve activity-day evidence, and make recalculation safe for duplicate, concurrent, and out-of-order approval effects.
Acceptance criteria:
- [x] Each member has one streak state with current length, best length, and most recent activity date; no approved activity means current and best are zero with no date.
- [x] An approved completion contributes one activity date from `submitted_at` in the configured project timezone; approval time does not select the date.
- [x] Multiple approved completions on one local date count once, while consecutive dates extend the current run.
- [x] A gap resets current streak to the run ending on the latest activity date and preserves the historical best.
- [x] Older or out-of-order approvals produce the same state as chronological processing and do not discard activity history.
- [x] Pending, rejected, invalid, missing, or cross-household completions have no streak side effects.
- [x] Replayed, retried, or concurrent approval effects are idempotent and cannot inflate or corrupt member-day or streak state.
- [x] Timezone-aware conversion handles local-midnight and daylight-saving boundaries using the project timezone.
- [x] Every read and write is household/member scoped; cross-household IDs cannot access or mutate streaks.
- [x] Streak state and activity-day evidence update atomically, with safe retry after failure.
- [x] Focused tests cover no activity, first/same-day/consecutive activity, one- and multi-day gaps, best preservation, out-of-order approval, invalid states, replay/concurrency, isolation, and timezone/DST boundaries.
Out of scope:
- Completion submission, review transitions, approval-effect orchestration, and the immutable completion contract: [#10](https://github.com/judricomo/homework_01/issues/10)
- Point awards and the points ledger: [#11](https://github.com/judricomo/homework_01/issues/11)
- Per-chore or on-time streaks; expanded streak taxonomy: [#19](https://github.com/judricomo/homework_01/issues/19)
- Fixed milestone badge definitions and awards: [#13](https://github.com/judricomo/homework_01/issues/13)
- All-time/current-period leaderboard calculations: [#14](https://github.com/judricomo/homework_01/issues/14)
- API and gamification documentation: [#16](https://github.com/judricomo/homework_01/issues/16)
- Frontend streak displays and notifications: [#18](https://github.com/judricomo/homework_01/issues/18)
Constraints:
- Keep changes in the chores domain, migrations, focused tests, and required approval-effect integration.
- Use dedicated streak state plus database-enforced member/activity-date uniqueness (or an equivalent durable design); do not infer streaks from mutable points.
- Consume the approved-completion contract from [#10](https://github.com/judricomo/homework_01/issues/10) and configured project timezone; do not duplicate recurrence, assignment, or review rules.
- Use timezone-aware Django datetimes, transactions, and appropriate locking/constraint handling for safe retries and concurrency.
- Preserve household scoping and historical activity evidence; document deletion behavior rather than silently rewriting history.

Implementation:
- Added `MemberStreak` state and durable `MemberActivityDay` evidence with member/date uniqueness.
- Integrated approved completion review with atomic, timezone-aware streak updates and replay-safe recalculation.
- Added focused model tests for gaps, ordering, duplicates, invalid states, and midnight/DST boundaries.
- Streak and activity history cascade with membership/household deletion to preserve existing deletion semantics.

## 13. Define and award milestone badges
Status: Completed in [#13](https://github.com/judricomo/homework_01/issues/13) ([QA: PASS](https://github.com/judricomo/homework_01/issues/13#issuecomment-5564356682))
Goal: Define the fixed v1 badge catalog and automatically award each milestone badge to a household member when approved activity causes the qualifying metric to reach or exceed its threshold. Awards must be durable, household-scoped, and safe to repeat.
Description: Implement the three fixed v1 milestones—7 consecutive approved-activity days, 100 approved points, and 50 approved chore completions—using the durable points and streak contracts. Evaluate badges only after successful approval effects and preserve immutable award evidence.
Acceptance criteria:
- [x] The fixed catalog contains exactly these v1 milestones: a 7-consecutive-day approved-activity streak, 100 approved points, and 50 approved chore completions.
- [x] Each catalog entry has a stable, immutable identifier, display name, description, metric, integer threshold, and documented threshold semantics.
- [x] A 7-day streak badge is awarded only when the member's durable streak reaches 7 consecutive activity days; a gap resets the current streak and does not qualify until 7 new consecutive days are reached.
- [x] A 100-point badge is awarded only when the member's approved point total reaches at least 100; pending or rejected completions contribute zero points.
- [x] A 50-chores badge is awarded only when the member's count of approved chore completions reaches at least 50; each approved completion is counted once.
- [x] Badge evaluation runs after the approval transaction has successfully updated the relevant points, streak, or approved-completion metric, and an approval that is pending, rejected, or otherwise unsuccessful creates no award.
- [x] Values below each threshold produce no award, the exact threshold produces one award, and values above the threshold also produce one award.
- [x] Re-running evaluation for the same approval, replaying an already-processed approval, or concurrently evaluating the same member/badge never creates duplicate awards.
- [x] An award stores the member, fixed badge identifier, and award timestamp, remains queryable after later metric changes, and is not revoked when a completion is later edited or deleted under the project's history rules.
- [x] Badge evaluation is restricted to the completion's household/member scope and cannot award a badge to another household's member.
- [x] Focused tests cover every catalog entry, below/exactly/above thresholds, streak gaps, pending and rejected completions, duplicate/replayed evaluation, concurrent-safe uniqueness, and durable award records.
Out of scope:
- Admin-defined, user-defined, or otherwise configurable badge definitions; tracked in [#21](https://github.com/judricomo/homework_01/issues/21).
- Points calculation and the immutable points ledger; consume the approved-award contract from [#11](https://github.com/judricomo/homework_01/issues/11).
- Streak calculation and activity-day state; consume the approved-activity contract from [#12](https://github.com/judricomo/homework_01/issues/12).
- Completion submission, approval/rejection workflow, and review permissions; consume [#10](https://github.com/judricomo/homework_01/issues/10).
- Badge-management API/UI, badge presentation beyond the implementation's focused surface, and broader API documentation; follow up in [#16](https://github.com/judricomo/homework_01/issues/16) and [#18](https://github.com/judricomo/homework_01/issues/18).
- Per-chore, on-time, rolling-window, seasonal, or retroactive badge types; no follow-up is implied unless product scope is explicitly expanded.
Constraints:
- Keep the implementation in the `chores` domain, its migrations, focused tests, and the required approval-effect integration.
- Keep the catalog centrally defined and fixed for v1; do not add custom-badge CRUD or user-configurable thresholds.
- Derive badge metrics only from approved completions and the durable points/streak state; pending and rejected records must be ignored.
- Use timezone-aware Django datetimes, database constraints, transactions, and appropriate locking/constraint handling so retries and concurrent approvals are safe.
- Preserve household scoping and immutable historical award evidence; follow existing deletion semantics rather than silently rewriting award history.

## 14. Add all-time and current-period leaderboards
Status: Completed in [#14](https://github.com/judricomo/homework_01/issues/14) ([QA: PASS](https://github.com/judricomo/homework_01/issues/14#issuecomment-5564397462))
Goal: Expose household-scoped rankings that let members compare approved points earned all time and during the current calendar week.
Description: Build read-only leaderboard endpoints for all-time totals and the current calendar week. Include every active household member, including members with zero qualifying points, and return each member's total and deterministic rank. The current period is Monday 00:00:00 through the following Monday 00:00:00 in Django's configured project timezone, represented as a half-open interval; the response exposes the period type, timezone, start, and exclusive end. Preserve the immutable points ledger across period boundaries.
Acceptance criteria:
- [x] An authenticated household member can retrieve a read-only all-time leaderboard; each active household member appears once with the sum of that member's approved points, and a member with no approved points has total `0`.
- [x] An authenticated household member can retrieve a read-only current-period leaderboard; it uses the current calendar week in the project timezone, with an inclusive start at Monday 00:00:00 and an exclusive end at the next Monday 00:00:00.
- [x] The current-period total includes ledger awards whose timezone-aware award timestamp is within `[period_start, period_end)`; an award exactly at the start is included and one exactly at the exclusive end is excluded.
- [ ] Both views read only the immutable points ledger and exclude pending or rejected completions and any award outside the requesting member's household.
- [x] Both views include only active memberships at query time; deactivated members and members from another household cannot appear or be used to access results.
- [x] Each response identifies the view (`all_time` or `current_period`), project timezone, and for the current-period view the period type, inclusive start, exclusive end, and server-evaluated reference time.
- [x] Ranking is deterministic: rows sort by total points descending, then stable member identifier ascending; ranks use competition ranking (`1, 1, 3`) and repeated identical requests return the same order and ranks.
- [x] A period rollover changes only current-period totals and metadata; it does not delete, reset, mutate, or re-date all-time ledger entries.
- [ ] Unauthorized requests are rejected, and authenticated requests cannot obtain or infer another household's members or totals by changing an identifier or filter.
- [ ] Focused tests cover authentication, approved totals, zero-point members, pending/rejected exclusion, exact period boundaries, timezone/DST behavior, rollover/history preservation, ties and rank numbering, inactive members, and household isolation.
Out of scope:
- Custom reporting periods, user-selected date ranges, and alternate period types: [#19](https://github.com/judricomo/homework_01/issues/19)
- Frontend leaderboard screens, charts, and visualizations: [#18](https://github.com/judricomo/homework_01/issues/18)
- Creating or changing points awards and the immutable ledger: [#11](https://github.com/judricomo/homework_01/issues/11)
- Badge, streak, completion-review, and notification behavior: [#10](https://github.com/judricomo/homework_01/issues/10), [#12](https://github.com/judricomo/homework_01/issues/12), [#13](https://github.com/judricomo/homework_01/issues/13), and [#15](https://github.com/judricomo/homework_01/issues/15)
Constraints:
- Keep this task read-only and limited to the chores domain's leaderboard queries/endpoints, serializers, routes, focused tests, and required documentation.
- Use the household and active-membership boundary from [#2](https://github.com/judricomo/homework_01/issues/2) and the immutable approved-award contract from [#11](https://github.com/judricomo/homework_01/issues/11); do not derive scores from mutable completion or chore fields.
- Use Django's configured project timezone and timezone-aware datetimes; do not use rolling 7-day windows, client-local timezone, or a database reset job for v1.
- Do not accept arbitrary period parameters in these endpoints. Expose server-calculated period metadata and leave custom ranges to [#19](https://github.com/judricomo/homework_01/issues/19).
- Document endpoint paths, response fields, rank semantics, authorization, and error behavior in the API documentation follow-up [#16](https://github.com/judricomo/homework_01/issues/16).

## 15. Add in-app due and overdue notification surfaces
Status: Completed in [#15](https://github.com/judricomo/homework_01/issues/15) ([QA: PASS](https://github.com/judricomo/homework_01/issues/15#issuecomment-5564444350))
Goal: Give an authenticated household member a read-only in-app API surface that clearly separates their currently due chores from overdue chores. Use the same occurrence, recurrence, assignment, approval, and project-timezone contracts as the chore APIs; do not send notifications outside the application.
Acceptance criteria:
- [ ] An authenticated active household member can retrieve a successful response containing separate `due` and `overdue` collections for that member; the endpoint is read-only and does not mutate chores, assignments, occurrences, or completions.
- [ ] A current occurrence is in `due` when its local due date/time is reached and it has no approved completion; an occurrence whose due date/time has passed is in `overdue`; future occurrences are in neither collection. The boundary comparison is explicit and tested.
- [ ] Each returned item identifies the chore and occurrence, assigned member or claim-pool state, local due date/time, current due state, and recurrence context sufficient for a client to explain why it is due or overdue.
- [ ] Results use the recurrence service and the same configured project timezone as chore listing, including local-midnight and daylight-saving boundaries; this task does not recalculate recurrence independently.
- [ ] An approved completion removes that occurrence from the response and allows the recurrence contract to determine the next occurrence; pending completions leave the occurrence in its calculated due or overdue collection.
- [ ] A rejected completion leaves the occurrence in its calculated due or overdue collection, preserves the assignment lifecycle, and never causes points, streaks, badges, or recurrence advancement.
- [ ] Only occurrences currently assigned to the requesting member, or currently claimable under the documented claim-pool visibility contract, are returned; unassigned, inactive-member, unavailable-claim, and future occurrences are excluded without exposing another member's data.
- [ ] An authenticated member cannot retrieve another household's items, including by supplying chore or occurrence identifiers or filters; cross-household and unknown identifiers have the documented non-disclosing error behavior.
- [ ] Unauthenticated requests return HTTP 401, and authenticated users without an active household membership receive the documented authorization response without data.
- [ ] Empty `due` and `overdue` collections return the documented successful response shape, and ordering plus any result bound/pagination rule is deterministic and documented.
- [ ] Focused API tests cover due-at-boundary, overdue, future, approved, pending, rejected, recurrence/timezone boundary, assignment visibility, empty, authentication, authorization, identifier/filter, and cross-household cases.
- [ ] The implementation introduces no email, push, chat, webhook, scheduler, background delivery, or other external notification side effect; focused tests verify the surface is read-only.
Out of scope:
- Token authentication and token issuance: [#3](https://github.com/judricomo/homework_01/issues/3).
- Household and membership model invariants: [#2](https://github.com/judricomo/homework_01/issues/2).
- Assignment visibility, claim behavior, and recurrence calculation: [#6](https://github.com/judricomo/homework_01/issues/6), [#7](https://github.com/judricomo/homework_01/issues/7), and [#8](https://github.com/judricomo/homework_01/issues/8).
- Chore listing/assignment APIs and their general visibility contract: [#9](https://github.com/judricomo/homework_01/issues/9).
- Completion submission, approval/rejection transitions, and completion side effects: [#10](https://github.com/judricomo/homework_01/issues/10).
- API-wide route, field, status-code, and error documentation: [#16](https://github.com/judricomo/homework_01/issues/16).
- Frontend dashboard rendering: [#18](https://github.com/judricomo/homework_01/issues/18).
- Email, push, chat, and other external notification delivery are excluded by the v1 scope in [_docs/plan.md](_docs/plan.md); no follow-up is implied by this task.
Constraints:
- Keep the surface authenticated, household-scoped, read-only, and frontend-agnostic; wire it through the chores API without adding a notification provider or delivery worker.
- Consume the occurrence, assignment, recurrence, timezone, and completion contracts from [#6](https://github.com/judricomo/homework_01/issues/6)–[#10](https://github.com/judricomo/homework_01/issues/10); do not duplicate their state transitions or calendar arithmetic.
- Scope every queryset and identifier lookup through the requesting member's active household. Do not use client-supplied household IDs to authorize access.
- Keep response semantics stable and document the route, fields, ordering, empty shape, due-state boundary, and errors in [#16](https://github.com/judricomo/homework_01/issues/16).
- Do not introduce multi-tenancy, self-service signup, photo verification, custom badges, per-chore streaks, or external notifications.

## 16. Document API behavior and v1 scope
Status: Completed in [#16](https://github.com/judricomo/homework_01/issues/16) ([QA: PASS](https://github.com/judricomo/homework_01/issues/16#issuecomment-5564471530))
Documentation: [`_docs/api.md`](_docs/api.md)
Goal: Publish a source-of-truth contract for the implemented v1 API so frontend developers and contributors can use it without inferring undocumented behavior.
Description: Document authentication, every implemented endpoint, request/response/error shapes, role permissions, household isolation, state transitions, recurrence and due/overdue rules, scoring, streaks, badges, leaderboards, timezone boundaries, and explicit v1 exclusions. Verify examples and unresolved decisions against the running implementation rather than inventing behavior.
Acceptance criteria:
- [ ] Authentication, methods, fields, permissions, status codes, validation errors, and error shapes are documented for every implemented route.
- [ ] Household scoping, active-membership behavior, administrator/member permissions, and cross-household/non-disclosing identifier behavior are documented.
- [ ] Difficulty points, assignment modes and visibility, recurrence variants, occurrence advancement, due/overdue boundaries, and project timezone/DST behavior are documented.
- [ ] Completion submit/approve/reject transitions and duplicate/finalized/invalid-transition edge cases are documented, including immutable rejected history and terminal rejection.
- [ ] Approval is documented as the only source of points, streak, badge, and recurrence effects; pending/rejected effects are explicitly stated.
- [ ] Points ledger behavior, fixed badge identifiers/thresholds, idempotency/history, leaderboard period boundaries, ties/ranks, zero-activity members, and rollover preservation are documented.
- [ ] Due/overdue response shape, empty results, assignment/claim visibility, exact boundary behavior, and read-only/no-external-notification behavior are documented.
- [ ] Examples include an authenticated success response and verified authentication, authorization, validation, not-found, and conflict/state-transition errors.
- [ ] Documentation is checked against the implementation and tests; unresolved product decisions and any implementation/plan mismatch are identified rather than silently resolved.
- [ ] v1 exclusions link to relevant follow-ups: frontend consumer [#18](https://github.com/judricomo/homework_01/issues/18), custom periods [#19](https://github.com/judricomo/homework_01/issues/19), self-service signup/invites [#20](https://github.com/judricomo/homework_01/issues/20), and custom badges [#21](https://github.com/judricomo/homework_01/issues/21).
Follow-up:
- API documentation is the contract consumed by the frontend dashboard: [#18](https://github.com/judricomo/homework_01/issues/18)
- Custom leaderboard periods/date ranges remain deferred: [#19](https://github.com/judricomo/homework_01/issues/19)
- Self-service signup and invitation flows remain deferred: [#20](https://github.com/judricomo/homework_01/issues/20)
- Administrator-defined custom badges remain deferred: [#21](https://github.com/judricomo/homework_01/issues/21)
