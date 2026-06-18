import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from app.peppol.models import CodeListStatus


@dataclass(frozen=True)
class ParticipantScheme:
    code: str
    name: str
    countries: tuple[str, ...] = ()
    identifier_types: tuple[str, ...] = ()
    status: CodeListStatus = CodeListStatus.valid
    validation_regex: str | None = None
    source_state: str | None = None
    removal_date: str | None = None


@dataclass(frozen=True)
class CandidateValidation:
    valid: bool
    status: str
    reason: str | None = None


def load_participant_schemes(payload: dict[str, Any]) -> dict[str, ParticipantScheme]:
    schemes: dict[str, ParticipantScheme] = {}
    for row in payload.get("values", []):
        if not isinstance(row, dict):
            continue
        code = str(row.get("iso6523") or "").strip()
        if not code:
            continue
        country = str(row.get("country") or "").strip().upper()
        countries = () if country in {"", "INTERNATIONAL"} else (country,)
        schemes[code] = ParticipantScheme(
            code=code,
            name=str(row.get("scheme-name") or row.get("schemeid") or code),
            countries=countries,
            identifier_types=_identifier_types(row),
            status=_status(row),
            validation_regex=_validation_regex(str(row.get("validation-rules") or "")),
            source_state=str(row.get("state") or "") or None,
            removal_date=str(row.get("removal-date") or "") or None,
        )
    return schemes


def built_in_participant_schemes() -> dict[str, ParticipantScheme]:
    return {
        scheme.code: scheme
        for scheme in [
            ParticipantScheme(
                "0007",
                "Swedish organisation number",
                ("SE",),
                ("company_number",),
                validation_regex="[0-9]{10}",
            ),
            ParticipantScheme("0009", "DUNS number", (), ("duns",), validation_regex="[0-9]{9}"),
            ParticipantScheme("0088", "GS1 GLN", (), ("gln",), validation_regex="[0-9]{13}"),
            ParticipantScheme(
                "0106",
                "Dutch Chamber of Commerce",
                ("NL",),
                ("company_number",),
                validation_regex="[0-9]{8}|[0-9]{17}",
            ),
            ParticipantScheme(
                "0151",
                "Australian Business Number",
                ("AU",),
                ("company_number",),
                validation_regex="[0-9]{11}",
            ),
            ParticipantScheme(
                "0192",
                "Norwegian organisation number",
                ("NO",),
                ("company_number",),
                validation_regex="[0-9]{9}",
            ),
            ParticipantScheme(
                "0208",
                "Belgian enterprise number",
                ("BE",),
                ("company_number", "vat"),
                validation_regex="[0-9]{10}",
            ),
            ParticipantScheme(
                "0211", "Finnish organization identifier", ("FI",), ("company_number",)
            ),
            ParticipantScheme("0215", "German Leitweg-ID", ("DE",), ("company_number",)),
            ParticipantScheme(
                "0216", "German VAT number", ("DE",), ("vat",), validation_regex="DE[0-9]{9}"
            ),
            ParticipantScheme(
                "9908",
                "Norwegian organization number",
                ("NO",),
                ("company_number",),
                validation_regex="[0-9]{9}",
            ),
            ParticipantScheme("9910", "Hungarian VAT number", ("HU",), ("vat",)),
            ParticipantScheme("9913", "Business Registers Network", (), ("company_number",)),
            ParticipantScheme("9914", "Austrian VAT number", ("AT",), ("vat",)),
            ParticipantScheme("9915", "Norwegian VAT number", ("NO",), ("vat",)),
            ParticipantScheme("9917", "Swiss VAT number", ("CH",), ("vat",)),
            ParticipantScheme(
                "9925", "Belgian VAT number", ("BE",), ("vat",), validation_regex="(BE)?[0-9]{10}"
            ),
            ParticipantScheme("9930", "Polish VAT number", ("PL",), ("vat",)),
            ParticipantScheme("9944", "Spanish VAT number", ("ES",), ("vat",)),
            ParticipantScheme("9957", "French VAT number", ("FR",), ("vat",)),
        ]
    }


def validate_candidate(scheme: ParticipantScheme, identifier: str) -> CandidateValidation:
    normalized = normalize_identifier_for_scheme(scheme.code, identifier)
    if scheme.status == CodeListStatus.removed:
        return CandidateValidation(False, "candidate_rejected", "scheme has been removed")
    if not scheme.validation_regex:
        return CandidateValidation(True, "candidate_valid")
    if re.fullmatch(scheme.validation_regex, normalized) is None:
        return CandidateValidation(False, "candidate_rejected", "identifier does not match regex")

    check_digit_validators = {
        "0007": _valid_luhn,
        "0088": _valid_gln,
        "0151": _valid_abn,
        "0192": _valid_norwegian_org_number,
        "0208": _valid_belgian_enterprise_number,
        "9908": _valid_norwegian_org_number,
        "9925": _valid_belgian_enterprise_number,
    }
    validator = check_digit_validators.get(scheme.code)
    if validator and not validator(normalized):
        return CandidateValidation(False, "candidate_rejected", "check digit validation failed")
    return CandidateValidation(True, "candidate_valid")


def candidate_is_valid(scheme: ParticipantScheme, identifier: str) -> bool:
    return validate_candidate(scheme, identifier).valid


def normalize_identifier_for_scheme(scheme_code: str, identifier: str) -> str:
    normalized = "".join(identifier.strip().split()).replace("-", "").replace(".", "")
    if scheme_code == "9925" and normalized.upper().startswith("BE"):
        return normalized[2:]
    return normalized.upper()


def _status(row: dict[str, Any]) -> CodeListStatus:
    removal_date = str(row.get("removal-date") or "").strip()
    if removal_date and _parse_date(removal_date) and _parse_date(removal_date) < date.today():
        return CodeListStatus.removed
    state = str(row.get("state") or "").strip().lower()
    if state == "deprecated":
        return CodeListStatus.deprecated
    if state == "removed":
        return CodeListStatus.removed
    return CodeListStatus.valid


def _parse_date(value: str) -> date | None:
    try:
        return datetime.fromisoformat(value).astimezone(UTC).date()
    except ValueError:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None


def _identifier_types(row: dict[str, Any]) -> tuple[str, ...]:
    text = " ".join(
        str(row.get(key) or "").lower()
        for key in ("schemeid", "scheme-name", "issuing-agency", "usage")
    )
    values = []
    if "vat" in text:
        values.append("vat")
    if "gln" in text or "global location number" in text:
        values.append("gln")
    if "duns" in text or "d-u-n-s" in text:
        values.append("duns")
    if not values:
        values.append("company_number")
    return tuple(dict.fromkeys(values))


def _validation_regex(validation_rules: str) -> str | None:
    match = re.search(r"RegEx:\s*(.+)", validation_rules)
    if not match:
        return None
    regex = match.group(1).strip()
    return regex if regex and "\n" not in regex else regex.splitlines()[0]


def _valid_luhn(value: str) -> bool:
    if not value.isdigit():
        return False
    total = 0
    reverse_digits = [int(character) for character in reversed(value)]
    for index, digit in enumerate(reverse_digits):
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _valid_gln(value: str) -> bool:
    if not value.isdigit():
        return False
    digits = [int(character) for character in value]
    check_digit = digits[-1]
    total = 0
    for index, digit in enumerate(reversed(digits[:-1])):
        total += digit * (3 if index % 2 == 0 else 1)
    return (10 - (total % 10)) % 10 == check_digit


def _valid_norwegian_org_number(value: str) -> bool:
    if not value.isdigit() or len(value) != 9:
        return False
    weights = [3, 2, 7, 6, 5, 4, 3, 2]
    total = sum(int(digit) * weight for digit, weight in zip(value[:8], weights, strict=True))
    remainder = total % 11
    check_digit = 11 - remainder
    if check_digit == 11:
        check_digit = 0
    if check_digit == 10:
        return False
    return check_digit == int(value[-1])


def _valid_belgian_enterprise_number(value: str) -> bool:
    if not value.isdigit() or len(value) != 10:
        return False
    body = int(value[:8])
    check = int(value[8:])
    expected = 97 - (body % 97)
    if expected == 0:
        expected = 97
    return check == expected


def _valid_abn(value: str) -> bool:
    if not value.isdigit() or len(value) != 11:
        return False
    weights = [10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19]
    digits = [int(character) for character in value]
    digits[0] -= 1
    total = sum(digit * weight for digit, weight in zip(digits, weights, strict=True))
    return total % 89 == 0
