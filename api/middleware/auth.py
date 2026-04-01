"""FastAPI dependency for JWT authentication."""

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from api.auth.service import decode_access_token
from api.config import Settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/verify-code")


def _get_settings() -> Settings:
    return Settings()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    settings: Settings = Depends(_get_settings),
) -> dict:
    """Extract and verify JWT from Authorization: Bearer header."""
    try:
        claims = decode_access_token(token, settings.JWT_SECRET)
    except HTTPException:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return claims
