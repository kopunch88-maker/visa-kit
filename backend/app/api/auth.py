"""
Auth router — login с bcrypt + JWT.

Pack 11: production-ready аутентификация по email + password.
- POST /api/auth/login — email + password → JWT
- GET  /api/auth/me   — проверка текущего пользователя по JWT

Также экспортирует FastAPI dependencies для других роутеров:
- get_current_user — возвращает User по Bearer токену
- current_user_id  — возвращает int id текущего юзера
- require_manager  — проверяет роль manager или admin
- require_admin    — проверяет роль admin

Создание пользователей — через scripts/create_admin.py (CLI).
"""

from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from app.db.session import get_session
from app.models import User, UserRole
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


# ============================================================================
# Pydantic schemas
# ============================================================================

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class MeResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    role: Optional[str] = None


# ============================================================================
# JWT helpers
# ============================================================================

def _get_secret() -> str:
    """Возвращает JWT secret (имя поля может быть jwt_secret или secret_key)."""
    if hasattr(settings, "jwt_secret") and settings.jwt_secret:
        return settings.jwt_secret
    if hasattr(settings, "secret_key") and settings.secret_key:
        return settings.secret_key
    raise RuntimeError("JWT secret is not configured (set JWT_SECRET in .env)")


def _create_jwt(user_id: int, email: str) -> str:
    """JWT валиден 7 дней."""
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": datetime.utcnow() + timedelta(days=7),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, _get_secret(), algorithm="HS256")


def _decode_jwt(token: str) -> dict:
    """Возвращает payload или кидает HTTPException."""
    try:
        return jwt.decode(token, _get_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired, please login again")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")


# ============================================================================
# Password helpers
# ============================================================================

def _verify_password(plain: str, hashed: str) -> bool:
    """bcrypt проверка."""
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def hash_password(plain: str) -> str:
    """Хеш для нового пароля. Используется в scripts/create_admin.py"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


# ============================================================================
# FastAPI dependencies (используются в других роутерах)
# ============================================================================

def get_current_user(
    authorization: str = Header(None),
    session: Session = Depends(get_session),
) -> User:
    """
    Извлекает User из JWT в Authorization header.
    Кидает 401 если токена нет или он невалидный.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")

    token = authorization.split(" ", 1)[1]
    payload = _decode_jwt(token)
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(401, "Invalid token payload")

    user = session.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "User not found or inactive")

    return user


def current_user_id(user: User = Depends(get_current_user)) -> int:
    """Возвращает id текущего user. Простой shortcut над get_current_user."""
    return user.id


def _check_role(user: User, allowed_roles) -> None:
    """Проверяет что роль user входит в allowed_roles. Иначе 403."""
    user_role = user.role
    # role может быть Enum или строкой — нормализуем
    if hasattr(user_role, "value"):
        user_role_str = user_role.value
    else:
        user_role_str = str(user_role).lower()

    allowed_strs = []
    for r in allowed_roles:
        if hasattr(r, "value"):
            allowed_strs.append(r.value)
        else:
            allowed_strs.append(str(r).lower())

    if user_role_str not in allowed_strs:
        raise HTTPException(
            403,
            f"Forbidden: requires role in {allowed_strs}, got {user_role_str}",
        )


def require_manager(user: User = Depends(get_current_user)) -> User:
    """Требует роль manager или admin."""
    _check_role(user, [UserRole.MANAGER, UserRole.ADMIN])
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Требует роль admin."""
    _check_role(user, [UserRole.ADMIN])
    return user


# ============================================================================
# Routes
# ============================================================================

@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)):
    """
    Login by email + password.
    Returns JWT valid for 7 days.
    """
    user = session.exec(
        select(User).where(User.email == payload.email.lower())
    ).first()

    if not user or not user.is_active:
        # Намеренно общая ошибка — не палим существование email
        raise HTTPException(401, "Неверный email или пароль")

    if not _verify_password(payload.password, user.password_hash or ""):
        raise HTTPException(401, "Неверный email или пароль")

    # Update last_login_at
    user.last_login_at = datetime.utcnow()
    session.add(user)
    session.commit()

    token = _create_jwt(user.id, user.email)

    role_value = user.role.value if hasattr(user.role, "value") else str(user.role)

    return LoginResponse(
        access_token=token,
        user={
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": role_value,
        },
    )


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)):
    """Возвращает текущего пользователя по JWT в Authorization header."""
    role_value = user.role.value if hasattr(user.role, "value") else str(user.role)
    return MeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=role_value,
    )