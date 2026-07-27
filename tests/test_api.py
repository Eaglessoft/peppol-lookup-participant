import asyncio
import os
import shutil
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.v1.lookup_routes import get_orchestrator
from app.main import create_app
from app.peppol.codelists.cache import CodeListCache
from app.peppol.codelists.document_types import load_document_types
from app.peppol.codelists.evaluator import CodeListEvaluator
from app.peppol.codelists.participant_schemes import validate_candidate
from app.peppol.codelists.processes import load_processes
from app.peppol.codelists.transport_profiles import load_transport_profiles
from app.peppol.company_lookup import (
    _directory_participant_values,
    _filter_directory_matches_by_icd,
)
from app.peppol.models import (
    CodeListStatus,
    DirectoryResult,
    LightLookupResponse,
    LookupMode,
    ParticipantIdentifier,
    SmlResult,
    SmpResult,
)
from app.peppol.normalizer import normalize_participant_id
from app.peppol.orchestrator import LookupOrchestrator, _with_required_source_dependencies
from app.peppol.parsers.business_card import business_entities_from_directory
from app.peppol.parsers.service_group import parse_service_group
from app.peppol.parsers.service_metadata import parse_service_metadata
from app.peppol.sources.directory import (
    _filter_payload_to_participant,
    _payload_has_exact_participant,
    participant_values_from_directory,
)
from app.peppol.sources.openpeppol_lookup import OpenPeppolLookupClient
from app.peppol.sources.sml_dns import build_sml_query_name, extract_smp_base_url
from app.shared.config import Settings


def test_api_info_returns_service_metadata() -> None:
    app = create_app(Settings())
    client = TestClient(app)

    response = client.get("/api")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "Peppol Lookup API"
    assert body["status"] == "running"

def test_health_returns_ok() -> None:
    app = create_app(Settings())
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_redirects_to_embed_ui() -> None:
    app = create_app(Settings())
    client = TestClient(app)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/embed/sample.html"


def test_root_redirect_honors_context_path() -> None:
    app = create_app(Settings(app_context_path="/peppol-lookup"))
    client = TestClient(app)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/peppol-lookup/embed/sample.html"

def test_redoc_is_disabled_and_swagger_remains_available() -> None:
    app = create_app(Settings())
    client = TestClient(app)

    docs_response = client.get("/docs")
    redoc_response = client.get("/redoc")

    assert docs_response.status_code == 200
    assert redoc_response.status_code == 404

def test_participant_lookup_route_uses_orchestrator_contract() -> None:
    class FakeOrchestrator:
        async def lookup(self, **kwargs):
            assert kwargs["participant"] == ParticipantIdentifier(value="0192:987654321")
            assert kwargs["mode"] == "light"
            assert kwargs["environments"] == ["prod"]
            assert kwargs["sources"] == {"directory"}
            return LightLookupResponse(participantIdentifier=kwargs["participant"])

    app = create_app(Settings())
    app.dependency_overrides[get_orchestrator] = lambda: FakeOrchestrator()
    client = TestClient(app)

    response = client.get(
        "/api/v1/participants/iso6523-actorid-upis%3A%3A0192%3A987654321"
        "?environments=prod&sources=directory"
    )

    assert response.status_code == 200
    assert response.json()["participantIdentifier"] == {
        "scheme": "iso6523-actorid-upis",
        "value": "0192:987654321",
    }

def test_normalize_participant_id_accepts_default_scheme() -> None:
    participant = normalize_participant_id("0192:987654321")

    assert participant.scheme == "iso6523-actorid-upis"
    assert participant.value == "0192:987654321"
    assert participant.icd == "0192"
    assert participant.local_identifier == "987654321"

def test_service_group_and_metadata_parser_extract_capabilities() -> None:
    service_group, refs = parse_service_group(
        """
        <ServiceGroup>
          <ParticipantIdentifier scheme="iso6523-actorid-upis">
            0192:987654321
          </ParticipantIdentifier>
          <ServiceMetadataReferenceCollection>
            <ServiceMetadataReference href="unused">
              <DocumentTypeIdentifier scheme="busdox-docid-qns">doc-1</DocumentTypeIdentifier>
            </ServiceMetadataReference>
          </ServiceMetadataReferenceCollection>
        </ServiceGroup>
        """
    )

    service = parse_service_metadata(
        """
        <ServiceMetadata>
          <ServiceInformation>
            <ProcessList>
              <Process>
                <ProcessIdentifier scheme="cenbii-procid-ubl">proc-1</ProcessIdentifier>
                <ServiceEndpointList>
                  <Endpoint transportProfile="peppol-transport-as4-v2_0">
                    <EndpointReference><Address>https://ap.example/as4</Address></EndpointReference>
                    <ServiceDescription>Example AP</ServiceDescription>
                    <TechnicalContactUrl>support@example.test</TechnicalContactUrl>
                  </Endpoint>
                </ServiceEndpointList>
              </Process>
            </ProcessList>
          </ServiceInformation>
        </ServiceMetadata>
        """,
        "doc-1",
        CodeListEvaluator("data/codelists").evaluate_document_type("doc-1"),
        None,
        CodeListEvaluator("data/codelists").evaluate_process,
        CodeListEvaluator("data/codelists").evaluate_transport_profile,
        False,
        1024,
    )

    assert service_group["participantIdentifier"]["value"] == "0192:987654321"
    assert refs == ["doc-1"]
    service_group_from_href, refs_from_href = parse_service_group(
        """
        <ServiceGroup>
          <ParticipantIdentifier scheme="iso6523-actorid-upis">
            0192:987654321
          </ParticipantIdentifier>
          <ServiceMetadataReferenceCollection>
            <ServiceMetadataReference
              href="https://smp.example/p/services/busdox-docid-qns%3A%3Adoc-2" />
          </ServiceMetadataReferenceCollection>
        </ServiceGroup>
        """
    )
    assert refs_from_href == ["busdox-docid-qns::doc-2"]
    assert service_group_from_href["documentReferenceUrls"]["busdox-docid-qns::doc-2"].endswith(
        "busdox-docid-qns%3A%3Adoc-2"
    )
    assert service.processes[0].processIdentifier.value == "proc-1"
    assert service.processes[0].processIdentifier.codeListStatus == CodeListStatus.unsupported
    assert service.processes[0].endpoints[0].endpointReference == "https://ap.example/as4"
    assert service.processes[0].endpoints[0].certificate["fingerprints"]["sha256"] is None

def test_service_group_parser_ignores_null_document_references() -> None:
    service_group, refs = parse_service_group(
        """
        <ServiceGroup>
          <ServiceMetadataReferenceCollection>
            <ServiceMetadataReference
              href="https://smp.example/p/services/busdox-docid-qns%3A%3Anull" />
            <ServiceMetadataReference
              href="https://smp.example/p/services/busdox-docid-qns%3A%3Adoc-1" />
          </ServiceMetadataReferenceCollection>
        </ServiceGroup>
        """
    )

    assert refs == ["busdox-docid-qns::doc-1"]
    assert service_group["documentReferences"] == ["busdox-docid-qns::doc-1"]

def test_directory_search_match_must_equal_candidate_participant() -> None:
    payload = {
        "matches": [
            {"participantID": "iso6523-actorid-upis::9913:000076-vidapilot.be0123456749"}
        ]
    }

    assert not _payload_has_exact_participant(
        payload, ParticipantIdentifier(value="9913:0123456749")
    )
    assert _payload_has_exact_participant(
        payload, ParticipantIdentifier(value="9913:000076-vidapilot.be0123456749")
    )

def test_directory_search_payload_is_filtered_to_exact_participant() -> None:
    payload = {
        "total-result-count": 2,
        "matches": [
            {
                "participantID": "iso6523-actorid-upis::9925:0123456749",
                "entities": [{"name": "Sajini"}],
            },
            {
                "participantID": "iso6523-actorid-upis::9925:be0123456749",
                "entities": [{"name": "Duy"}],
            },
        ],
    }

    filtered = _filter_payload_to_participant(
        payload, ParticipantIdentifier(value="9925:0123456749")
    )

    assert filtered["total-result-count"] == 1
    assert filtered["matches"][0]["entities"][0]["name"] == "Sajini"

def test_directory_participant_values_are_extracted_for_lookup() -> None:
    payload = {
        "matches": [
            {"participantID": "iso6523-actorid-upis::9925:be0123456749"},
            {"participantID": {"scheme": "iso6523-actorid-upis", "value": "0208:0123456744"}},
            {"id": "https://www.ibm.com/products/peppol-services"},
            {"id": "https://www.ibm.com/products/b2b-integration-saas"},
            {
                "documentTypes": [
                    {
                        "scheme": "busdox-docid-qns",
                        "value": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
                    }
                ]
            },
        ]
    }

    assert participant_values_from_directory(payload) == [
        "9925:be0123456749",
        "0208:0123456744",
    ]

def test_business_card_websites_stay_on_business_entity() -> None:
    directory = DirectoryResult(
        baseUrl="https://directory.example",
        found=True,
        businessCard={
            "entities": [
                {
                    "name": "IBM Demo Endpoint NA",
                    "countryCode": "US",
                    "websiteURIs": [
                        "https://www.ibm.com/products/peppol-services",
                        "https://www.ibm.com/products/b2b-integration-saas",
                    ],
                    "additionalIdentifiers": [
                        {"scheme": "VAT", "value": "NL01155611"},
                        {"scheme": "TAX", "value": "7381020160503"},
                    ],
                    "contacts": [
                        {"type": "Technical", "email": "peppol@eaglessoft.com"},
                    ],
                    "additionalInformation": "Australia Austria Belgium",
                }
            ]
        },
    )

    entities = business_entities_from_directory(directory)

    assert len(entities) == 1
    assert entities[0].name == "IBM Demo Endpoint NA"
    assert entities[0].websites == [
        "https://www.ibm.com/products/peppol-services",
        "https://www.ibm.com/products/b2b-integration-saas",
    ]
    assert entities[0].identifiers == [
        {"scheme": "VAT", "value": "NL01155611"},
        {"scheme": "TAX", "value": "7381020160503"},
    ]
    assert entities[0].contacts == [{"type": "Technical", "email": "peppol@eaglessoft.com"}]
    assert entities[0].additionalInfo == "Australia Austria Belgium"

def test_business_card_entities_are_extracted_from_directory_search_matches() -> None:
    directory = DirectoryResult(
        baseUrl="https://directory.example",
        found=True,
        businessCard={
            "matches": [
                {
                    "participantID": {
                        "scheme": "iso6523-actorid-upis",
                        "value": "0208:0123456749",
                    },
                    "entities": [
                        {
                            "name": [{"name": "gorsele-test"}],
                            "countryCode": "BE",
                            "additionalInfo": "Via The Yuki Company",
                            "regDate": "2025-11-24",
                        }
                    ],
                }
            ]
        },
    )

    entities = business_entities_from_directory(directory)

    assert len(entities) == 1
    assert entities[0].name == "gorsele-test"
    assert entities[0].countryCode == "BE"
    assert entities[0].additionalInfo == "Via The Yuki Company"
    assert entities[0].regDate == "2025-11-24"

def test_directory_matches_are_filtered_when_explicit_icd_is_used() -> None:
    directory_matches = [
        DirectoryResult(
            baseUrl="https://directory.example",
            found=True,
            businessCard={
                "total-result-count": 3,
                "matches": [
                    {"participantID": "iso6523-actorid-upis::9925:be0123456749"},
                    {"participantID": "iso6523-actorid-upis::0208:0123456749"},
                    {"participantID": "iso6523-actorid-upis::9913:000076.example"},
                ],
            },
        )
    ]

    filtered = _filter_directory_matches_by_icd(directory_matches, "0208")

    assert _directory_participant_values(filtered, "0208") == {"0208:0123456749"}
    assert filtered[0].businessCard["total-result-count"] == 1
    assert filtered[0].businessCard["matches"][0]["participantID"].endswith("0208:0123456749")

def test_codelist_evaluator_loads_cached_official_json() -> None:
    cache_dir = Path(__file__).parent / "fixtures" / "codelists"
    evaluator = CodeListEvaluator(str(cache_dir))

    assert evaluator.metadata()["version"] == "9.6"
    assert evaluator.evaluate_participant_scheme("0208") == CodeListStatus.valid
    assert evaluator.evaluate_document_type("doc-1") == CodeListStatus.deprecated
    assert evaluator.evaluate_document_type("busdox-docid-qns::doc-1") == (
        CodeListStatus.deprecated
    )
    assert evaluator.document_type_name("busdox-docid-qns::doc-1") == "Fixture Document Type"
    assert evaluator.evaluate_transport_profile("peppol-transport-as4-v2_0") == (
        CodeListStatus.valid
    )
    assert evaluator.participant_candidates("BE", "0123456749", None, 10)[0][1] == (
        "0208:0123456749"
    )

def test_participant_countries_endpoint_uses_codelist() -> None:
    app = create_app(Settings())
    client = TestClient(app)

    response = client.get("/api/v1/codelists/participant-countries")

    assert response.status_code == 200
    countries = response.json()["countries"]
    assert "BE" in countries
    assert "DE" in countries
    assert countries == sorted(countries)

def test_codelist_refresh_is_public() -> None:
    class FakeOrchestrator:
        async def refresh_codelists(self):
            return {"status": "refreshed"}

    app = create_app(Settings())
    app.dependency_overrides[get_orchestrator] = lambda: FakeOrchestrator()
    client = TestClient(app)

    response = client.post("/api/v1/codelists/refresh")

    assert response.status_code == 200
    assert response.json() == {"status": "refreshed"}

def test_codelist_required_fails_startup_without_valid_cache() -> None:
    with pytest.raises(RuntimeError, match="PEPPOL_CODELIST_REQUIRED"):
        create_app(
            Settings(
                peppol_codelist_cache_dir=str(
                    Path(__file__).parent / "fixtures" / "missing_codelists"
                ),
                peppol_codelist_required=True,
            )
        )

def test_lookup_rate_limit_returns_429() -> None:
    class FakeOrchestrator:
        settings = Settings(peppol_rate_limit_requests=1, peppol_rate_limit_window_seconds=60)

        async def lookup(self, **kwargs):
            return LightLookupResponse(participantIdentifier=kwargs["participant"])

    app = create_app(Settings(peppol_rate_limit_requests=1, peppol_rate_limit_window_seconds=60))
    app.dependency_overrides[get_orchestrator] = lambda: FakeOrchestrator()
    client = TestClient(app)

    first = client.get("/api/v1/participants/0192:987654321?sources=directory")
    second = client.get("/api/v1/participants/0192:987654321?sources=directory")

    assert first.status_code == 200
    assert second.status_code == 429

def test_participant_scheme_check_digit_validation() -> None:
    evaluator = CodeListEvaluator("data/codelists")

    assert evaluator.participant_candidates("NO", "745707327", "0192", 10)[0][1] == (
        "0192:745707327"
    )
    assert evaluator.participant_candidates("BE", "0123456749", "0208", 10)[0][1] == (
        "0208:0123456749"
    )

    scheme = evaluator.participant_schemes["0208"]
    rejected = validate_candidate(scheme, "0123456700")

    assert rejected.valid is False
    assert rejected.reason == "check digit validation failed"

def test_codelist_removed_dates_are_tagged_removed() -> None:
    payload = {
        "values": [
            {"value": "doc-removed", "removal-date": "2000-01-01"},
            {"process-id": "proc-removed", "removal-date": "2000-01-01"},
            {"transport-profile": "transport-removed", "removal-date": "2000-01-01"},
        ]
    }

    assert load_document_types(payload)["doc-removed"] == CodeListStatus.removed
    assert load_processes(payload)["proc-removed"] == CodeListStatus.removed
    assert load_transport_profiles(payload)["transport-removed"] == CodeListStatus.removed

def test_company_lookup_detail_returns_rejected_candidates() -> None:
    class FakeOrchestrator:
        settings = Settings(peppol_directory_enabled=False)
        codelists = CodeListEvaluator("data/codelists")

        async def lookup(self, **kwargs):
            raise AssertionError("invalid candidates should not be looked up")

    app = create_app(Settings())
    app.dependency_overrides[get_orchestrator] = lambda: FakeOrchestrator()
    client = TestClient(app)

    response = client.get(
        "/api/v1/companies?country=BE&identifier=0123456700"
        "&identifier_type=0208&mode=detail"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["candidates"][0]["validationStatus"] == "candidate_rejected"
    assert body["candidates"][0]["rejectionReason"] == "check digit validation failed"
    assert body["matches"] == []

def test_sml_dns_helpers_build_query_and_extract_smp_url() -> None:
    participant = ParticipantIdentifier(value="0192:987654321")
    query_name = build_sml_query_name(participant, "participant.sml.prod.tech.peppol.org")
    smp_url, records = extract_smp_base_url(
        [
            {
                "data": (
                    '100 10 "U" "Meta:SMP" '
                    '"!^.*$!https://smp.example.test!" .'
                )
            }
        ]
    )

    assert query_name.endswith(".iso6523-actorid-upis.participant.sml.prod.tech.peppol.org")
    assert not query_name.startswith("b-")
    assert smp_url == "https://smp.example.test"
    assert records

def test_openpeppol_lookup_client_uses_post_api(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return httpx.Response(
                200,
                json={"exists": True, "smpUrl": "https://smp.example"},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(async_lookup("0208:0123456749"))

    assert captured["url"] == "https://api-lookup.peppol.org/lookup"
    assert captured["json"] == {
        "identifier": "iso6523-actorid-upis::0208:0123456749"
    }
    assert result["payload"]["exists"] is True

async def async_lookup(value: str) -> dict[str, object]:
    return await OpenPeppolLookupClient("https://api-lookup.peppol.org", 1000).lookup(
        ParticipantIdentifier(value=value)
    )

def test_smp_url_is_resolved_from_prod_sml_and_test_smk(monkeypatch) -> None:
    resolved_zones = []
    smp_base_urls = []

    class FakeSmlDnsClient:
        def __init__(self, dns_zone: str, timeout_ms: int, source: str) -> None:
            self.dns_zone = dns_zone
            self.source = source

        async def resolve(self, participant: ParticipantIdentifier) -> SmlResult:
            resolved_zones.append((self.source, self.dns_zone, participant.value))
            return SmlResult(
                source=self.source,
                dnsZone=self.dns_zone,
                queryName=f"hash.{self.dns_zone}",
                smpBaseUrl=f"https://resolved-{self.source}.example",
            )

    class FakeSmpClient:
        def __init__(self, base_url: str, timeout_ms: int, codelists: CodeListEvaluator) -> None:
            self.base_url = base_url
            smp_base_urls.append(base_url)

        async def lookup(
            self, participant: ParticipantIdentifier, include_raw: bool, raw_max_bytes: int
        ) -> SmpResult:
            return SmpResult(baseUrl=self.base_url)

    monkeypatch.setattr("app.peppol.orchestrator.SmlDnsClient", FakeSmlDnsClient)
    monkeypatch.setattr("app.peppol.orchestrator.SmpClient", FakeSmpClient)

    orchestrator = LookupOrchestrator(
        Settings(
            peppol_sml_prod_dns_zone="prod-zone.example",
            peppol_sml_test_dns_zone="test-zone.example",
        )
    )

    asyncio.run(
        orchestrator.lookup(
            participant=ParticipantIdentifier(value="0208:0123456749"),
            mode=LookupMode.detail,
            environments=["prod", "test"],
            sources={"smp"},
            include_raw=False,
            timeout_ms=1000,
            refresh=True,
        )
    )

    assert resolved_zones == [
        ("sml", "prod-zone.example", "0208:0123456749"),
        ("smk", "test-zone.example", "0208:0123456749"),
    ]
    assert smp_base_urls == [
        "https://resolved-sml.example",
        "https://resolved-smk.example",
    ]

def test_smp_source_adds_sml_smk_dependency() -> None:
    assert _with_required_source_dependencies({"smp"}) == {"smp", "sml", "smk"}
    assert _with_required_source_dependencies({"directory"}) == {"directory"}

def test_codelist_cache_write_is_atomic(monkeypatch) -> None:
    original_replace = os.replace
    replace_calls = []
    cache_dir = Path(".test-codelist-cache") / uuid4().hex

    def tracking_replace(source, destination):
        source_path = Path(source)
        destination_path = Path(destination)
        replace_calls.append((source_path, destination_path, source_path.exists()))
        original_replace(source, destination)

    monkeypatch.setattr("app.peppol.codelists.cache.os.replace", tracking_replace)

    try:
        cache = CodeListCache(str(cache_dir))
        written = cache.write("document_types", {"values": []}, "https://example.test/codelist.json")
        read_back = cache.read("document_types")

        assert replace_calls
        temporary_path, destination_path, source_existed = replace_calls[0]
        assert source_existed is True
        assert temporary_path.name.startswith(".document_types.json.")
        assert temporary_path.suffix == ".tmp"
        assert not temporary_path.exists()
        assert destination_path == cache_dir / "document_types.json"
        assert written.path == destination_path
        assert read_back is not None
        assert read_back.payload["values"] == []
    finally:
        shutil.rmtree(cache_dir.parent, ignore_errors=True)
