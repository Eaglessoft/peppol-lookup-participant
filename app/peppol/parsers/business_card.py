from typing import Any

from app.peppol.models import BusinessEntity, DirectoryResult


def business_entities_from_directory(directory: DirectoryResult) -> list[BusinessEntity]:
    payload = directory.businessCard or {}
    source_entities = _source_entities(payload)
    if isinstance(source_entities, dict):
        source_entities = (
            source_entities.get("businessEntity") or source_entities.get("entities") or []
        )
    if isinstance(source_entities, dict):
        source_entities = [source_entities]
    if not isinstance(source_entities, list):
        return []

    entities: list[BusinessEntity] = []
    for entity in source_entities:
        if not isinstance(entity, dict):
            continue
        entities.append(
            BusinessEntity(
                name=_first_value(entity, "name", "Name"),
                countryCode=_first_value(entity, "countryCode", "CountryCode"),
                geoInfo=_first_value(entity, "geoInfo", "geographicalInformation"),
                identifiers=_list_value(
                    entity,
                    "identifiers",
                    "additionalIdentifiers",
                    "additionalIdentifier",
                    "AdditionalIdentifiers",
                ),
                websites=_list_value(
                    entity,
                    "websites",
                    "websiteURIs",
                    "websiteUris",
                    "websiteURI",
                    "websiteUri",
                    "WebsiteURIs",
                ),
                contacts=_list_value(entity, "contacts", "contact", "Contacts"),
                additionalInfo=_first_value(entity, "additionalInfo", "additionalInformation"),
                regDate=_first_value(entity, "regDate", "registrationDate"),
            )
        )
    return entities


def _first_value(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return _coerce_scalar(mapping[key])
    return None


def _list_value(mapping: dict[str, Any], *keys: str) -> list[Any]:
    value = _first_raw_value(mapping, *keys)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _source_entities(payload: dict[str, Any]) -> Any:
    direct_entities = (
        payload.get("businessEntities")
        or payload.get("entities")
        or payload.get("BusinessEntities")
    )
    if direct_entities:
        return direct_entities

    matches = payload.get("matches")
    if not isinstance(matches, list):
        return []

    entities: list[Any] = []
    for match in matches:
        if not isinstance(match, dict):
            continue
        match_entities = match.get("entities") or match.get("businessEntities")
        if isinstance(match_entities, list):
            entities.extend(match_entities)
        elif isinstance(match_entities, dict):
            entities.append(match_entities)
    return entities


def _coerce_scalar(value: Any) -> Any:
    if isinstance(value, list):
        if not value:
            return None
        return _coerce_scalar(value[0])
    if isinstance(value, dict):
        for key in ("name", "value", "text"):
            if key in value:
                return _coerce_scalar(value[key])
    return value


def _first_raw_value(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None
