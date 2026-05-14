# Peppol Lookup Service Design

This document defines the target service that discovers Peppol participant information from known Peppol network sources and exposes the collected result as JSON.

## Goal

Build a Python API service that receives a Peppol participant identifier and returns:

- Whether the participant is visible in Peppol production and/or test networks.
- Which SMP is responsible for the participant.
- Which document type identifiers (DTI / document capabilities) are supported.
- Which processes, transport profiles, AP endpoints, and certificates are published by the SMP.
- Which public Business Card / Directory information is available.
- Source-level status, errors, timing, and environment information.

The service must also support company discovery from country + local identifier inputs. In that mode it should use the current Peppol Participant Identifier Schemes code list to generate candidate participant IDs, test them across the configured environments, and return matching companies/participants.

The service must support two output modes:

- `light`: compact response for UI/business usage.
- `detail`: full technical response with every field we can discover from SML/SMK, SMP, Directory, Lookup Service, and future adapters.

## Terminology

- Participant ID: Peppol endpoint identifier, usually represented as `scheme::value`, for example `iso6523-actorid-upis::0192:987654321`.
- ICD: Identifier code inside participant value, for example `0192`.
- SML: Service Metadata Locator for production discovery.
- SMK: Test Service Metadata Locator.
- SMP: Service Metadata Publisher. Holds service groups, document capabilities, endpoint metadata, process metadata, transport profile, and AP certificate data.
- AP: Access Point. Receiver endpoint for document delivery.
- DTI: Document Type Identifier, also called document capability.
- Business Card: Directory representation of the participant, including company/entity metadata and optional contact fields.

## Discovery Sources

### Mandatory Sources

| Source | Environment | Purpose | Notes |
| --- | --- | --- | --- |
| OpenPeppol Directory | `prod` | Search public Business Cards and document capabilities | Not every valid Peppol participant is listed because Directory publication is not mandatory. |
| OpenPeppol Directory TEST | `test` | Same as production Directory for test network | Used for SMK/test participant data. |
| OpenPeppol Lookup Service | `prod`, later `test` if available | Verify current publication status | OpenPeppol describes this as a simple publication-status verification service. |
| SML DNS discovery | `prod` | Authoritative discovery of SMP address for a participant | DNS-based lookup; should be treated as stronger evidence than Directory. |
| SMK DNS discovery | `test` | Test-network equivalent of SML lookup | Used to resolve test SMPs. |
| Resolved SMP | `prod` / `test` | Fetch service group and service metadata | Source for DTI, process, endpoint, transport profile, AP certificate. |

### Optional/Future Sources

| Source Type | Purpose |
| --- | --- |
| Directory export files | Bulk refresh/cache of Business Cards and participant IDs. |
| Country/authority directories | Some countries may expose additional public registries or validation endpoints. |
| Third-party lookup APIs | Can be added as non-authoritative enrichment adapters if needed. |
| Certificate trust metadata | Enrich AP/SMP certificate chain and validity checks. |

All sources must be implemented as adapters so new registries can be added without changing the response contract.

## Code Lists

The service must maintain a local cache of the current OpenPeppol eDelivery code lists and use them during lookup, validation, and result enrichment.

Official source:

- `https://docs.peppol.eu/edelivery/codelists/`

Required code lists:

| Code List | Use |
| --- | --- |
| Participant Identifier Schemes | Country + local identifier to participant ID candidate generation, identifier validation, status tagging. |
| Document Types | DTI validation and `valid` / `deprecated` / `removed` / `unsupported` tagging. |
| Processes | Process identifier validation and status tagging. |
| Transport Profiles | Endpoint transport profile validation and status tagging. |

The codelist cache should support:

- Scheduled refresh from the official JSON or GeneriCode artifacts.
- Manual refresh endpoint for operators.
- Version metadata: release version, fetched timestamp, source URL, checksum, item counts.
- Fallback to the last valid local cache if the remote source is unavailable.
- A startup failure only when no local cache exists and codelist validation is configured as mandatory.

Rows with a `deprecated` state must be tagged as deprecated but still understood. Rows with a removal date in the past must be tagged as removed and not treated as valid Peppol Network usage. Unknown values must be tagged as unsupported or unknown, depending on whether the code list was available during evaluation.

## Known Central Endpoints

| Name | Base URL / DNS Zone | Environment | Use |
| --- | --- | --- | --- |
| Peppol Directory | `https://directory.peppol.eu` | `prod` | REST search and exports. |
| Peppol Directory TEST | `https://test-directory.peppol.eu` | `test` | REST search and exports. |
| Peppol Lookup Service | `https://lookup.peppol.org` | `prod` | Publication status lookup. API details must be confirmed during implementation. |
| SML DNS zone | `edelivery.tech.ec.europa.eu` | `prod` | Participant-to-SMP discovery. |
| SMK DNS zone | `sml.test.tech.peppol.org` | `test` | Test participant-to-SMP discovery. |

The endpoint registry must be configuration-driven. Defaults are committed, but operators can disable or override any source via environment variables.

## Public API

### Lookup

```http
GET /api/v1/participants/{participant_id}/lookup
```

Query parameters:

| Name | Default | Description |
| --- | --- | --- |
| `mode` | `light` | `light` or `detail`. |
| `environments` | `prod,test` | Comma-separated lookup environments. |
| `sources` | `all` | Optional source allowlist, for example `directory,sml,smp`. |
| `include_raw` | `false` | Include raw XML/JSON payload excerpts in `detail` mode. |
| `timeout_ms` | service default | Per-source timeout override within allowed limits. |
| `refresh` | `false` | Bypass cache when allowed. |

Participant ID path value must support URL encoding because Peppol identifiers contain `:`, `#`, and other special characters.

Alternative POST endpoint for safer encoding:

```http
POST /api/v1/lookup
Content-Type: application/json

{
  "participant_id": {
    "scheme": "iso6523-actorid-upis",
    "value": "0192:987654321"
  },
  "mode": "detail",
  "environments": ["prod", "test"]
}
```

### Source Health

```http
GET /api/v1/sources
GET /api/v1/sources/health
```

Returns configured source adapters, enabled environments, base URLs, cache status, and last health check.

### Company Discovery

```http
GET /api/v1/companies/lookup
```

Query parameters:

| Name | Default | Description |
| --- | --- | --- |
| `country` | required | ISO 3166-1 alpha-2 country code, for example `BE`, `NL`, `DE`. |
| `identifier` | required | Local company identifier, VAT number, chamber of commerce number, GLN, or other known value. |
| `identifier_type` | optional | Hint such as `vat`, `company_number`, `gln`, `duns`, or explicit ICD like `0208`. |
| `mode` | `light` | `light` or `detail`. |
| `environments` | `prod,test` | Comma-separated lookup environments. |
| `max_candidates` | service default | Upper bound for generated participant ID candidates. |

Alternative POST endpoint:

```http
POST /api/v1/companies/lookup
Content-Type: application/json

{
  "country": "BE",
  "identifier": "0000000000",
  "identifier_type": "company_number",
  "mode": "detail",
  "environments": ["prod", "test"]
}
```

Company discovery flow:

1. Normalize country and identifier.
2. Load current Participant Identifier Schemes codelist from local cache.
3. Select schemes applicable to the country plus international schemes when relevant.
4. Apply scheme rules where available: regex, length, check digit notes, display requirements.
5. Generate candidate Peppol participant IDs such as `iso6523-actorid-upis::0208:0000000000`.
6. Query Directory by participant candidate and by name/identifier when applicable.
7. Query SML/SMK for each candidate.
8. Fetch SMP details for found candidates.
9. Rank matches by source confidence.
10. Return matching companies/participants with rejected candidates and reasons in `detail` mode.

Candidate result example:

```json
{
  "input": {
    "country": "BE",
    "identifier": "0000000000",
    "identifierType": "company_number"
  },
  "candidates": [
    {
      "participantIdentifier": {
        "scheme": "iso6523-actorid-upis",
        "value": "0208:0000000000"
      },
      "country": "BE",
      "schemeCode": "0208",
      "schemeName": "Example National Company Register",
      "schemeStatus": "valid",
      "validationStatus": "candidate_valid",
      "found": true,
      "foundIn": ["prod:sml", "prod:smp", "prod:directory"]
    }
  ],
  "matches": []
}
```

## Light Response

The light response is optimized for common business usage and hides source-level noise. It should aggregate Business Card data and supported document capabilities into a compact shape.

Anonymized example:

```json
{
  "participantIdentifier": {
    "scheme": "iso6523-actorid-upis",
    "value": "0208:0000000000"
  },
  "businessEntities": [
    {
      "name": "Example Manufacturing International",
      "countryCode": "BE",
      "geoInfo": "Example Industrial Park, 1000 Example City",
      "identifiers": [],
      "websites": [],
      "contacts": [
        {
          "type": "primary",
          "name": "Primary Contact",
          "phone": "",
          "email": "primary.contact@example.com"
        }
      ],
      "additionalInfo": "",
      "regDate": "2025-12-17"
    }
  ],
  "documentCapabilities": [
    {
      "documentTypeIdentifier": {
        "scheme": "busdox-docid-qns",
        "value": "urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2::ApplicationResponse##urn:fdc:peppol.eu:poacc:trns:invoice_response:3::2.1",
        "status": "valid"
      },
      "processIdentifier": {
        "scheme": "cenbii-procid-ubl",
        "value": "urn:fdc:peppol.eu:poacc:bis:invoice_response:3",
        "status": "valid"
      },
      "transportProfile": {
        "value": "peppol-transport-as4-v2_0",
        "status": "valid"
      },
      "serviceDescription": "Example Access Point Provider",
      "technicalContactUrl": "support@example-ap-provider.com",
      "technicalInformationUrl": ""
    },
    {
      "documentTypeIdentifier": {
        "scheme": "busdox-docid-qns",
        "value": "urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2::ApplicationResponse##urn:fdc:peppol.eu:poacc:trns:mlr:3::2.1",
        "status": "valid"
      },
      "processIdentifier": {
        "scheme": "cenbii-procid-ubl",
        "value": "urn:fdc:peppol.eu:poacc:bis:mlr:3",
        "status": "valid"
      },
      "transportProfile": {
        "value": "peppol-transport-as4-v2_0",
        "status": "valid"
      },
      "serviceDescription": "Example Access Point Provider",
      "technicalContactUrl": "support@example-ap-provider.com",
      "technicalInformationUrl": ""
    },
    {
      "documentTypeIdentifier": {
        "scheme": "busdox-docid-qns",
        "value": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2::CreditNote##urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0::2.1",
        "status": "valid"
      },
      "processIdentifier": {
        "scheme": "cenbii-procid-ubl",
        "value": "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0",
        "status": "valid"
      },
      "transportProfile": {
        "value": "peppol-transport-as4-v2_0",
        "status": "valid"
      },
      "serviceDescription": "Example Access Point Provider",
      "technicalContactUrl": "support@example-ap-provider.com",
      "technicalInformationUrl": ""
    },
    {
      "documentTypeIdentifier": {
        "scheme": "busdox-docid-qns",
        "value": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2::CreditNote##urn:cen.eu:en16931:2017#conformant#urn:UBL.BE:1.0.0.20180214::2.1",
        "status": "valid"
      },
      "processIdentifier": {
        "scheme": "cenbii-procid-ubl",
        "value": "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0",
        "status": "valid"
      },
      "transportProfile": {
        "value": "peppol-transport-as4-v2_0",
        "status": "valid"
      },
      "serviceDescription": "Example Access Point Provider",
      "technicalContactUrl": "support@example-ap-provider.com",
      "technicalInformationUrl": ""
    },
    {
      "documentTypeIdentifier": {
        "scheme": "busdox-docid-qns",
        "value": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0::2.1",
        "status": "valid"
      },
      "processIdentifier": {
        "scheme": "cenbii-procid-ubl",
        "value": "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0",
        "status": "valid"
      },
      "transportProfile": {
        "value": "peppol-transport-as4-v2_0",
        "status": "valid"
      },
      "serviceDescription": "Example Access Point Provider",
      "technicalContactUrl": "support@example-ap-provider.com",
      "technicalInformationUrl": ""
    },
    {
      "documentTypeIdentifier": {
        "scheme": "busdox-docid-qns",
        "value": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##urn:cen.eu:en16931:2017#conformant#urn:UBL.BE:1.0.0.20180214::2.1",
        "status": "valid"
      },
      "processIdentifier": {
        "scheme": "cenbii-procid-ubl",
        "value": "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0",
        "status": "valid"
      },
      "transportProfile": {
        "value": "peppol-transport-as4-v2_0",
        "status": "valid"
      },
      "serviceDescription": "Example Access Point Provider",
      "technicalContactUrl": "support@example-ap-provider.com",
      "technicalInformationUrl": ""
    },
    {
      "documentTypeIdentifier": {
        "scheme": "busdox-docid-qns",
        "value": "urn:oasis:names:specification:ubl:schema:xsd:Order-2::Order##urn:fdc:peppol.eu:poacc:trns:order:3::2.1",
        "status": "valid"
      },
      "processIdentifier": {
        "scheme": "cenbii-procid-ubl",
        "value": "urn:fdc:peppol.eu:poacc:bis:order_only:3",
        "status": "valid"
      },
      "transportProfile": {
        "value": "peppol-transport-as4-v2_0",
        "status": "valid"
      },
      "serviceDescription": "Example Access Point Provider",
      "technicalContactUrl": "support@example-ap-provider.com",
      "technicalInformationUrl": ""
    }
  ]
}
```

Field notes:

- `participantIdentifier` is the normalized participant identifier used for lookup.
- `businessEntities` follows Peppol Directory Business Card terminology. Field names intentionally align with Directory JSON where possible: `name`, `countryCode`, `geoInfo`, `identifiers`, `websites`, `contacts`, `additionalInfo`, `regDate`.
- `documentCapabilities` is built from SMP service metadata and can be enriched by Directory `docTypes`.
- `documentTypeIdentifier`, `processIdentifier`, and `transportProfile` follow SMP/eDelivery terminology.
- `serviceDescription` and `technicalContactUrl` come from SMP endpoint metadata when available.
- `status` values under `documentTypeIdentifier`, `processIdentifier`, and `transportProfile` are evaluated against the locally cached current Peppol codelists.
- `light` mode should not expose raw XML, DNS records, certificate details, endpoint URLs, or per-source errors unless a later requirement explicitly adds them.

## Detail Response

Detail mode must preserve every useful discovery result and make conflicts visible.

```json
{
  "lookupId": "018f7c0f-0000-7000-9000-000000000000",
  "createdAt": "2026-05-14T19:00:00Z",
  "mode": "detail",
  "input": {
    "raw": "iso6523-actorid-upis::0192:987654321",
    "normalized": {
      "scheme": "iso6523-actorid-upis",
      "value": "0192:987654321",
      "icd": "0192",
      "identifier": "987654321"
    }
  },
  "summary": {
    "exists": true,
    "routable": true,
    "foundIn": ["prod:sml", "prod:smp", "prod:directory"],
    "notFoundIn": ["test:smk", "test:directory"],
    "warnings": [
      "Participant found in SML/SMP but missing in test Directory"
    ]
  },
  "environments": [
    {
      "name": "prod",
      "status": "found",
      "sml": {
        "source": "sml",
        "dnsZone": "edelivery.tech.ec.europa.eu",
        "queryName": "computed-query-name",
        "naptrRecords": [],
        "smpBaseUrl": "https://smp.example.com"
      },
      "smp": {
        "source": "smp",
        "baseUrl": "https://smp.example.com",
        "serviceGroup": {
          "participantIdentifier": {
            "scheme": "iso6523-actorid-upis",
            "value": "0192:987654321"
          },
          "documentReferences": []
        },
        "services": [
          {
            "documentTypeIdentifier": {
              "scheme": "busdox-docid-qns",
              "value": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice...",
              "codeListStatus": "valid",
              "statusReason": null
            },
            "processes": [
              {
                "processIdentifier": {
                  "scheme": "cenbii-procid-ubl",
                  "value": "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0",
                  "codeListStatus": "valid",
                  "statusReason": null
                },
                "endpoints": [
                  {
                    "transportProfile": "peppol-transport-as4-v2_0",
                    "transportProfileStatus": "valid",
                    "endpointReference": "https://ap.example.com/as4",
                    "requireBusinessLevelSignature": false,
                    "minimumAuthenticationLevel": null,
                    "serviceActivationDate": null,
                    "serviceExpirationDate": null,
                    "certificate": {
                      "rawBase64": null,
                      "subject": null,
                      "issuer": null,
                      "serialNumber": null,
                      "notBefore": null,
                      "notAfter": null,
                      "fingerprints": {
                        "sha256": null
                      }
                    },
                    "technicalContactUrl": null,
                    "technicalInformationUrl": null,
                    "extensions": []
                  }
                ],
                "extensions": []
              }
            ],
            "rawXmlIncluded": false
          }
        ]
      },
      "codeListEvaluation": {
        "version": "9.6",
        "fetchedAt": "2026-05-14T18:30:00Z",
        "documentTypes": {
          "valid": 7,
          "deprecated": 0,
          "removed": 0,
          "unsupported": 0,
          "unknown": 0
        },
        "processes": {
          "valid": 7,
          "deprecated": 0,
          "removed": 0,
          "unsupported": 0,
          "unknown": 0
        },
        "transportProfiles": {
          "valid": 1,
          "deprecated": 0,
          "removed": 0,
          "unsupported": 0,
          "unknown": 0
        }
      },
      "directory": {
        "source": "directory",
        "baseUrl": "https://directory.peppol.eu",
        "found": true,
        "businessCard": {
          "participantId": {
            "scheme": "iso6523-actorid-upis",
            "value": "0192:987654321"
          },
          "entities": [
            {
              "name": "Example Company",
              "countryCode": "NL",
              "registrationDate": null,
              "geographicalInformation": null,
              "identifiers": [],
              "websites": [],
              "contacts": [],
              "additionalInformation": []
            }
          ],
          "documentTypes": []
        }
      },
      "lookupService": {
        "source": "openpeppol-lookup",
        "baseUrl": "https://lookup.peppol.org",
        "status": "unknown",
        "payload": null
      }
    }
  ],
  "sourceResults": [
    {
      "source": "prod:directory",
      "status": "success",
      "httpStatus": 200,
      "durationMs": 120,
      "rateLimited": false,
      "error": null
    }
  ]
}
```

## Discovery Flow

For each requested environment:

1. Normalize and validate participant ID.
2. Load current codelist cache.
3. Validate participant scheme against Participant Identifier Schemes.
4. Query Directory by exact participant ID.
5. Query SML/SMK DNS to resolve SMP base URL.
6. If SMP is resolved, fetch ServiceGroup.
7. For each document reference in ServiceGroup, fetch ServiceMetadata.
8. Parse processes, endpoints, certificates, dates, contacts, technical URLs, and extensions.
9. Tag DTI, process, and transport profile values against codelists.
10. Query OpenPeppol Lookup Service if enabled.
11. Merge source results into summary, preserving source-specific details.
12. Produce `light` or `detail` response.

Directory and SML/SMP results must be treated separately. Directory absence does not mean the participant is not routable.

## Caching and Rate Limits

- Directory REST API has strict rate limits, so adapter-level throttling is required.
- Cache positive and negative source results separately.
- Suggested defaults:
  - Directory search: 15 minutes.
  - SML/SMK DNS result: 15 minutes.
  - SMP ServiceGroup/ServiceMetadata: 15 minutes.
  - Source health: 1 minute.
- `refresh=true` bypasses cache only for authenticated/admin usage or within safe rate limits.

## Error Model

The API should return `200` for completed multi-source lookups even if some sources fail. Source failures are represented inside `sourceResults`.

Use non-200 API responses only for request-level errors:

- `400`: invalid participant ID or invalid query parameter.
- `422`: syntactically valid request but unsupported identifier format.
- `429`: local service rate limit exceeded.
- `500`: unexpected internal failure before lookup orchestration can complete.
- `504`: all requested sources timed out and no partial response can be produced.

Source statuses:

- `success`
- `not_found`
- `timeout`
- `rate_limited`
- `invalid_response`
- `disabled`
- `error`

## Configuration

Environment variables:

| Name | Default | Description |
| --- | --- | --- |
| `PEPPOL_LOOKUP_ENVIRONMENTS` | `prod,test` | Enabled environments. |
| `PEPPOL_DIRECTORY_PROD_URL` | `https://directory.peppol.eu` | Production Directory base URL. |
| `PEPPOL_DIRECTORY_TEST_URL` | `https://test-directory.peppol.eu` | Test Directory base URL. |
| `PEPPOL_LOOKUP_SERVICE_URL` | `https://lookup.peppol.org` | OpenPeppol Lookup Service base URL. |
| `PEPPOL_SML_PROD_DNS_ZONE` | `edelivery.tech.ec.europa.eu` | Production SML DNS zone. |
| `PEPPOL_SML_TEST_DNS_ZONE` | `sml.test.tech.peppol.org` | Test SMK DNS zone. |
| `PEPPOL_SOURCE_TIMEOUT_MS` | `8000` | Per-source timeout. |
| `PEPPOL_CACHE_TTL_SECONDS` | `900` | Default cache TTL. |
| `PEPPOL_INCLUDE_RAW_MAX_BYTES` | `65536` | Max raw payload bytes in detail mode. |
| `PEPPOL_CODELIST_SOURCE_URL` | `https://docs.peppol.eu/edelivery/codelists/` | Official codelist index URL. |
| `PEPPOL_CODELIST_CACHE_DIR` | `data/codelists` | Local codelist cache directory. |
| `PEPPOL_CODELIST_REFRESH_SECONDS` | `86400` | Scheduled codelist refresh interval. |
| `PEPPOL_CODELIST_REQUIRED` | `true` | Whether startup requires at least one valid cached codelist snapshot. |

## Implementation Modules

Proposed structure:

```text
app/
  api/v1/
    lookup_routes.py
  shared/
    config.py
    responses.py
  peppol/
    models.py
    normalizer.py
    orchestrator.py
    company_lookup.py
    sources/
      base.py
      directory.py
      sml_dns.py
      smp.py
      openpeppol_lookup.py
    codelists/
      client.py
      cache.py
      evaluator.py
      participant_schemes.py
      document_types.py
      processes.py
      transport_profiles.py
    parsers/
      business_card.py
      service_group.py
      service_metadata.py
      certificate.py
```

## Validation Requirements

- Participant ID parser must accept:
  - `iso6523-actorid-upis::0192:987654321`
  - `0192:987654321` when default scheme is configured.
- Company lookup must accept country + identifier and generate participant ID candidates from the current Participant Identifier Schemes codelist.
- All URLs must be built with proper URL encoding.
- XML parsing must be namespace-aware.
- XML parser must disable external entity resolution.
- Certificates should be decoded and fingerprinted when possible, but raw certificate exposure must be configurable.
- DTI, process, and transport profile values must be tagged as `valid`, `deprecated`, `removed`, `unsupported`, or `unknown`.
- Deprecated entries are still returned but flagged.
- Removed entries are returned but flagged as not valid for current Peppol Network use.
- Unsupported entries are values not present in the current codelist when the codelist is available.
- Unknown is used only when codelist evaluation cannot be performed.

## Security and Privacy

- Do not log full raw SMP payloads by default.
- Do not expose raw certificates unless `include_raw=true` and policy allows it.
- Apply local rate limits per caller.
- Add request timeout and source timeout separately.
- Keep source errors sanitized in `light` mode.

## References

- OpenPeppol Directory: `https://peppol.org/tools-support/peppol-directory/`
- OpenPeppol Lookup Service: `https://peppol.org/tools-support/peppol-lookup-service/`
- OpenPeppol Interoperability Framework: `https://peppol.org/learn-more/peppol-interoperability-framework/`
- OpenPeppol eDelivery specifications: `https://docs.peppol.eu/edelivery/`
- OpenPeppol eDelivery code lists: `https://docs.peppol.eu/edelivery/codelists/`
- Peppol Directory REST API: `https://directory.peppol.eu/public/menuitem-docs-rest-api`
- Peppol Directory TEST REST API: `https://test-directory.peppol.eu/public/menuitem-docs-rest-api`
