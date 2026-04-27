import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note


# ── ORM model tests ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def general_note(db_session: AsyncSession) -> Note:
    note = Note(
        source="icinga-prod",
        check_name="check_disk",
        host=None,
        content="Run df -h to check disk usage.",
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


@pytest_asyncio.fixture
async def host_note(db_session: AsyncSession) -> Note:
    note = Note(
        source="icinga-prod",
        check_name="check_disk",
        host="server01.example.com",
        content="Ticket #1234 opened with client for disk expansion.",
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


async def test_general_note_has_no_host(general_note: Note) -> None:
    assert general_note.host is None
    assert general_note.source == "icinga-prod"
    assert general_note.check_name == "check_disk"


async def test_host_note_has_host(host_note: Note) -> None:
    assert host_note.host == "server01.example.com"


async def test_note_defaults(general_note: Note) -> None:
    assert general_note.resolved is False
    assert isinstance(general_note.id, uuid.UUID)
    assert isinstance(general_note.created_at, datetime)


async def test_resolve_note(db_session: AsyncSession, general_note: Note) -> None:
    general_note.resolved = True
    await db_session.commit()
    await db_session.refresh(general_note)
    assert general_note.resolved is True


async def test_multiple_notes_per_check(db_session: AsyncSession) -> None:
    for i in range(3):
        db_session.add(Note(
            source="icinga-prod",
            check_name="check_disk",
            content=f"Note {i}",
        ))
    await db_session.commit()

    from sqlalchemy import select
    result = await db_session.execute(
        select(Note).where(Note.check_name == "check_disk")
    )
    notes = result.scalars().all()
    assert len(notes) == 3


# ── API helpers ───────────────────────────────────────────────────────────────

async def _register_and_login(client: AsyncClient) -> None:
    await client.post("/api/auth/register", json={
        "email": "user@example.com",
        "password": "password123",
    })
    await client.post("/api/auth/jwt/login", data={
        "username": "user@example.com",
        "password": "password123",
    })


# ── API tests ─────────────────────────────────────────────────────────────────

async def test_list_notes_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/notes", params={"source": "s", "check_name": "c"})
    assert response.status_code == 401


async def test_create_note_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/api/notes", json={
        "source": "s", "check_name": "c", "content": "x",
    })
    assert response.status_code == 401


async def test_create_general_note(client: AsyncClient) -> None:
    await _register_and_login(client)
    response = await client.post("/api/notes", json={
        "source": "icinga-prod",
        "check_name": "check_disk",
        "content": "General note",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["source"] == "icinga-prod"
    assert data["check_name"] == "check_disk"
    assert data["host"] is None
    assert data["content"] == "General note"
    assert data["resolved"] is False
    assert "id" in data
    assert data["author"] == "user@example.com"


async def test_create_host_specific_note(client: AsyncClient) -> None:
    await _register_and_login(client)
    response = await client.post("/api/notes", json={
        "source": "icinga-prod",
        "check_name": "check_disk",
        "host": "server01",
        "content": "Host-specific note",
    })
    assert response.status_code == 201
    assert response.json()["host"] == "server01"


async def test_list_notes_by_source_and_check(client: AsyncClient) -> None:
    await _register_and_login(client)
    await client.post("/api/notes", json={
        "source": "icinga-prod", "check_name": "check_disk", "content": "A",
    })
    await client.post("/api/notes", json={
        "source": "icinga-prod", "check_name": "check_load", "content": "B",
    })
    response = await client.get("/api/notes", params={
        "source": "icinga-prod", "check_name": "check_disk",
    })
    assert response.status_code == 200
    notes = response.json()
    assert len(notes) == 1
    assert notes[0]["content"] == "A"


async def test_list_notes_with_host_returns_general_and_host_specific(
    client: AsyncClient,
) -> None:
    await _register_and_login(client)
    await client.post("/api/notes", json={
        "source": "icinga-prod", "check_name": "check_disk", "content": "General",
    })
    await client.post("/api/notes", json={
        "source": "icinga-prod", "check_name": "check_disk",
        "host": "server01", "content": "Host note",
    })
    await client.post("/api/notes", json={
        "source": "icinga-prod", "check_name": "check_disk",
        "host": "server02", "content": "Other host note",
    })
    response = await client.get("/api/notes", params={
        "source": "icinga-prod", "check_name": "check_disk", "host": "server01",
    })
    notes = response.json()
    contents = {n["content"] for n in notes}
    assert "General" in contents
    assert "Host note" in contents
    assert "Other host note" not in contents


async def test_update_note_content(client: AsyncClient) -> None:
    await _register_and_login(client)
    create_resp = await client.post("/api/notes", json={
        "source": "icinga-prod", "check_name": "check_disk", "content": "Old content",
    })
    note_id = create_resp.json()["id"]
    patch_resp = await client.patch(f"/api/notes/{note_id}", json={"content": "New content"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["content"] == "New content"


async def test_resolve_note_via_api(client: AsyncClient) -> None:
    await _register_and_login(client)
    create_resp = await client.post("/api/notes", json={
        "source": "icinga-prod", "check_name": "check_disk", "content": "Note",
    })
    note_id = create_resp.json()["id"]
    patch_resp = await client.patch(f"/api/notes/{note_id}", json={"resolved": True})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["resolved"] is True


async def test_update_nonexistent_note(client: AsyncClient) -> None:
    await _register_and_login(client)
    fake_id = str(uuid.uuid4())
    response = await client.patch(f"/api/notes/{fake_id}", json={"content": "x"})
    assert response.status_code == 404


async def test_delete_note(client: AsyncClient) -> None:
    await _register_and_login(client)
    create_resp = await client.post("/api/notes", json={
        "source": "icinga-prod", "check_name": "check_disk", "content": "To delete",
    })
    note_id = create_resp.json()["id"]
    delete_resp = await client.delete(f"/api/notes/{note_id}")
    assert delete_resp.status_code == 204
    list_resp = await client.get("/api/notes", params={
        "source": "icinga-prod", "check_name": "check_disk",
    })
    assert list_resp.json() == []


async def test_delete_nonexistent_note(client: AsyncClient) -> None:
    await _register_and_login(client)
    fake_id = str(uuid.uuid4())
    response = await client.delete(f"/api/notes/{fake_id}")
    assert response.status_code == 404


async def test_resolved_notes_still_appear_in_list(client: AsyncClient) -> None:
    await _register_and_login(client)
    create_resp = await client.post("/api/notes", json={
        "source": "icinga-prod", "check_name": "check_disk", "content": "Archived",
    })
    note_id = create_resp.json()["id"]
    await client.patch(f"/api/notes/{note_id}", json={"resolved": True})
    list_resp = await client.get("/api/notes", params={
        "source": "icinga-prod", "check_name": "check_disk",
    })
    notes = list_resp.json()
    assert len(notes) == 1
    assert notes[0]["resolved"] is True
