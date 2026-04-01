"""Pydantic schemas for auth endpoints."""

from pydantic import BaseModel, Field, field_validator


class RequestCodeInput(BaseModel):
    telegram_username: str = Field(
        min_length=2,
        max_length=64,
        description="Telegram username, with or without leading @",
    )

    @field_validator("telegram_username")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        """Strip leading @ and whitespace, lowercase."""
        return v.strip().lstrip("@").lower()


class VerifyCodeInput(BaseModel):
    telegram_username: str = Field(
        min_length=2,
        max_length=64,
        description="Telegram username, with or without leading @",
    )
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")

    @field_validator("telegram_username")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        """Strip leading @ and whitespace, lowercase."""
        return v.strip().lstrip("@").lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
