from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_name: str
    last_name: str
    email: EmailStr
    password: str = Field(min_length=8)


class CreateGuestUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_name: str
    last_name: str
    email: EmailStr
    phone: str


class CreateAdminUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8)
    phone: str | None = Field(default=None, min_length=6, max_length=30)


class ResolveUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    phone: str = Field(min_length=6, max_length=30)
    dni: str | None = Field(default=None, max_length=30)
