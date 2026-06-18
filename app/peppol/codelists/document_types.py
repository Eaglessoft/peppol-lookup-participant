from datetime import UTC, date, datetime
from typing import Any

from app.peppol.models import CodeListStatus


def load_document_types(payload: dict[str, Any]) -> dict[str, CodeListStatus]:
    return _load_value_statuses(payload)


def load_document_type_names(payload: dict[str, Any]) -> dict[str, str]:
    names: dict[str, str] = {}
    for row in payload.get("values", []):
        if not isinstance(row, dict):
            continue
        value = str(row.get("value") or row.get("document-type-identifier") or "").strip()
        name = str(row.get("name") or "").strip()
        if value and name:
            names[value] = name
    return names


def built_in_document_types() -> dict[str, CodeListStatus]:
    invoice = (
        "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##"
        "urn:cen.eu:en16931:2017#compliant#"
        "urn:fdc:peppol.eu:2017:poacc:billing:3.0::2.1"
    )
    credit_note = (
        "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2::CreditNote##"
        "urn:cen.eu:en16931:2017#compliant#"
        "urn:fdc:peppol.eu:2017:poacc:billing:3.0::2.1"
    )
    order = (
        "urn:oasis:names:specification:ubl:schema:xsd:Order-2::Order##"
        "urn:fdc:peppol.eu:poacc:trns:order:3::2.1"
    )
    return {
        invoice: CodeListStatus.valid,
        credit_note: CodeListStatus.valid,
        order: CodeListStatus.valid,
    }


def _load_value_statuses(payload: dict[str, Any]) -> dict[str, CodeListStatus]:
    values: dict[str, CodeListStatus] = {}
    for row in payload.get("values", []):
        if not isinstance(row, dict):
            continue
        value = str(
            row.get("value")
            or row.get("document-type-identifier")
            or row.get("process-id")
            or row.get("transport-profile")
            or ""
        ).strip()
        if value:
            values[value] = _status(row)
    return values


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
