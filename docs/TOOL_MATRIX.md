# TOOL_MATRIX

Every external tool is wrapped behind a stable internal interface:

```python
run(target) -> ToolResult
```

`ToolResult` = tool, status, duration, findings, errors, raw reference, coverage.

| Tool | Purpose | Integration | Status |
|---|---|---|---|
| Holehe | email → account list | `tools/email/holehe.py` (site manifest) | ✅ Phase 6 |
| Sherlock | username → profiles | `tools/username/sherlock.py` (site manifest) | ✅ Phase 6 |
| Maigret | username → profiles (deep) | future manifest extension | ⬜ |
| WHOIS | domain registration (RDAP) | `tools/web/whois.py` | ✅ Phase 6 |
| DNS | DNS records (DNS-over-HTTPS) | `tools/web/dns.py` | ✅ Phase 6 |
| Public search | web evidence (DDG HTML) | `tools/web/search.py` | ✅ Phase 6 |
| GitHub search | handle/code exposure | `tools/web/github.py` | ✅ Phase 6 |
| ExifTool | EXIF metadata | `tools/photo/exif.py` (Pillow) | ✅ Phase 7 |
| ImageMagick | image transform | not required (Pillow) | – |
| OpenCV | image ops (QR decode) | `tools/photo/qr.py` (opencv-headless) | ✅ Phase 7 |
| Pillow | image load/EXIF/dhash | `tools/photo/base.py` | ✅ Phase 7 |
| Tesseract | OCR | exported as `ocr` job → Colab worker via `app/backend/services/vision_transport.py` (image travels as base64 in the job payload; `colab/handlers.py` `_handle_ocr`) | ✅ Phase 15 wiring |
| pHash | perceptual hashing | `tools/photo/phash.py` (d-hash) | ✅ Phase 7 |
| Ollama Qwen | local reasoning | `app/backend/services/model_router.py` | ✅ router code (backend optional) |
| Ollama Qwen-VL/Gemma | local vision | same | ✅ router code (backend optional) |
| Colab worker | heavy vision/OCR/embeddings | `colab/` (capabilities, handlers, worker lifecycle, notebook incl. Ollama setup); dispatch bind via `app/backend/services/job_dispatcher.py` + direct protocol `GET /api/jobs/next`, `POST /api/jobs/{job_id}/result` | ✅ Phase 8 (+ protocol E2E) |
| Laptop dispatcher | job submit/poll | `app/backend/services/job_dispatcher.py` + `POST /api/jobs/{id}/dispatch|poll` | ✅ Phase 8 |

## Policy
- Prefer local-first; every external call must be optional + approved where it
  touches personal data.
- Any tool with a network component is treated as untrusted input source.
- Site manifests (`tools/site_manifests/`) ship as real catalogs — username
  catalog generated from sherlock (MIT, ~256 sites, https-only, NSFW excluded),
  email catalog curated from live-verified public services. Empty manifest =
  adapter reports "no sites configured" (blocked).