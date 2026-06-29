"""Clerk JWT verification.

Production path: fetches Clerk's JWKS, caches it, validates JWTs from the
`Authorization: Bearer ...` header. Extracts `sub` (user_id) and `org_id`
(optional — users without a Clerk org are treated as solo users).

Dev path (when CLERK_JWKS_URL unset): accepts `X-Dev-User` (required) and
`X-Dev-Org` (optional) headers verbatim. Lets you build features without
setting up Clerk.
"""

from dataclasses import dataclass
from functools import lru_cache

import httpx
from fastapi import Depends, Header, HTTPException, Request, status
from jose import JWTError, jwt

from pynote_core.settings import Settings, get_settings


@dataclass(frozen=True)
class Principal:
    """Authenticated caller identity. `org_id` is None for solo users."""

    user_id: str
    org_id: str | None = None
    email: str | None = None


@lru_cache(maxsize=1)
def _jwks_cache() -> dict[str, object] | None:
    settings = get_settings()
    if not settings.clerk_jwks_url:
        return None
    resp = httpx.get(settings.clerk_jwks_url, timeout=5.0)
    resp.raise_for_status()
    return resp.json()


def _verify_clerk_jwt(token: str, settings: Settings) -> Principal:
    jwks = _jwks_cache()
    if jwks is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Clerk JWKS not configured.",
        )
    try:
        unverified = jwt.get_unverified_header(token)
        kid = unverified.get("kid")
        key = next((k for k in jwks["keys"] if k["kid"] == kid), None)  # type: ignore[index]
        if key is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown signing key.")
        claims = jwt.decode(
            token,
            key,  # type: ignore[arg-type]
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}") from e

    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token is missing user.")
    # org_id is optional (solo users have no Clerk org). Clerk v2 session tokens
    # nest the active org under `o.id`; older/templated tokens expose `org_id`
    # at the top level. Accept either; leave None for solo users.
    org_id = claims.get("org_id")
    if not org_id:
        org_claim = claims.get("o")
        if isinstance(org_claim, dict):
            org_id = org_claim.get("id")
    return Principal(user_id=user_id, org_id=org_id, email=claims.get("email"))


async def current_principal(
    request: Request,
    authorization: str | None = Header(default=None),
    x_dev_user: str | None = Header(default=None),
    x_dev_org: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """FastAPI dep — returns the authenticated principal or raises 401."""
    # Dev shortcut: when Clerk isn't configured, trust X-Dev-* headers.
    if not settings.clerk_jwks_url:
        if not x_dev_user:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Dev auth requires X-Dev-User header (Clerk is not configured).",
            )
        return Principal(user_id=x_dev_user, org_id=x_dev_org)

    # Production: Bearer token from Clerk.
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Bearer token.")
    return _verify_clerk_jwt(authorization.split(" ", 1)[1], settings)
