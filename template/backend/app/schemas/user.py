"""User schemas."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import EmailStr, Field, field_validator

from app.schemas.base import BaseSchema, TimestampSchema


def _supported_locale(value: str | None) -> str | None:
    """Keelson: a language code accepted by the API (app/core/i18n.py), or ValueError."""
    if value is None:
        return None
    from app.core.i18n import SUPPORTED_LANGUAGES, supported

    code = supported(value)
    if code is None:
        raise ValueError(f"unsupported language; use one of: {', '.join(SUPPORTED_LANGUAGES)}")
    return code


class UserRole(StrEnum):
    """User role enumeration for API schemas."""

    ADMIN = "admin"
    USER = "user"


class UserBase(BaseSchema):
    """Base user schema."""

    email: EmailStr = Field(max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool = True

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower()


class UserRegister(BaseSchema):
    """Self-registration (Keelson, from the official template): no role, no status.

    Upstream registered with ``UserCreate``, so anyone could send ``"role": "admin"``.
    """

    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower()


class UserCreate(UserBase):
    """Schema for creating a user (administrators)."""

    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.USER


class UserUpdate(BaseSchema):
    """Schema for updating a user."""

    email: EmailStr | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    role: UserRole | None = None
    onboarding_completed_at: datetime | None = Field(
        default=None,
        description="Set to a timestamp to mark onboarding complete; null to reset.",
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str | None) -> str | None:
        return v.lower() if v is not None else None


class UserUpdateMe(BaseSchema):
    """Fields a user may change on their own profile (Keelson, from the official template).

    Password, role and account status are excluded: the password changes through
    ``UpdatePassword``, which requires the current one; role and status are for administrators.
    """

    email: EmailStr | None = Field(default=None, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    onboarding_completed_at: datetime | None = Field(
        default=None,
        description="Set to a timestamp to mark onboarding complete; null to reset.",
    )
    locale: str | None = Field(
        default=None, description="Preferred language, one of the supported languages."
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str | None) -> str | None:
        return v.lower() if v is not None else None

    @field_validator("locale")
    @classmethod
    def supported_locale(cls, v: str | None) -> str | None:
        return _supported_locale(v)


class UpdatePassword(BaseSchema):
    """Own password change: the current password is required (from the official template)."""

    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UserRead(UserBase, TimestampSchema):
    """Schema for reading a user."""

    id: UUID
    role: UserRole = UserRole.USER
    avatar_url: str | None = None
    onboarding_completed_at: datetime | None = None
    locale: str | None = None


class UserInDB(UserRead):
    """User schema with hashed password (internal use)."""

    hashed_password: str


class AdminUserRead(BaseSchema):
    """Minimal user info for admin endpoints."""

    id: UUID
    email: str
    full_name: str | None = None
    role: str = "user"
    is_active: bool = True
    is_app_admin: bool = False
    conversation_count: int = 0
    created_at: datetime


class AdminUserList(BaseSchema):
    """Paginated list of users for admin."""

    items: list[AdminUserRead]
    total: int


class ImpersonateResponse(BaseSchema):
    """Response schema for admin user impersonation."""

    access_token: str
    token_type: str
    impersonated_user_id: str
    impersonated_by: str
    expires_in: int
