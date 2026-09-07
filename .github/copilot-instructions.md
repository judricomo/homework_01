# Copilot Instructions

## Project overview

This repository is an API-first Django project for a household chores tool. The backend is frontend-agnostic and is expected to expose Django REST Framework APIs; the current baseline still contains only the generated `config` project, the registered `chores` app, the Django admin route, and a minimal project-loading test.

The planned domain is documented in `_docs/plan.md`, and the implementation sequence is tracked in `_docs/backlog.md`. The v1 scope is one household with administrator and regular-member roles, chore assignment and recurrence, pending completion approval, points, streaks, badges, leaderboards, and in-app due/overdue surfaces. Do not introduce multi-tenancy, self-service signup, photo verification, external notifications, custom badges, or per-chore streaks without an explicit scope change.

## Environment and commands

- Python requirement: 3.12 or newer, pinned locally by `.python-version`.
- Dependency manager: `uv`; `pyproject.toml` and `uv.lock` are the source of truth.
- Set up or refresh the environment:

  ```bash
  uv sync
  source .venv/bin/activate
  ```

- Run database migrations and the development server:

  ```bash
  python manage.py migrate
  python manage.py runserver
  ```

- Run Django checks:

  ```bash
  python manage.py check
  ```

- Run the full test suite:

  ```bash
  python manage.py test
  ```

- Run a single test or test class:

  ```bash
  python manage.py test chores.tests.ProjectLoadsTest
  python manage.py test chores.tests.ProjectLoadsTest.test_admin_login_page_loads
  ```

- No lint command or lint configuration is currently defined. Do not assume a formatter or linter is available; use Django checks and the test suite unless a tool is added deliberately.

## Architecture

- `manage.py` is the command-line entry point and uses `config.settings`.
- `config/settings.py` owns installed apps, middleware, SQLite database configuration, timezone settings, and DRF registration.
- `config/urls.py` is the project-level URL router. It currently exposes only the Django admin at `/admin/`; API routes should be wired here through app URL modules as the API is implemented.
- `chores/` is the domain app. Its models, views, tests, migrations, and admin integration belong here; it is already registered in `INSTALLED_APPS`.
- `rest_framework` is installed and registered, but token authentication and API endpoints are not configured yet. Implement those as a separate task rather than assuming authentication already exists.
- SQLite is the current development database. The database file is ignored and migrations should be committed when models are introduced.

## Repository conventions

- Use `uv add` to change runtime dependencies and keep `uv.lock` synchronized with `pyproject.toml`; use `uv sync` after dependency changes.
- Use Django migrations for schema changes and keep migration files in `chores/migrations/`.
- Keep household scoping explicit in domain queries and API behavior. The product is single-household for v1, but models and permissions should still prevent access to unrelated household data if that boundary is represented.
- Keep approval as the source of truth for gamification: pending or rejected completions must not award points, update streaks, or trigger badges.
- Preserve the distinction between administrator capabilities and regular-member capabilities described in `_docs/plan.md`.
- Add focused Django tests alongside the app behavior. Existing tests are in `chores/tests.py`; use Django’s test runner and target individual test paths when iterating.
- Keep implementation work aligned with one backlog issue at a time and update `_docs/backlog.md` when a task’s acceptance criteria are completed.

## Task workflow

- Treat GitHub issues as the unit of work and implement one issue at a time.
- Read the issue's acceptance criteria before starting and before closing the task.
- Groom tasks before implementation using `_docs/pm.md` and the template in `_docs/task-template.md`.
- Keep acceptance criteria checkable and document any moved scope as a linked follow-up issue.
- After implementation, QA must check the running code against every acceptance criterion, run and report tests, and comment a `PASS` or `FAIL` verdict without changing code; follow `_docs/team/qa-engineer.md`.
- Commit regularly and keep task-process guidance in `_docs/process.md`.
