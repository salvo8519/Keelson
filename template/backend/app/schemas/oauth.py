"""Single sign-on schemas (Keelson)."""

from pydantic import Field

from app.schemas.base import BaseSchema


class OAuthProviderRead(BaseSchema):
    """A provider shown on the sign-in page."""

    name: str
    label: str


class OAuthCodeExchange(BaseSchema):
    """The one-time code the frontend received after signing in at a provider."""

    code: str = Field(min_length=16, max_length=128)
