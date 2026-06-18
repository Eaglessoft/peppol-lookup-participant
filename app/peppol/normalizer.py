from urllib.parse import unquote

from fastapi import HTTPException

from app.peppol.models import ParticipantIdentifier

DEFAULT_PARTICIPANT_SCHEME = "iso6523-actorid-upis"


def normalize_participant_id(
    raw_value: str, default_scheme: str = DEFAULT_PARTICIPANT_SCHEME
) -> ParticipantIdentifier:
    value = unquote(raw_value).strip()
    if not value:
        raise HTTPException(status_code=400, detail="participant_id is required")

    if "::" in value:
        scheme, participant_value = value.split("::", 1)
    else:
        scheme, participant_value = default_scheme, value

    scheme = scheme.strip().lower()
    participant_value = participant_value.strip()

    if not scheme:
        raise HTTPException(status_code=400, detail="participant identifier scheme is required")
    if not participant_value:
        raise HTTPException(status_code=400, detail="participant identifier value is required")
    if ":" not in participant_value:
        raise HTTPException(
            status_code=422,
            detail=(
                "participant identifier value must include an ICD prefix, "
                "for example 0192:987654321"
            ),
        )

    icd, local_identifier = participant_value.split(":", 1)
    if not icd or not local_identifier:
        raise HTTPException(
            status_code=422,
            detail="participant identifier value must be formatted as ICD:identifier",
        )

    return ParticipantIdentifier(scheme=scheme, value=f"{icd.strip()}:{local_identifier.strip()}")


def normalize_environment_list(raw_value: str | None, defaults: list[str]) -> list[str]:
    source = raw_value or ",".join(defaults)
    environments = [
        environment.strip().lower() for environment in source.split(",") if environment.strip()
    ]
    allowed = {"prod", "test"}
    invalid = sorted(set(environments) - allowed)
    if invalid:
        detail = f"unsupported environments: {', '.join(invalid)}"
        raise HTTPException(status_code=400, detail=detail)
    return environments


def normalize_source_list(raw_value: str | None) -> set[str]:
    if not raw_value or raw_value.strip().lower() == "all":
        return {"directory", "sml", "smk", "smp", "lookup"}
    sources = {source.strip().lower() for source in raw_value.split(",") if source.strip()}
    allowed = {"directory", "sml", "smk", "smp", "lookup"}
    invalid = sorted(sources - allowed)
    if invalid:
        raise HTTPException(status_code=400, detail=f"unsupported sources: {', '.join(invalid)}")
    return sources
