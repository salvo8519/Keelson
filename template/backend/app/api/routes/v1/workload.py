"""Workload identity: a CI job trades its OpenID Connect token for a credential (Keelstone)."""

import logging
from typing import Any

from fastapi import APIRouter

from app.core import workload_identity
from app.core.config import settings
from app.core.exceptions import AuthenticationError
from app.schemas.workload import WorkloadToken, WorkloadTokenRequest
from app.services.rate_limit import RateLimitCategory, make_anonymous_rate_limit_dep

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/workload-token",
    response_model=WorkloadToken,
    dependencies=[make_anonymous_rate_limit_dep(RateLimitCategory.AUTH)],
)
async def exchange_workload_token(body: WorkloadTokenRequest) -> Any:
    """Exchange the OpenID Connect token of a CI job for a short-lived credential.

    The token must come from a trusted issuer, for the configured audience, with the
    configured claims (repository, branch...). The credential acts for the trust's
    organization with its scopes, like an API key, until it expires.
    """
    try:
        trust, claims = await workload_identity.verify(body.token, settings.WORKLOAD_IDENTITIES)
    except workload_identity.WorkloadRefused as refused:
        logger.warning("workload_token_refused", extra={"reason": str(refused)})
        raise AuthenticationError(message="Workload token not accepted") from None
    credential, expires_at = workload_identity.issue(trust, settings.SECRET_KEY)
    logger.info(
        "workload_credential_issued",
        extra={
            "workload": trust.name,
            "organization_id": str(trust.organization_id),
            "ci_subject": claims.get("sub"),
        },
    )
    return WorkloadToken(
        credential=credential,
        expires_at=expires_at,
        organization_id=trust.organization_id,
        scopes=sorted(trust.scopes),
    )
