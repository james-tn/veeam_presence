"""Entra ID JWT validation helpers.

Simplified from daily_planner — no OBO chain needed since
Presence reads local pkl files (no user-scoped data access).
"""

from __future__ import annotations

import logging
from typing import Any

import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

_ENTRA_JWKS_URL = "https://login.microsoftonline.com/common/discovery/v2.0/keys"
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(_ENTRA_JWKS_URL, cache_keys=True)
    return _jwks_client


def validate_entra_token(
    token: str,
    expected_audience: str,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """
    Validate an Entra ID JWT and return the decoded claims.

    Raises jwt.InvalidTokenError on failure.
    """
    client = _get_jwks_client()
    signing_key = client.get_signing_key_from_jwt(token)

    options = {
        "verify_exp": True,
        "verify_aud": True,
        "verify_iss": False,  # Entra issues from multiple issuers
    }

    decoded = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=expected_audience,
        options=options,
    )

    # Optionally verify tenant
    if tenant_id:
        token_tid = decoded.get("tid", "")
        if token_tid != tenant_id:
            raise jwt.InvalidTokenError(f"Token tenant {token_tid} != expected {tenant_id}")

    return decoded
