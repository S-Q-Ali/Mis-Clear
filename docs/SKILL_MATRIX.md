# SKILL_MATRIX (Phase 2)

Skills + dev-intelligence integrated for Privacy Guardian. Skill precedence
(master plan §5): privacy/security rules > project docs > architecture > threat
model > engineering skills > UI skills > preferences. Third-party skills never
override privacy rules.

## Engineering skills (Addy Osmani / agent-skills, MIT) — installed

Location: `.opencode/skills/<name>/SKILL.md` · references: `.opencode/references/`

| Skill | Phase of lifecycle | Used for |
|---|---|---|
| spec-driven-development | define | new feature / significant change — spec before code |
| test-driven-development | verify | red-green-refactor; prove slices |
| incremental-implementation | build | thin vertical slices, verify each |
| api-and-interface-design | build | REST endpoints, module boundaries, contracts |
| debugging-and-error-recovery | verify | bugs/hangs/repro→localize→fix→guard |
| code-review-and-quality | review | pre-merge multi-axis review |
| code-simplification | review | clarity without behavior change |
| security-and-hardening | review | OWASP, untrusted input, least privilege |
| performance-optimization | review | measure first, optimize what matters |
| git-workflow-and-versioning | ship | atomic commits, clean history |
| using-agent-skills | meta | skill discovery/routing |

Note: skills activate from the session after install (startup-locked list).

## Graphify — installed

- Skill: user config `C:\Users\MuslimQasim\.config\opencode\skills\graphify\SKILL.md` +
  `.opencode/plugins/graphify.js` (execute.before hook).
- Graph: `graphify . --code-only` (no API key — deterministic AST)
  → `graphify-out/graph.json` (356 nodes / 576 edges / 40 communities),
  `GRAPH_REPORT.md`, `graph.html`. Artifacts gitignored (regenerable).
- Usage policy (master plan §3): regenerate after major architecture changes;
  use `graphify explain/path/query` before editing unfamiliar subsystems.

## Anthropic skills (anthropics/skills)

Evaluated as a **reference only** (doc/creative oriented). UI/design principles
adopted into `docs/UI_GUIDELINES.md`. No API key used. The docx/pdf/pptx/xlsx
skills are source-available, not open source — not vendored.

## Project-specific skill docs

- `.opencode/skills/using-agent-skills` — intent → skill routing (AGENTS.md table).
- References include `definition-of-done.md`, project-relevant checklists.

## Gap / blocked

- Ollama local AI integration (Phase 3) blocked on Ollama installation.
- `skills` CLI (npx) not needed — skills vendored directly.