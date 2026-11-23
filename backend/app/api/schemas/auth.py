"""Auth: bootstrap, login, sessione e cambio password."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    is_admin: bool
    created_at: datetime
    last_login_at: datetime | None = None


class BootstrapRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class BootstrapOut(BaseModel):
    user: UserOut


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)
