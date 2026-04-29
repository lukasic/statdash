from fastapi import APIRouter, Depends

from app.core.app_config import get_app_config
from app.core.auth import ApiTokenUser, User, current_user_or_token
from app.core.cache import valkey
from app.services.dashboard import get_dashboard_data

router = APIRouter(prefix="/checks", tags=["checks"])


@router.get("")
async def list_checks(
    _: User | ApiTokenUser = Depends(current_user_or_token),
) -> dict:
    return await get_dashboard_data(get_app_config(), valkey)
