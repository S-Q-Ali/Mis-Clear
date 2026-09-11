# Plan — Phase 7: Photo Forensics (local-first; heavy AI → Colab)

Controlling spec: `MASTER_BUILD_INSTRUCTIONS.md` Phase 7 (§7, §11, §12 image
pipeline, §13 Colab worker, §14 job protocol) + recorded user decision:
**heavy AI/GPU (vision, heavy OCR) → approved Colab worker; laptop sirf local
processing. No external image upload by default.** Colab = temporary compute,
never system of record; down/unapproved → graceful degradation only.

## User decisions (confirmed)
- Add **Pillow** dependency (EXIF + pHash).
- **QR → local decode** (`opencv-python-headless`, no system lib); 1D **barcode → vision (Colab)** (deferred to Phase 8 wiring).
- Image trigger: **`POST /api/scans/{id}/image`** (multipart → `data/uploads`, gitignored) → photo tool chain.

## Architecture split
- **Local, always on:** `md5`/`sha256` (stdlib), d-hash `pHash` (Pillow), EXIF+GPS parse (Pillow), QR decode (opencv-headless).
- **Colab-routed, graceful:** local vision / heavy OCR via `ModelRouter.route()` (Qwen-VL/Gemma). No backend → no finding, honest coverage, never crash.

## Slices (incremental + TDD, har slice verify)
1. Deps: `uv add pillow opencv-python-headless` (lockfile + pyproject).
2. `tools/photo/base.py` — `PhotoTool` helpers (load image, hashes) reusing `tools/base.py` `ToolResult`/`ToolFinding`.
3. `tools/photo/hash.py` — md5+sha256 adapter (confirmed/informational).
4. `tools/photo/phash.py` — perceptual d-hash adapter (Pillow, deterministic).
5. `tools/photo/exif.py` — EXIF + GPS adapter (untrusted metadata; location finding possible/confirmed).
6. `tools/photo/qr.py` — QR decode (opencv-headless local); barcode → vision placeholder.
7. `tools/photo/vision.py` — vision/OCR adapter via `ModelRouter`. debatable backend routing: approved+available → inference job; else graceful (status `blocked`, coverage honest, errors note "no AI backend"). (Actual Colab job transport = Phase 8.)
8. `tools/photo/registry.py` — `photo_pipeline()` ordered adapter chain.
9. Orchestrator: photo-scan path — create `ToolRun` per photo adapter, persist `Image` row (filename, local_path, md5, sha256, phash, exif) + `Finding` rows + identity (image target); status running→completed; refuses external upload when `scan_mode` PRIVACY gate requires approval (upload is local by default).
10. Upload API: `POST /api/scans/{id}/image` (multipart, validate size/type/magic bytes, store under `data/uploads/<scan_id>/`), returns updated `ScanOut`; 404 missing scan; config `PG_UPLOAD_DIR`.
11. Tests:
    - `tests/unit/test_photo_adapters.py` — synthetic images generated at test time (Pillow): hash correctness (known digest vectors), phash robustness (tiny resize → close hamming), EXIF fixture (synthetic GPS), QR fixture (draw+decode), vision graceful (no backend → blocked, no crash).
    - `tests/integration/test_photo_scan.py` — upload → pipeline → `Image` row + findings + tool_runs; monkeypatched registry/router (no real AI/network).
12. Docs + tracking: TOOL_MATRIX (photo rows ✅ where landed), PROJECT_DOCUMENTATION (Phase 7 ✅), ARCHITECTURE (photo pipeline + upload), COLAB_GPU_ARCHITECTURE (photo adapters via router), SESSION_STATE (Phase 7 entry).
13. Verify + ship: `uv run pytest` (53 + new green), legacy 46+34, `npm run build`, commit (`feat: phase 7 - photo forensics (local hashes/exif/phash/qr, vision via colab router)`) + push `origin/main`.

## Guardrails
- Synthetic fixtures only — no real personal photos/EXIF.
- Untrusted upload bytes validated (magic bytes + size cap); no path traversal.
- Vision/OCR never fabricates: no backend → no finding.
- Do NOT touch `.opencode/opencode.json` (unrelated).

## Out of scope (later)
- Phase 8: Colab job transport not marked vision/OCR live; barcode decode; identity-graph links for images (Phase 9); image search workflow (needs explicit hybrid approval).