---
description: Exception handling patterns and security conventions
globs: ["backend/app/core/**/*.py", "backend/app/services/**/*.py"]
---

# Exceptions & Security

## Domain Exceptions (`app/core/exceptions.py`)

All extend `AppException`. Always pass `message` and `details`:

```python
raise NotFoundError(message="User not found", details={"user_id": str(user_id)})
raise AlreadyExistsError(message="Email already registered", details={"email": email})
raise AuthenticationError(message="Invalid or expired token")
raise AuthorizationError(message="Role 'admin' required for this action")
```

Exception handlers in `api/exception_handlers.py` automatically:
- Map to HTTP status codes
- Log with structured context (path, method, error code)
- Return consistent JSON error format
- Add `WWW-Authenticate: Bearer` header on 401

## Security Patterns

JWT auth (`core/security.py`):
- `issue_session_tokens(user)` — access and refresh token in the user's session version;
  `create_access_token(subject, version=...)` / `create_refresh_token(subject, version=...)` below it
- `read_session_token(token, ACCESS | REFRESH)` → `SessionClaims | None`; then
  `claims.is_current_for(user)` (active user, current `token_epoch`)
- Token payload: `{"exp", "sub": user_id, "type": "access"|"refresh", "ver": token_epoch}`,
  plus `jti` and `sid` (refresh: token and session ids, rotated and ended in
  `app/core/revoked_tokens.py`), `act` (impersonation: administrator id and session version)
  and `auth_time` (sign-in time, kept by rotations; `UserService.confirm_identity`)
- A change of credentials raises `users.token_epoch` (`UserService`), ending every session
- User content is served through `app/core/user_content.py` (sandbox, nosniff, RFC 6266 names)

Password hashing (pwdlib):
- `get_password_hash(password)` — Argon2id
- `verify_password(plain, hashed)`; at sign-in `verify_and_update_password` also upgrades bcrypt hashes
- NEVER store plain passwords; never log them (tests/test_log_trap.py)
- A model's `__repr__` never includes a secret column (hashes, tokens, keys, encrypted
  credentials): representations reach logs and tracebacks unredacted (tests/test_model_repr.py)

API keys:
- `secrets.compare_digest()` for constant-time comparison
- `APIKeyHeader(name=settings.API_KEY_HEADER, auto_error=False)`

## Role-Based Access Control

```python
class RoleChecker:
    def __init__(self, required_role: UserRole) -> None:
        self.required_role = required_role

    async def __call__(self, user: Annotated[User, Depends(get_current_user)]) -> User:
        if not user.has_role(self.required_role):
            raise AuthorizationError(message=f"Role '{self.required_role.value}' required")
        return user

CurrentAdmin = Annotated[User, Depends(RoleChecker(UserRole.ADMIN))]
```
