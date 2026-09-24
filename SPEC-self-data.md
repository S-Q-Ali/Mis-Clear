# Spec: self-data

## Objective
Extends the catalog for "my data" surfaces: where images appear, where emails/usernames
appear, and whether a password hash is present in public breach range responses.

## Breach k-anonymity check (tool `breach_check`)
- Input: a set of passwords (user-provided, ephemeral) or single value.
- Compute SHA-1 → first 5 hex chars → `GET {PG_BREACH_API_URL}/{prefix}` (e.g., HIBP Pwned
  Passwords range endpoint). Suffix list compared locally against remaining 35 hex chars.
- Never persist input or full hash; only a boolean `breached: true/false` + count suffix
  matches and the password-anonymized note.
- Config: `PG_BREACH_API_URL` (empty → tool reports `{"ok": false, "blocked": true}`).

## Image exposure
- `photo_reverse_search` (Yandex, requires hybrid/approved scan) already yields
  `image_exposure` findings (weak evidence). Agent surfaces them as evidence cards with the
  provider + URL; never claims identity proof.

## Boundaries
- **Always:** ephemeral; nothing stored; hybrid approval gate respected.
- **Never:** full hash/plaintext logging; multiple unapproved scans; auto-follow hit URLs.