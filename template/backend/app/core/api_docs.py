"""API reference with Scalar, branded and without calls to third parties (Keelstone).

The page is rendered by ``scalar-fastapi``, maintained by Scalar. Everything that would reach
Scalar's services is switched off: telemetry, the AI agent, the hosted fonts, the request
proxy and the button that opens Scalar's client. A Content Security Policy built from the
rendered page enforces it in the browser: scripts only from the pinned bundle and the page's
own inline script, connections only to this API.
"""

import base64
import hashlib
import re
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from scalar_fastapi import AgentScalarConfig, get_scalar_api_reference

from app.core.brand import BRAND_MARK_SVG, BRAND_NAME, BRAND_PRIMARY_COLOR
from app.core.config import settings

API_DOCS_PATH = "/docs"
_INLINE_SCRIPT = re.compile(r"<script>(.*?)</script>", re.DOTALL)

BRAND_CSS = f"""
.light-mode, .dark-mode {{
  --scalar-color-accent: {BRAND_PRIMARY_COLOR};
  --scalar-button-1: {BRAND_PRIMARY_COLOR};
  --scalar-button-1-color: #ffffff;
  --scalar-font: Inter, system-ui, sans-serif;
  --scalar-font-code: ui-monospace, SFMono-Regular, Menlo, monospace;
}}
/* White label: the vendor link is hidden (Scalar is MIT licensed; the link is a courtesy). */
a[href*="scalar.com"] {{
  display: none;
}}
"""


def _favicon_data_url() -> str:
    encoded = base64.b64encode(BRAND_MARK_SVG.encode()).decode()
    return f"data:image/svg+xml;base64,{encoded}"


def _source(url: str) -> str:
    """CSP source of the Scalar bundle: its origin, or 'self' when served by this app."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.netloc else "'self'"


def content_security_policy(html: str, script_url: str) -> str:
    """The policy of the reference page: only the pinned bundle and the page's inline script."""
    hashes = " ".join(
        "'sha256-{}'".format(base64.b64encode(hashlib.sha256(script.encode()).digest()).decode())
        for script in _INLINE_SCRIPT.findall(html)
    )
    directives = {
        "default-src": "'none'",
        "script-src": f"{_source(script_url)} {hashes}".strip(),
        # Scalar injects its styles at runtime.
        "style-src": "'self' 'unsafe-inline'",
        "img-src": "'self' data:",
        "font-src": "'self' data:",
        "connect-src": "'self'",
        "worker-src": "'self' blob:",
        "frame-ancestors": "'none'",
        "base-uri": "'none'",
        "form-action": "'none'",
    }
    return "; ".join(f"{name} {value}" for name, value in directives.items())


def api_reference(openapi_url: str) -> HTMLResponse:
    """The Scalar page for ``openapi_url``, with its Content Security Policy."""
    script_url = settings.API_DOCS_SCALAR_JS_URL
    response = get_scalar_api_reference(
        openapi_url=openapi_url,
        title=f"{BRAND_NAME} API",
        scalar_js_url=script_url,
        scalar_favicon_url=_favicon_data_url(),
        telemetry=False,
        agent=AgentScalarConfig(disabled=True),
        with_default_fonts=False,
        hide_client_button=True,
        show_developer_tools="never",
        custom_css=BRAND_CSS,
    )
    html = bytes(response.body).decode()
    response.headers["Content-Security-Policy"] = content_security_policy(html, script_url)
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def add_api_reference(app: FastAPI, openapi_url: str) -> None:
    """Serve the reference at ``/docs``."""

    @app.get(API_DOCS_PATH, include_in_schema=False)
    async def api_docs() -> HTMLResponse:
        return api_reference(openapi_url)
