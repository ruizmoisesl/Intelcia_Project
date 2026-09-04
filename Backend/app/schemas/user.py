from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import Role, ShiftId


class UserPublic(BaseModel):
    """Información básica del usuario (nunca el hash)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    role: Role
    shift: ShiftId


class UserBrief(BaseModel):
    """Usuario resumido para vistas de equipo y novedades."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: Role


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Role = Role.EMPLOYEE
    shift: ShiftId
    rotation_position: int | None = Field(default=None, ge=1, le=9999)
    is_active: bool = True


class UserUpdate(BaseModel):
    """Todos los campos opcionales: solo se aplican los presentes (exclude_unset)."""
    name: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: Role | None = None
    shift: ShiftId | None = None
    rotation_position: int | None = Field(default=None, ge=1, le=9999)
    is_active: bool | None = None


class UserAdminOut(BaseModel):
    """Vista de administración (nunca el hash)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    role: Role
    shift: ShiftId
    rotation_position: int | None
    is_active: bool
    created_at: datetime

class UserListOut(BaseModel):
    total: int
    items: list[UserAdminOut]