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
| ExifTool | EXIF metadata | `tools/photo/` | planned (Phase 7) |
| ImageMagick | image transform | `tools/photo/` | planned (Phase 7) |
| OpenCV | image ops | `tools/photo/` | planned (Phase 7) |
| Tesseract | OCR | `tools/photo/` | planned (Phase 7) |
| pHash | perceptual hashing | `tools/photo/` | planned (Phase 7) |
| Ollama Qwen | local reasoning | `app/backend/services/model_router.py` | ✅ router code (backend optional) |
| Ollama Qwen-VL/Gemma | local vision | same | ✅ router code (backend optional) |
| Colab T4 | heavy vision/OCR/embeddings | `colab/` | planned (Phase 8) |

## Policy
- Prefer local-first; every external call must be optional + approved where it
  touches personal data.
- Any tool with a network component is treated as untrusted input source.
- Site manifests (`tools/site_manifests/`) ship as synthetic samples — replace
  with real catalogs before user-facing scans; empty manifest = adapter reports
  "no sites configured" (blocked).