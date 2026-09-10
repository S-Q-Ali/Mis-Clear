# UI_GUIDELINES

Target: a **professional privacy/security product UI**, not a generic
AI-generated dashboard. Applied in Phase 12 (React), but the bar is fixed now.

## Design goals
- Clear information hierarchy; high signal-to-noise ratio.
- Responsive layout; keyboard accessible; accessible color contrast.
- Clear severity indicators (critical/high/medium/low/informational).
- Meaningful empty states, loading states, error states, confirmation states.
- Progressive disclosure; evidence-first presentation (source + URL + timestamp before conclusions).
- Tool coverage always visible; failed tools clearly shown.
- No unnecessary animations, no fake metrics, no decorative bulk.

## Core screens
- **Dashboard** — overall privacy risk, active scans, recent/critical findings, tool coverage, failed tools, Colab worker + local AI state, recent activity.
- **New Scan** — email / username / image / custom identifier; scan mode (local-only / hybrid); explicit privacy warning before hybrid.
- **Investigation** — scan progress, active agents, tools executing, evidence discovered, failed/blocked tools, coverage, confidence.
- **Findings** — severity, confidence, title, evidence, source, URL, timestamp, affected identity, recommended action.
- **Identity Graph** — email → username → profile → website → public identity (visualization only where it aids understanding).
- **Photo Forensics** — EXIF, GPS, device metadata, timestamps, OCR, QR/barcodes, hashes, pHash, sensitive info detection, possible public matches.
- **Privacy Actions** — recommended action, official deletion URL, instructions, evidence, **explicit approval required**, status. No one-click destructive actions.

## Accessibility
- Keyboard nav, focus states, WCAG contrast, semantics-first markup, labels on all inputs.