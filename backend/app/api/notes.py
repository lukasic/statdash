import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import current_active_user
from app.core.database import get_async_session
from app.models.note import Note
from app.models.user import User
from app.schemas.note import NoteCreate, NoteRead, NoteUpdate

router = APIRouter(prefix="/notes", tags=["notes"])


@router.get("", response_model=list[NoteRead])
async def list_notes(
    source: str = Query(...),
    check_name: str = Query(...),
    host: str | None = Query(None),
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(current_active_user),
) -> list[Note]:
    stmt = select(Note).where(Note.source == source, Note.check_name == check_name)
    if host is not None:
        stmt = stmt.where((Note.host == None) | (Note.host == host))  # noqa: E711
    stmt = stmt.order_by(Note.created_at)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=NoteRead, status_code=201)
async def create_note(
    body: NoteCreate,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> Note:
    note = Note(
        source=body.source,
        check_name=body.check_name,
        host=body.host,
        author=user.email,
        content=body.content,
    )
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


@router.patch("/{note_id}", response_model=NoteRead)
async def update_note(
    note_id: uuid.UUID,
    body: NoteUpdate,
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(current_active_user),
) -> Note:
    note = await session.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if body.content is not None:
        note.content = body.content
    if body.resolved is not None:
        note.resolved = body.resolved
    await session.commit()
    await session.refresh(note)
    return note


@router.delete("/{note_id}", status_code=204)
async def delete_note(
    note_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(current_active_user),
) -> None:
    note = await session.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    await session.delete(note)
    await session.commit()
