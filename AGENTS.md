# Mis-Clear — Agent Guidelines

Python 3.11 desktop app (tkinter, stdlib-only) that removes traces of unwanted
websites (history, cookies, autofill, cache) from Chrome/Edge/Brave/Opera/
Firefox profiles, using custom keywords + a StevenBlack adult-domain blocklist.

## Core Rules

- If a task matches a skill, invoke it with the `skill` tool before acting.
- Skills are located in `.opencode/skills/<skill-name>/SKILL.md`.
- Follow the skill workflow strictly; do not partially apply it.
- Never skip required steps (spec, plan, test) when a skill demands them.

## Repository Conventions

- **Dependencies:** Python stdlib only. Any local vendor libs go under `lib/`
  (gitignored). Never commit secrets or big runtime files.
- **Commits:** every change in its own commit, pushed to `origin/main`.
- **Tracking:** update `SESSION_STATE.md` (gitignored) after each change; it
  keeps commit log, bug/fix log, and known limitations.
- **Tests:** everything is proven by tests.
  - Unit: `python tests\test_cleaners.py`
  - Integration: `python tests\test_integration.py`
- **Runtime data (gitignored):** `blocklist.txt` (StevenBlack download),
  `config.json` (user settings).

## Intent → Skill Mapping

Map user intent to the matching skill automatically:

- Focused discovery of what the user really wants → `spec-driven-development`
- Spec / new feature / significant change → `spec-driven-development`
- Bug / hang / crash / unexpected behavior → `debugging-and-error-recovery`
- Writing or extending tests → `test-driven-development`
- Module boundaries / public functions (cleaner/engine API) → `api-and-interface-design`
- Code that works but needs review before merge → `code-review-and-quality`
- Refactoring / simplification → `code-simplification`
- Security review (handles browser DBs / cookies) → `security-and-hardening`
- Slow operations (cache walk, scan time) → `performance-optimization`
- Every commit/shipping step → `git-workflow-and-versioning`
- Deciding which skill applies at all → `using-agent-skills`

## Execution Model

For every request:

1. Determine if any skill applies (even a small chance).
2. Load the skill with the `skill` tool.
3. Follow the skill workflow exactly, including its verification gates.
4. Only proceed to implementation once required steps are complete.