# Environment Report (Phase 0)

> Generated: 2026-09-10 · Project: Privacy Guardian (pivot from Mis-Clear)
> Method: live system audit on the developer laptop (`E:\Web App\Cleaner`).

## Summary

| Check | Status | Value |
|---|---|---|
| OS | OK | Windows 11 (build 26200.0) |
| PowerShell | OK | 5.1.26100.9444 |
| Git | OK | 2.55.0.windows.2 |
| Python | OK | 3.11.15 (uv-managed interpreter also present) |
| uv | OK | 0.11.32 |
| Node.js | OK | v24.18.0 |
| npm | OK | 11.16.0 |
| OpenCode | OK | 1.18.21 |
| Graphify | OK | 0.9.57 (`C:\Users\MuslimQasim\.local\bin\graphify.exe`) |
| Agent Skills | OK | vendored in `.opencode/skills` (11 skills) |
| Ollama | NOT INSTALLED | needed for Phase 3 (Local AI) |
| Docker | NOT INSTALLED | optional; not required by master plan |
| skills CLI (`npx skills`) | NOT INSTALLED | skills already vendored directly |
| GPU (NVIDIA) | Present | GeForce MX250, 2 GB VRAM (weak) |
| GPU (Intel) | Present | Iris Plus Graphics, 1 GB VRAM |
| RAM | OK | 15.8 GB total / 5.4 GB free |
| CPU | OK | Intel Core i7-1065G7, 4 cores / 8 threads |
| Disk (C:) | Low-ish | 28.7 GB free of ~236 GB |

## Detailed findings

### Languages / runtimes
- **Python 3.11.15** active in shell (`hermes-agent` venv shim), plus
  `uv`-managed CPython 3.11 at
  `C:\Users\MuslimQasim\AppData\Roaming\uv\python`. Prefer **`uv` for all
  project venvs** (fast, pinned).
- **Node v24.18.0 / npm 11.16.0** — suitable for Vite + React + TypeScript
  toolchain.

### AI / workers
- **Ollama: missing.** Phase 3 requires installation
  (ollama.com) and at least one local model, e.g. a Qwen-family reasoning
  model. Nothing is hard-coded pending installation; `ModelRouter` will
  degrade gracefully when Ollama is absent.
- **Docker: missing.** Not required by the architecture (Colab is the GPU
  worker). Skipping installation to keep the laptop lean.
- **Colab**: no local component needed — reached via notebook/HTTP protocol;
  confirmed viable approach given weak local GPU (MX250 2 GB).

### Dev intelligence
- **Graphify 0.9.57** installed and on PATH. Integration into the OpenCode
  workflow is pending (Phase 2: `graphify install --platform opencode`,
  `/graphify .`).
- **Addy Osmani agent-skills**: already vendored (commit `7084d1a`);
  10 curated skills + meta-skill in `.opencode/skills/`, references in
  `.opencode/references/`.
- **Anthropic skills**: evaluated previously; doc-oriented skills were not
  applicable as the primary pack. No API key required / used.

### Hardware constraints
- **GPU**: MX250 is entry-level (2 GB). Local vision/OCR is possible but
  slow; heavy batches belong on the **Colab T4 worker** (explicit approval).
- **RAM**: 15.8 GB — adequate for SQLite + FastAPI + Ollama (7B model) +
  browser, but not roomy. Keep Ollama model ≤ 7B locally.
- **Disk**: 28.7 GB free. Watch `uv` caches, model weights (~4–8 GB per
  7B), and dataset/cache growth in `data/`.

## Gaps / actions

1. Install **Ollama** + pull one local reasoning model (Phase 3 gate).
2. Optionally rename remote repo `S-Q-Ali/Mis-Clear` → `privacy-guardian`
   (cosmetic; affects clone URLs). Pending user decision.
3. Graphify: run `graphify install --platform opencode` and generate a
   project graph after Phase 1 bootstrap.
4. `skills` CLI not needed — skills are vendored directly.