# THREAT_MODEL

Threat list for Privacy Guardian (living doc; grows with phases).

| # | Threat | Attack surface | Control | Phase |
|---|---|---|---|---|
| T1 | Prompt injection via web content | OSINT fetch, LLM prompts | web content ≠ instructions; SSRF-safe fetch; input sanitized | 6,13 |
| T2 | Data leakage to Colab/AI | hybrid payloads | explicit approval; payloads reference IDs, minimize raw data | 8,13 |
| T3 | SSRF from tool inputs | external URL fetch | allow-lists, no file://, no private-IP redirects | 6,13 |
| T4 | Command injection via tool args | subprocess adapters | adapter contract, argument validation, no shell interpolation | 6,13 |
| T5 | Path traversal | evidence/files, photo uploads | canonical path checks, uploads outside served roots | 7,13 |
| T6 | Downloaded malicious artifact | OSINT tool installs | pinned versions, review before install, vendored deps audit | 6,13 |
| T7 | Local network exposure | dev server, FastAPI | bind 127.0.0.1; CORS allow-list; auth if LAN enabled | 1,13 |
| T8 | Evidence tampering / fabrication | writes to evidence store | append-only audit log, hashes of sources | 4,13 |
| T9 | Secrets in repo | .env, API keys, Colab creds | .gitignore, secret scan, never commit | all |
| T10 | CSRF/XSS on local UI | frontend | React defaults, CSP, no unsafe innerHTML | 12,13 |

## Residual risks (accepted)
- OSINT source reliability varies → evidence captures exact source + timestamp + confidence.
- Local GPU weak → some workloads only possible via approved Colab → availability gap, not security gap.