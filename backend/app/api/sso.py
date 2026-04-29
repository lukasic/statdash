import hmac
import os
import secrets
from urllib.parse import quote_plus, urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_jwt_strategy
from app.core.config import settings
from app.core.database import get_async_session
from app.models.user import User

router = APIRouter(prefix="/auth/sso", tags=["auth"])

_STATE_COOKIE = "statdash_sso_state"


def _oidc_base() -> str:
    return f"{settings.keycloak_base_url}/realms/{settings.keycloak_realm}/protocol/openid-connect"


def _callback_url(request: Request) -> str:
    if settings.sso_callback_url:
        return settings.sso_callback_url
    return str(request.base_url).rstrip("/") + "/api/auth/sso/callback"


def _frontend_url(path: str = "") -> str:
    base = settings.sso_frontend_url.rstrip("/")
    return f"{base}/{path.lstrip('/')}" if path else base or "/"


@router.get("/config")
async def sso_config() -> dict:
    return {
        "enabled": settings.sso_configured,
        "button_label": settings.sso_button_label if settings.sso_configured else None,
    }


@router.get("/login")
async def sso_login(request: Request) -> RedirectResponse:
    if not settings.sso_configured:
        raise HTTPException(status_code=404, detail="SSO not configured")

    state = os.urandom(16).hex()
    params = urlencode({
        "client_id": settings.keycloak_client_id,
        "redirect_uri": _callback_url(request),
        "response_type": "code",
        "scope": "openid email",
        "state": state,
    })

    response = RedirectResponse(url=f"{_oidc_base()}/auth?{params}", status_code=302)
    response.set_cookie(key=_STATE_COOKIE, value=state, httponly=True, samesite="lax", max_age=300)
    return response


@router.get("/callback")
async def sso_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    session: AsyncSession = Depends(get_async_session),
) -> RedirectResponse:
    if not settings.sso_configured:
        raise HTTPException(status_code=404, detail="SSO not configured")

    if error:
        msg = quote_plus(error_description or error)
        return RedirectResponse(url=_frontend_url(f"login?sso_error={msg}"), status_code=302)

    stored_state = request.cookies.get(_STATE_COOKIE)
    if not stored_state or not state or not hmac.compare_digest(stored_state, state):
        raise HTTPException(status_code=400, detail="Invalid SSO state")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    async with httpx.AsyncClient() as http:
        token_resp = await http.post(
            f"{_oidc_base()}/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _callback_url(request),
                "client_id": settings.keycloak_client_id,
                "client_secret": settings.keycloak_client_secret,
            },
        )
        token_resp.raise_for_status()

        userinfo_resp = await http.get(
            f"{_oidc_base()}/userinfo",
            headers={"Authorization": f"Bearer {token_resp.json()['access_token']}"},
        )
        userinfo_resp.raise_for_status()
        email: str | None = userinfo_resp.json().get("email")

    if not email:
        raise HTTPException(status_code=400, detail="SSO provider did not return an email address")

    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = await _provision_user(email, session)
    elif not user.is_active:
        raise HTTPException(status_code=403, detail=f"Account {email} is disabled")

    strategy = get_jwt_strategy()
    token = await strategy.write_token(user)

    response = RedirectResponse(url=_frontend_url(), status_code=302)
    response.set_cookie(
        key="statdash_auth",
        value=token,
        max_age=3600 * 24 * 7,
        httponly=True,
        secure=False,
        samesite="lax",
    )
    response.delete_cookie(_STATE_COOKIE)
    return response


async def _provision_user(email: str, session: AsyncSession) -> User:
    from fastapi_users.password import PasswordHelper

    hashed_password = PasswordHelper().hash(secrets.token_urlsafe(32))
    user = User(email=email, hashed_password=hashed_password, is_active=True, is_verified=True, is_superuser=False)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
