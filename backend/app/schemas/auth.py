from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GoogleLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential: str = Field(min_length=1, max_length=10000)


class PublicUser(BaseModel):
    id: UUID
    email: str
    display_name: str | None = None
    picture_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: PublicUser
