"""Auth API endpoints: request-code, verify-code, refresh, logout."""

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from api.auth import service
from api.auth.models import RequestCodeInput, TokenResponse, VerifyCodeInput
from api.config import Settings
from api.deps import get_pool

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_settings() -> Settings:
    return Settings()


@router.post("/request-code")
async def request_code(
    body: RequestCodeInput,
    pool: asyncpg.Pool = Depends(get_pool),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        await service.request_code(pool, settings.TELEGRAM_BOT_TOKEN, body.telegram_username)
    except HTTPException as exc:
        if exc.status_code == 404:
            return {"sent": False, "error": "not found", "detail": exc.detail}
        raise
    return {"sent": True}


@router.post("/verify-code", response_model=TokenResponse)
async def verify_code(
    body: VerifyCodeInput,
    pool: asyncpg.Pool = Depends(get_pool),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    access_token, refresh_token = await service.verify_code(
        settings.TELEGRAM_BOT_TOKEN,
        pool,
        body.telegram_username,
        body.code,
        settings.JWT_SECRET,
        settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
    )
    response = JSONResponse(
        content={"access_token": access_token, "token_type": "bearer"}
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api/auth",
        max_age=30 * 86400,
    )
    return response


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    new_access, new_refresh = await service.refresh_tokens(
        pool,
        refresh_token,
        settings.JWT_SECRET,
        settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
    )
    response = JSONResponse(content={"access_token": new_access, "token_type": "bearer"})
    response.set_cookie(
        "refresh_token",
        new_refresh,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api/auth",
        max_age=30 * 86400,
    )
    return response


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
) -> Response:
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        await service.invalidate_refresh_token(pool, refresh_token)
    response = Response(status_code=204)
    response.delete_cookie("refresh_token", path="/api/auth")
    return response
