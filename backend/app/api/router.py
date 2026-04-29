from fastapi import APIRouter

from app.api.actions import router as actions_router
from app.api.checks import router as checks_router
from app.api.notes import router as notes_router
from app.api.sso import router as sso_router
from app.core.auth import fastapi_users, auth_backend
from app.schemas.user import UserRead, UserCreate, UserUpdate

api_router = APIRouter()
api_router.include_router(actions_router)
api_router.include_router(checks_router)
api_router.include_router(notes_router)
api_router.include_router(sso_router)

api_router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)

api_router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)

api_router.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/auth",
    tags=["auth"],
)

api_router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)
