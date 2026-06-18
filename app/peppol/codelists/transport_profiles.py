from datetime import UTC, date, datetime
from typing import Any

from app.peppol.models import CodeListStatus


def load_transport_profiles(payload: dict[str, Any]) -> dict[str, CodeListStatus]:
    values: dict[str, CodeListStatus] = {}
    for row in payload.get("values", []):
        if not isinstance(row, dict):
            continue
        value = str(
            row.get("value") or row.get("transport-profile") or row.get("profile-id") or ""
        ).strip()
        if value:
            values[value] = _status(row)
    return values


def built_in_transport_profiles() -> dict[str, CodeListStatus]:
    return {
        "peppol-transport-as4-v2_0": CodeListStatus.valid,
        "busdox-transport-as2-ver1p0": CodeListStatus.valid,
    }


def _status(row: dict[str, Any]) -> CodeListStatus:
    removal_date = str(row.get("removal-date") or "").strip()
    parsed_removal_date = _parse_date(removal_date)
    if parsed_removal_date and parsed_removal_date < date.today():
        return CodeListStatus.removed
    state = str(row.get("state") or "").strip().lower()
    if state == "deprecated":
        return CodeListStatus.deprecated
    if state == "removed":
        return CodeListStatus.removed
    return CodeListStatus.valid


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).astimezone(UTC).date()
    except ValueError:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
