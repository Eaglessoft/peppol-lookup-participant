from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field


class LookupMode(StrEnum):
    light = "light"
    detail = "detail"


class EnvironmentName(StrEnum):
    prod = "prod"
    test = "test"


class SourceStatus(StrEnum):
    success = "success"
    not_found = "not_found"
    timeout = "timeout"
    rate_limited = "rate_limited"
    invalid_response = "invalid_response"
    disabled = "disabled"
    error = "error"


class CodeListStatus(StrEnum):
    valid = "valid"
    deprecated = "deprecated"
    removed = "removed"
    unsupported = "unsupported"
    unknown = "unknown"


class ParticipantIdentifier(BaseModel):
    scheme: str = "iso6523-actorid-upis"
    value: str

    @property
    def compact(self) -> str:
        return f"{self.scheme}::{self.value}"

    @property
    def icd(self) -> str | None:
        if ":" not in self.value:
            return None
        return self.value.split(":", 1)[0]

    @property
    def local_identifier(self) -> str:
        if ":" not in self.value:
            return self.value
        return self.value.split(":", 1)[1]


class ParticipantInput(BaseModel):
    scheme: str = "iso6523-actorid-upis"
    value: str


class LookupRequest(BaseModel):
    participant_id: ParticipantInput = Field(alias="participant_id")
    mode: LookupMode = LookupMode.light
    environments: list[EnvironmentName] = Field(default_factory=lambda: list(EnvironmentName))
    include_raw: bool = False
    timeout_ms: int | None = None
    refresh: bool = False


class CompanyLookupRequest(BaseModel):
    country: str
    identifier: str
    identifier_type: str | None = None
    mode: LookupMode = LookupMode.light
    environments: list[EnvironmentName] = Field(default_factory=lambda: list(EnvironmentName))
    max_candidates: int = 20
    refresh: bool = False


class SourceResult(BaseModel):
    source: str
    status: SourceStatus
    httpStatus: int | None = None
    durationMs: int
    rateLimited: bool = False
    error: str | None = None


class IdentifierWithStatus(BaseModel):
    scheme: str | None = None
    value: str
    status: CodeListStatus = CodeListStatus.unknown
    displayName: str | None = None

    @computed_field
    @property
    def codeListStatus(self) -> CodeListStatus:
        return self.status

    @computed_field
    @property
    def statusReason(self) -> str | None:
        return None


class BusinessEntity(BaseModel):
    name: str | None = None
    countryCode: str | None = None
    geoInfo: str | None = None
    identifiers: list[dict[str, Any]] = Field(default_factory=list)
    websites: list[str] = Field(default_factory=list)
    contacts: list[dict[str, Any]] = Field(default_factory=list)
    additionalInfo: str | None = None
    regDate: str | None = None


class DocumentCapability(BaseModel):
    documentTypeIdentifier: IdentifierWithStatus
    processIdentifier: IdentifierWithStatus | None = None
    transportProfile: IdentifierWithStatus | None = None
    serviceDescription: str | None = None
    technicalContactUrl: str | None = None
    technicalInformationUrl: str | None = None


class EndpointMetadata(BaseModel):
    transportProfile: str
    transportProfileStatus: CodeListStatus = CodeListStatus.unknown
    endpointReference: str | None = None
    requireBusinessLevelSignature: bool | None = None
    minimumAuthenticationLevel: str | None = None
    serviceActivationDate: str | None = None
    serviceExpirationDate: str | None = None
    certificate: dict[str, Any] = Field(default_factory=dict)
    serviceDescription: str | None = None
    technicalContactUrl: str | None = None
    technicalInformationUrl: str | None = None
    extensions: list[dict[str, Any]] = Field(default_factory=list)


class ProcessMetadata(BaseModel):
    processIdentifier: IdentifierWithStatus
    endpoints: list[EndpointMetadata] = Field(default_factory=list)
    extensions: list[dict[str, Any]] = Field(default_factory=list)


class ServiceMetadata(BaseModel):
    documentTypeIdentifier: IdentifierWithStatus
    processes: list[ProcessMetadata] = Field(default_factory=list)
    rawXmlIncluded: bool = False
    rawXml: str | None = None


class DirectoryResult(BaseModel):
    source: str = "directory"
    baseUrl: str
    found: bool = False
    businessCard: dict[str, Any] | None = None


class SmlResult(BaseModel):
    source: str
    dnsZone: str
    queryName: str
    naptrRecords: list[str] = Field(default_factory=list)
    smpBaseUrl: str | None = None


class SmpResult(BaseModel):
    source: str = "smp"
    baseUrl: str
    serviceGroup: dict[str, Any] | None = None
    services: list[ServiceMetadata] = Field(default_factory=list)


class EnvironmentResult(BaseModel):
    name: EnvironmentName
    status: str
    sml: SmlResult | None = None
    smp: SmpResult | None = None
    directory: DirectoryResult | None = None
    lookupService: dict[str, Any] | None = None
    codeListEvaluation: dict[str, Any] = Field(default_factory=dict)


class LightLookupResponse(BaseModel):
    participantIdentifier: ParticipantIdentifier
    businessEntities: list[BusinessEntity] = Field(default_factory=list)
    documentCapabilities: list[DocumentCapability] = Field(default_factory=list)


class DetailLookupResponse(BaseModel):
    lookupId: str = Field(default_factory=lambda: str(uuid4()))
    createdAt: datetime = Field(default_factory=lambda: datetime.now(UTC))
    mode: LookupMode = LookupMode.detail
    input: dict[str, Any]
    summary: dict[str, Any]
    environments: list[EnvironmentResult] = Field(default_factory=list)
    sourceResults: list[SourceResult] = Field(default_factory=list)


class CandidateResult(BaseModel):
    participantIdentifier: ParticipantIdentifier
    country: str
    schemeCode: str
    schemeName: str | None = None
    schemeStatus: CodeListStatus = CodeListStatus.unknown
    validationStatus: str
    rejectionReason: str | None = None
    found: bool = False
    foundIn: list[str] = Field(default_factory=list)
    confidenceScore: int = 0


class CompanyLookupResponse(BaseModel):
    input: dict[str, Any]
    candidates: list[CandidateResult] = Field(default_factory=list)
    matches: list[LightLookupResponse | DetailLookupResponse] = Field(default_factory=list)
    directoryMatches: list[DirectoryResult] = Field(default_factory=list)
