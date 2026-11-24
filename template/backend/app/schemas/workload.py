"""Workload identity schemas (Keelson)."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class WorkloadTokenRequest(BaseSchema):
    """The OpenID Connect token of a CI job (GitHub Actions, GitLab CI)."""

    token: str = Field(min_length=20, max_length=8192)


class WorkloadToken(BaseSchema):
    """A credential of this API: send it as an API key (``X-API-Key``) until it expires."""

    credential: str
    expires_at: datetime
    organization_id: UUID
    scopes: list[str]
