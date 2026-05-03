from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.app_config import Icinga2SourceConfig, PrometheusSourceConfig, get_app_config
from app.core.auth import ApiTokenUser, User, current_user_or_token
from app.services.backends.icinga2 import Icinga2Backend
from app.services.backends.prometheus import PrometheusBackend

router = APIRouter(prefix="/actions", tags=["actions"])


class RecheckRequest(BaseModel):
    source: str
    check_id: str


class AckRequest(BaseModel):
    source: str
    check_id: str
    comment: str
    expiry_at: str | None = None  # ISO 8601 UTC datetime


class DowntimeRequest(BaseModel):
    source: str
    check_id: str
    comment: str
    expiry_at: str  # ISO 8601 UTC datetime


def _resolve_icinga_source(source: str) -> Icinga2SourceConfig:
    config = get_app_config()
    source_cfg = next((s for s in config.sources if s.name == source), None)
    if not source_cfg or not isinstance(source_cfg, Icinga2SourceConfig):
        raise HTTPException(status_code=404, detail="Icinga2 source not found")
    return source_cfg


def _resolve_source(source: str):
    config = get_app_config()
    source_cfg = next((s for s in config.sources if s.name == source), None)
    if not source_cfg:
        raise HTTPException(status_code=404, detail=f"Source '{source}' not found")
    return source_cfg


def _split_check_id(check_id: str) -> tuple[str, str]:
    parts = check_id.split("!", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=422, detail="Invalid check_id: expected host!service")
    return parts[0], parts[1]


@router.post("/recheck", status_code=204)
async def recheck(
    body: RecheckRequest,
    _: Annotated[User | ApiTokenUser, Depends(current_user_or_token)],
) -> None:
    source_cfg = _resolve_icinga_source(body.source)
    host, service = _split_check_id(body.check_id)
    await Icinga2Backend(source_cfg).recheck(host, service)


@router.post("/acknowledge", status_code=204)
async def acknowledge(
    body: AckRequest,
    user: Annotated[User | ApiTokenUser, Depends(current_user_or_token)],
) -> None:
    source_cfg = _resolve_icinga_source(body.source)
    host, service = _split_check_id(body.check_id)
    expiry_at = datetime.fromisoformat(body.expiry_at).replace(tzinfo=timezone.utc) if body.expiry_at else None
    await Icinga2Backend(source_cfg).acknowledge(
        host=host, service=service, author=user.email, comment=body.comment, expiry_at=expiry_at,
    )


@router.post("/schedule-downtime", status_code=204)
async def schedule_downtime(
    body: DowntimeRequest,
    user: Annotated[User | ApiTokenUser, Depends(current_user_or_token)],
) -> None:
    source_cfg = _resolve_source(body.source)
    expiry_at = datetime.fromisoformat(body.expiry_at).replace(tzinfo=timezone.utc)
    duration_seconds = max(60, int((expiry_at - datetime.now(timezone.utc)).total_seconds()))

    if isinstance(source_cfg, Icinga2SourceConfig):
        host, service = _split_check_id(body.check_id)
        await Icinga2Backend(source_cfg).schedule_downtime(
            host=host, service=service, author=user.email, comment=body.comment, duration_seconds=duration_seconds,
        )
    elif isinstance(source_cfg, PrometheusSourceConfig):
        await PrometheusBackend(source_cfg).create_silence(
            fingerprint=body.check_id, author=user.email, comment=body.comment, ends_at=expiry_at,
        )
    else:
        raise HTTPException(status_code=422, detail=f"schedule-downtime not supported for source type '{source_cfg.type}'")


@router.post("/remove-ack", status_code=204)
async def remove_ack(
    body: RecheckRequest,
    _: Annotated[User | ApiTokenUser, Depends(current_user_or_token)],
) -> None:
    source_cfg = _resolve_icinga_source(body.source)
    host, service = _split_check_id(body.check_id)
    await Icinga2Backend(source_cfg).remove_ack(host, service)


@router.post("/remove-downtime", status_code=204)
async def remove_downtime(
    body: RecheckRequest,
    _: Annotated[User | ApiTokenUser, Depends(current_user_or_token)],
) -> None:
    source_cfg = _resolve_source(body.source)
    if isinstance(source_cfg, Icinga2SourceConfig):
        host, service = _split_check_id(body.check_id)
        await Icinga2Backend(source_cfg).remove_downtime(host, service)
    elif isinstance(source_cfg, PrometheusSourceConfig):
        await PrometheusBackend(source_cfg).remove_silence(body.check_id)
    else:
        raise HTTPException(status_code=422, detail=f"remove-downtime not supported for source type '{source_cfg.type}'")
