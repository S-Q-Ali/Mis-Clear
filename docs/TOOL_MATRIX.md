# TOOL_MATRIX

Every external tool is wrapped behind a stable internal interface:

```python
run(target) -> ToolResult
```

`ToolResult` = tool, status, duration, findings, errors, raw reference, coverage.

| Tool | Purpose | Integration | Status |
|---|---|---|---|
| Holehe | email → account list | `tools/email/` adapter | planned (Phase 6) |
| Sherlock | username → profiles | `tools/username/` | planned (Phase 6) |
| Maigret | username → profiles (deep) | `tools/username/` | planned (Phase 6) |
| WHOIS | domain registration | `tools/web/` | planned (Phase 6) |
| DNS | DNS records | `tools/web/` | planned (Phase 6) |
| Public search | web evidence | `tools/web/` | planned (Phase 6) |
| GitHub search | handle/code exposure | `tools/web/` | planned (Phase 6) |
| ExifTool | EXIF metadata | `tools/photo/` | planned (Phase 7) |
| ImageMagick | image transform | `tools/photo/` | planned (Phase 7) |
| OpenCV | image ops | `tools/photo/` | planned (Phase 7) |
| Tesseract | OCR | `tools/photo/` | planned (Phase 7) |
| pHash | perceptual hashing | `tools/photo/` | planned (Phase 7) |
| Ollama Qwen | local reasoning | `app/backend/services/model_router.py` | blocked (Phase 3) |
| Ollama Qwen-VL/Gemma | local vision | same | blocked (Phase 3) |
| Colab T4 | heavy vision/OCR/embeddings | `colab/` | planned (Phase 8) |

## Policy
- Prefer local-first; every external call must be optional + approved where it
  touches personal data.
- Any tool with a network component is treated as untrusted input source.