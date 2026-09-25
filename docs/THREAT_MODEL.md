# THREAT_MODEL

Threat list for Privacy Guardian (living doc; grows with phases).

| # | Threat | Attack surface | Control | Phase |
|---|---|---|---|---|
| T1 | Prompt injection via web content | OSINT fetch, LLM prompts | web content ≠ instructions; SSRF-safe fetch; input sanitized; **evidence centrally capped (2000 chars); content stored as inert data — nothing executes** | 6,13 |
| T2 | Data leakage to Colab/AI | hybrid payloads | explicit approval; payloads reference IDs, minimize raw data | 8,13 |
| T3 | SSRF from tool inputs | external URL fetch | allow-lists, no file://, no private-IP redirects; **`security/url_safety` guard: https-only, private/reserved IP + hostname families rejected, userinfo rejected; sitecheck manifest probe URLs validated (no `{target}` in authority) + host-consistency after interpolation** | 6,13 |
| T4 | Command injection via tool args | subprocess adapters | adapter contract, argument validation, no shell interpolation; **verified by test: probe argv is a fixed list, no `shell=True`/`eval(`/`exec(`/`os.system`** | 6,13 |
| T5 | Path traversal | evidence/files, photo uploads | canonical path checks, uploads outside served roots; **store names are server-generated (scan_id + uuid), display name is a stripped basename; tests assert files land inside upload dir for `/`, `%2F`, `\` payloads** | 7,13 |
| T6 | Downloaded malicious artifact | OSINT tool installs | pinned versions, review before install, vendored deps audit | 6,13 |
| T7 | Local network exposure | dev server, FastAPI | bind 127.0.0.1; CORS allow-list; auth if LAN enabled; **default `host`/CORS loopback verified by test; settings write endpoints 405; CORS disallowed-origin rejected** | 1,13 |
| T8 | Evidence tampering / fabrication | writes to evidence store | append-only audit log, hashes of sources | 4,13 |
| T9 | Secrets in repo | .env, API keys, Colab creds | .gitignore, secret scan, never commit; **rg scan clean (2026-09-12); `uvx pip-audit` + `npm audit` = 0 vulns recorded** | all,13 |
| T10 | CSRF/XSS on local UI | frontend | React defaults, CSP, no unsafe innerHTML; **API responses get CSP `default-src 'none'`, nosniff/deny-frame/no-referrer/no-store headers** | 12,13 |
| T11 | Decompression / pixel bomb | image upload | **upload rejects declared `width*height > 50 MP` before pixels are allocated (in addition to 20 MB size cap + magic-byte verify)** | 7,13 |
| T12 | Feedback / output-data servility | LLM output, fetched pages | AI output = data only; risk scoring + research are deterministic; **explanation determinism verified by test** | 10,13 |
| T13 | Agent prompt injection via tool results | agent brain, tool outputs | loop wraps tool output as `<untrusted>`; evidence-only findings; allowlist blocks unknown tools (incl. shell/URL/exec); **security suite: injected 'run shell' results stay inert, arg allowlisting strips hostile keys** | 14–15 |
| T14 | Agent auto-removal / state change | agent confirm flow | **no action without a per-item confirm event**: proposals are read back from persisted conversation steps, `POST /confirm` only `approve|deny`, actions stay `pending` behind the existing approval UI; security tests assert chat never creates actions | 15 |
| T15 | Secret/plaintext in agent audit trail | conversation persistence | tool args that look like secrets redacted to `***` before DB write; breach path emits only k-anonymity prefix + suffix count (no plaintext, no full hash); **verified by persist + security tests** | 15 |
| T16 | Third-party-network abuse by agent | agent tools | reverse-image search and breach range API gated behind explicit hybrid approval (`approveHybrid`); local-only runs report blocked; **verified by gate tests** | 15 |
| T17 | Uncensored/abliterated brain misalignment | agent brain (user-chosen `PG_AGENT_MODEL`, e.g. Qwen3.8-27B-Uncensored, refusals 98/100→12/100) | model output treated as **data, never instructions**: tool allowlist (+ arg allowlist) — no shell/URL/exec; results wrapped `<untrusted>`; findings/evidence = tool outputs only; AI text never feeds the deterministic risk score; removals still per-item human `approve|deny`; model name routed verbatim (locked by `test_agent_brain.py`) | 16 |

## Residual risks (accepted)
- OSINT source reliability varies → evidence captures exact source + timestamp + confidence.
- Local GPU weak → some workloads only possible via approved Colab → availability gap, not security gap.
- The app is a single-user, loopback-bound local tool: there is no authentication layer. Exposure of the port beyond loopback (LAN deployment) would require an auth layer (out of scope; guarded by default bind).
- DNS-rebind TOCTOU remains on the OSINT fetchers (public DoH/search engines only — no host-rooted SSRF surface; sitecheck hosts are manifest-curated and validated).