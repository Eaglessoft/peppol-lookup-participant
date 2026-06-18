from app.peppol.codelists.cache import CachedCodeList, CodeListCache
from app.peppol.codelists.document_types import (
    built_in_document_types,
    load_document_type_names,
    load_document_types,
)
from app.peppol.codelists.participant_schemes import (
    CandidateValidation,
    ParticipantScheme,
    built_in_participant_schemes,
    candidate_is_valid,
    load_participant_schemes,
    normalize_identifier_for_scheme,
    validate_candidate,
)
from app.peppol.codelists.processes import built_in_processes, load_processes
from app.peppol.codelists.transport_profiles import (
    built_in_transport_profiles,
    load_transport_profiles,
)
from app.peppol.models import CodeListStatus


class CodeListEvaluator:
    def __init__(self, cache_dir: str) -> None:
        self.cache = CodeListCache(cache_dir)
        self.loaded_from_cache: dict[str, CachedCodeList] = {}
        self.participant_schemes = built_in_participant_schemes()
        self.document_types = built_in_document_types()
        self.document_type_names: dict[str, str] = {}
        self.processes = built_in_processes()
        self.transport_profiles = built_in_transport_profiles()
        self._load_cache()

    def _load_cache(self) -> None:
        participant_schemes = self.cache.read("participant_identifier_schemes")
        if participant_schemes:
            loaded = load_participant_schemes(participant_schemes.payload)
            if loaded:
                self.participant_schemes = loaded
                self.loaded_from_cache[participant_schemes.name] = participant_schemes

        document_types = self.cache.read("document_types")
        if document_types:
            loaded = load_document_types(document_types.payload)
            if loaded:
                self.document_types = loaded
                self.document_type_names = load_document_type_names(document_types.payload)
                self.loaded_from_cache[document_types.name] = document_types

        processes = self.cache.read("processes")
        if processes:
            loaded = load_processes(processes.payload)
            if loaded:
                self.processes = loaded
                self.loaded_from_cache[processes.name] = processes

        transport_profiles = self.cache.read("transport_profiles")
        if transport_profiles:
            loaded = load_transport_profiles(transport_profiles.payload)
            if loaded:
                self.transport_profiles = loaded
                self.loaded_from_cache[transport_profiles.name] = transport_profiles

    def evaluate_participant_scheme(self, code: str | None) -> CodeListStatus:
        if not code:
            return CodeListStatus.unsupported
        scheme = self.participant_schemes.get(code)
        return scheme.status if scheme else CodeListStatus.unsupported

    def evaluate_document_type(self, value: str) -> CodeListStatus:
        normalized_value = _strip_identifier_scheme(value, "busdox-docid-qns")
        if normalized_value in self.document_types:
            return self.document_types[normalized_value]
        if "document_types" not in self.loaded_from_cache:
            return CodeListStatus.unknown
        return CodeListStatus.unsupported

    def document_type_name(self, value: str) -> str | None:
        normalized_value = _strip_identifier_scheme(value, "busdox-docid-qns")
        return self.document_type_names.get(normalized_value)

    def evaluate_process(self, value: str) -> CodeListStatus:
        return self.processes.get(value, CodeListStatus.unsupported)

    def evaluate_transport_profile(self, value: str) -> CodeListStatus:
        return self.transport_profiles.get(value, CodeListStatus.unsupported)

    def participant_countries(self) -> list[str]:
        countries = {
            country
            for scheme in self.participant_schemes.values()
            if scheme.status in {CodeListStatus.valid, CodeListStatus.deprecated}
            for country in scheme.countries
        }
        return sorted(countries)

    def participant_candidates(
        self, country: str, identifier: str, identifier_type: str | None, max_candidates: int
    ) -> list[tuple[ParticipantScheme, str]]:
        country = country.upper()
        normalized_identifier = "".join(identifier.strip().split())
        identifier_type = identifier_type.lower() if identifier_type else None
        matches: list[tuple[ParticipantScheme, str]] = []

        for scheme in self.participant_schemes.values():
            country_match = not scheme.countries or country in scheme.countries
            type_match = (
                not identifier_type
                or identifier_type in scheme.identifier_types
                or identifier_type == scheme.code
            )
            status_match = scheme.status in {CodeListStatus.valid, CodeListStatus.deprecated}
            if (
                country_match
                and type_match
                and status_match
                and candidate_is_valid(scheme, normalized_identifier)
            ):
                candidate_identifier = normalize_identifier_for_scheme(
                    scheme.code, normalized_identifier
                )
                matches.append((scheme, f"{scheme.code}:{candidate_identifier}"))
            if len(matches) >= max_candidates:
                break
        return matches

    def participant_candidate_evaluations(
        self, country: str, identifier: str, identifier_type: str | None, max_candidates: int
    ) -> list[tuple[ParticipantScheme, str, CandidateValidation]]:
        country = country.upper()
        normalized_identifier = "".join(identifier.strip().split())
        identifier_type = identifier_type.lower() if identifier_type else None
        matches: list[tuple[ParticipantScheme, str, CandidateValidation]] = []

        for scheme in self.participant_schemes.values():
            country_match = not scheme.countries or country in scheme.countries
            type_match = (
                not identifier_type
                or identifier_type in scheme.identifier_types
                or identifier_type == scheme.code
            )
            if not country_match or not type_match:
                continue
            candidate_identifier = normalize_identifier_for_scheme(
                scheme.code, normalized_identifier
            )
            validation = validate_candidate(scheme, candidate_identifier)
            matches.append((scheme, f"{scheme.code}:{candidate_identifier}", validation))
            if len(matches) >= max_candidates:
                break
        return matches

    def metadata(self) -> dict[str, object]:
        return {
            "version": self._version(),
            "source": "cache" if self.loaded_from_cache else "built-in-starter",
            "cacheDir": str(self.cache.cache_dir),
            "items": {
                "participantSchemes": len(self.participant_schemes),
                "documentTypes": len(self.document_types),
                "processes": len(self.processes),
                "transportProfiles": len(self.transport_profiles),
            },
            "artifacts": {
                name: {
                    "path": str(cached.path),
                    "checksum": cached.checksum,
                    "fetchedAt": cached.fetched_at,
                    "entryCount": cached.payload.get("entry-count"),
                    "sourceUrl": cached.payload.get("_cache", {}).get("sourceUrl"),
                }
                for name, cached in self.loaded_from_cache.items()
            },
        }

    def _version(self) -> str:
        versions = {
            str(cached.payload.get("version"))
            for cached in self.loaded_from_cache.values()
            if cached.payload.get("version")
        }
        if len(versions) == 1:
            return versions.pop()
        if versions:
            return ",".join(sorted(versions))
        return "built-in-starter"


def _strip_identifier_scheme(value: str, scheme: str) -> str:
    prefix = f"{scheme}::"
    return value[len(prefix) :] if value.startswith(prefix) else value
