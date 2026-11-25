"""Content uploaded by users is served so that it cannot act in the API's origin (Keelson)."""

from pathlib import Path

import pytest

from app.core.user_content import (
    USER_CONTENT_CSP,
    avatar_response,
    content_disposition,
    user_content_headers,
)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("report.pdf", 'attachment; filename="report.pdf"'),
        (
            "Résumé 2026.pdf",
            "attachment; filename=\"R_sum_ 2026.pdf\"; filename*=UTF-8''R%C3%A9sum%C3%A9%202026.pdf",
        ),
        (
            "отчёт.txt",
            "attachment; filename=\"_____.txt\"; filename*=UTF-8''%D0%BE%D1%82%D1%87%D1%91%D1%82.txt",
        ),
        ('a"b\\c\r\nd.txt', "attachment; filename=\"a_b_c__d.txt\"; filename*=UTF-8''a%22b%5Cc%0D%0Ad.txt"),
    ],
)
def test_content_disposition_follows_rfc_6266(filename: str, expected: str) -> None:
    header = content_disposition("attachment", filename)
    assert header == expected
    header.encode("latin-1")  # what Starlette does with every header value


def test_unknown_dispositions_are_attachments() -> None:
    assert content_disposition("bogus", "a.txt").startswith("attachment;")


@pytest.mark.parametrize(
    "media_type",
    [
        "text/html",
        "text/html; charset=utf-8",
        "application/xhtml+xml",
        "image/svg+xml",
        "text/javascript",
        "application/javascript",
        "application/xml",
        "text/xml",
        "application/rss+xml",
        "TEXT/HTML",
    ],
)
def test_active_content_is_always_an_attachment(media_type: str) -> None:
    headers = user_content_headers(media_type, "inline", "page.html")
    assert headers["Content-Disposition"].startswith("attachment;")
    assert headers["Content-Security-Policy"] == USER_CONTENT_CSP
    assert headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize("media_type", ["application/pdf", "image/png", "text/plain", "video/mp4"])
def test_passive_content_may_be_shown_inline_in_a_sandbox(media_type: str) -> None:
    headers = user_content_headers(media_type, "inline", "file")
    assert headers["Content-Disposition"].startswith("inline;")
    assert headers["Content-Security-Policy"] == USER_CONTENT_CSP


@pytest.mark.parametrize(
    ("name", "media_type"),
    [
        ("a.png", "image/png"),
        ("a.jpg", "image/jpeg"),
        ("a.webp", "image/webp"),
        ("a.gif", "image/gif"),
        ("a.svg", "application/octet-stream"),
        ("a.html", "application/octet-stream"),
    ],
)
def test_avatars_are_served_as_images_only(tmp_path: Path, name: str, media_type: str) -> None:
    path = tmp_path / name
    path.write_bytes(b"x")
    response = avatar_response(str(path))
    assert response.media_type == media_type
    assert response.headers["content-security-policy"] == USER_CONTENT_CSP
    assert response.headers["x-content-type-options"] == "nosniff"
