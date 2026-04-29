from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastmcp import FastMCP

from settings import settings

mcp = FastMCP("StatDash")

_STATDASH_URL = settings.statdash_url.rstrip("/")


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.statdash_api_token}"}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers=_headers(), base_url=_STATDASH_URL, timeout=30)


def _expiry_iso(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


@mcp.tool()
async def list_checks(status_filter: str | None = None) -> dict[str, Any]:
    """Return all monitoring checks grouped by dashboard section.

    Args:
        status_filter: Optional filter — 'warning', 'critical', or 'unknown'.
                       When omitted all non-OK checks are returned.
    """
    async with _client() as client:
        response = await client.get("/api/checks")
        response.raise_for_status()
        data: dict[str, Any] = response.json()

    if status_filter:
        for section in data.get("sections", []):
            section["checks"] = [
                c for c in section["checks"] if c["status"] == status_filter
            ]

    return data


@mcp.tool()
async def get_check_notes(source: str, check_name: str, host: str | None = None) -> list[dict[str, Any]]:
    """Return notes attached to a monitoring check.

    Args:
        source: Source name as defined in the StatDash config (e.g. 'icinga-prod').
        check_name: Name of the check/service (e.g. 'check_disk').
        host: Optional host name to narrow results to host-specific notes.
    """
    params: dict[str, str] = {"source": source, "check_name": check_name}
    if host:
        params["host"] = host
    async with _client() as client:
        response = await client.get("/api/notes", params=params)
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def add_note(source: str, check_name: str, content: str, host: str | None = None) -> dict[str, Any]:
    """Add a note to a monitoring check.

    Args:
        source: Source name as defined in the StatDash config.
        check_name: Name of the check/service.
        content: Text content of the note.
        host: Optional — when provided the note is scoped to this specific host.
              Omit to create a general note matching the check across all hosts.
    """
    async with _client() as client:
        response = await client.post(
            "/api/notes",
            json={"source": source, "check_name": check_name, "content": content, "host": host},
        )
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def acknowledge_check(
    source: str,
    check_id: str,
    comment: str,
    expiry_hours: float = 2.0,
) -> str:
    """Acknowledge a failing check in Icinga2 to suppress notifications.

    Args:
        source: Icinga2 source name as defined in the StatDash config.
        check_id: Check identifier in the format 'hostname!service_name'.
        comment: Reason for the acknowledgement.
        expiry_hours: How many hours until the ACK expires (default 2).
    """
    async with _client() as client:
        response = await client.post(
            "/api/actions/acknowledge",
            json={
                "source": source,
                "check_id": check_id,
                "comment": comment,
                "expiry_at": _expiry_iso(expiry_hours),
            },
        )
        response.raise_for_status()
    return f"Acknowledged {check_id} on {source} for {expiry_hours}h."


@mcp.tool()
async def schedule_downtime(
    source: str,
    check_id: str,
    comment: str,
    expiry_hours: float = 2.0,
) -> str:
    """Schedule a downtime window for a check in Icinga2.

    Args:
        source: Icinga2 source name as defined in the StatDash config.
        check_id: Check identifier in the format 'hostname!service_name'.
        comment: Reason for the downtime.
        expiry_hours: Duration of the downtime in hours (default 2).
    """
    async with _client() as client:
        response = await client.post(
            "/api/actions/schedule-downtime",
            json={
                "source": source,
                "check_id": check_id,
                "comment": comment,
                "expiry_at": _expiry_iso(expiry_hours),
            },
        )
        response.raise_for_status()
    return f"Scheduled downtime for {check_id} on {source} for {expiry_hours}h."


@mcp.tool()
async def remove_acknowledgement(source: str, check_id: str) -> str:
    """Remove an existing acknowledgement from a check in Icinga2.

    Args:
        source: Icinga2 source name as defined in the StatDash config.
        check_id: Check identifier in the format 'hostname!service_name'.
    """
    async with _client() as client:
        response = await client.post(
            "/api/actions/remove-ack",
            json={"source": source, "check_id": check_id},
        )
        response.raise_for_status()
    return f"Removed acknowledgement for {check_id} on {source}."


@mcp.tool()
async def remove_downtime(source: str, check_id: str) -> str:
    """Remove an active downtime from a check in Icinga2.

    Args:
        source: Icinga2 source name as defined in the StatDash config.
        check_id: Check identifier in the format 'hostname!service_name'.
    """
    async with _client() as client:
        response = await client.post(
            "/api/actions/remove-downtime",
            json={"source": source, "check_id": check_id},
        )
        response.raise_for_status()
    return f"Removed downtime for {check_id} on {source}."


@mcp.tool()
async def force_recheck(source: str, check_id: str) -> str:
    """Force an immediate recheck of a service in Icinga2.

    Args:
        source: Icinga2 source name as defined in the StatDash config.
        check_id: Check identifier in the format 'hostname!service_name'.
    """
    async with _client() as client:
        response = await client.post(
            "/api/actions/recheck",
            json={"source": source, "check_id": check_id},
        )
        response.raise_for_status()
    return f"Triggered recheck for {check_id} on {source}."


if __name__ == "__main__":
    transport = settings.mcp_transport
    if transport == "sse":
        mcp.run(transport="sse", host=settings.mcp_host, port=settings.mcp_port)
    else:
        mcp.run(transport="stdio")
