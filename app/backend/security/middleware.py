"""Security response-header middleware (Phase 13).

Applies conservative, API-appropriate defaults to every response. `setdefault`
keeps any explicit header the app sets, and the CSP (`default-src 'none'`) is
correct for a JSON control plane that never serves HTML.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders

X_CONTENT_TYPE = "nosniff"
FRAME_OPTIONS = "DENY"
REFERRER = "no-referrer"
CSP = "default-src 'none'"
NO_STORE = "no-store"

SECURITY_HEADERS = {
    "x-content-type-options": X_CONTENT_TYPE,
    "x-frame-options": FRAME_OPTIONS,
    "referrer-policy": REFERRER,
    "content-security-policy": CSP,
}


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                if path.startswith("/api"):
                    headers.setdefault("cache-control", NO_STORE)
            await send(message)

        await self.app(scope, receive, send_wrapper)