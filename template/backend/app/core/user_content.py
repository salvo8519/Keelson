"""Serving content that users uploaded (Keelstone).

Documents, chat files and avatars are served from the API's origin, where the session cookie
lives. A file that a browser renders as a page (HTML, SVG, XML, scripts) would run with that
origin: a stored cross-site scripting attack as soon as a file is seen by someone other than
its author. Every response that carries user content therefore:

* is sandboxed (``Content-Security-Policy: sandbox; default-src 'none'``): no script runs, no
  resource loads, the document has an opaque origin;
* is not sniffed (``X-Content-Type-Options: nosniff``);
* is an attachment when its type is active, whatever the caller asked;
* names the file as RFC 6266 says: ``filename*=UTF-8''...`` with an ASCII ``filename``
  fallback, so a name outside Latin-1 does not break the response.

Passive types (PDF, images, audio, video, plain text) may still be shown inline. Browsers do
not run their PDF viewer in a sandboxed document: such a file opens as a download there.
"""

import mimetypes
import re
from urllib.parse import quote

from starlette.responses import FileResponse

from app.services.file_storage import AVATAR_TYPES

USER_CONTENT_CSP = "sandbox; default-src 'none'"
FALLBACK_MEDIA_TYPE = "application/octet-stream"
_ACTIVE_TYPES = frozenset(
    {
        "text/html",
        "application/xhtml+xml",
        "image/svg+xml",
        "text/xml",
        "application/xml",
        "text/xsl",
        "text/javascript",
        "application/javascript",
        "application/ecmascript",
        "text/ecmascript",
    }
)
_UNSAFE_IN_FALLBACK = re.compile(r'[^\x20-\x7e]|["\\]')


def is_active(media_type: str | None) -> bool:
    """A type a browser may render as a document or run (any XML, scripts, HTML, SVG)."""
    essence = (media_type or "").split(";", 1)[0].strip().lower()
    return essence in _ACTIVE_TYPES or essence.endswith("+xml")


def content_disposition(disposition: str, filename: str) -> str:
    """``inline`` or ``attachment`` (anything else) with the file name, RFC 6266."""
    mode = "inline" if disposition == "inline" else "attachment"
    fallback = _UNSAFE_IN_FALLBACK.sub("_", filename)
    header = f'{mode}; filename="{fallback}"'
    encoded = quote(filename, safe="")
    if encoded != filename:
        header += f"; filename*=UTF-8''{encoded}"
    return header


def user_content_headers(media_type: str | None, disposition: str, filename: str) -> dict[str, str]:
    """The headers of a response that carries user content."""
    if is_active(media_type):
        disposition = "attachment"
    return {
        "Content-Disposition": content_disposition(disposition, filename),
        "Content-Security-Policy": USER_CONTENT_CSP,
        "X-Content-Type-Options": "nosniff",
    }


def avatar_response(path: str) -> FileResponse:
    """An avatar image, typed from its name among the accepted image types only."""
    guessed = mimetypes.guess_type(path)[0]
    media_type = guessed if guessed in AVATAR_TYPES else FALLBACK_MEDIA_TYPE
    headers = {
        "Content-Security-Policy": USER_CONTENT_CSP,
        "X-Content-Type-Options": "nosniff",
    }
    return FileResponse(path, media_type=media_type, headers=headers)
