from collections.abc import Callable

from app.peppol.models import (
    CodeListStatus,
    EndpointMetadata,
    IdentifierWithStatus,
    ProcessMetadata,
    ServiceMetadata,
)
from app.peppol.parsers.certificate import parse_certificate
from app.peppol.parsers.common import element_to_dict, first_child, local_name, parse_xml, text


def parse_service_metadata(
    xml_text: str,
    document_type_value: str,
    document_status: CodeListStatus,
    document_name: str | None,
    process_evaluator: Callable[[str], CodeListStatus],
    transport_evaluator: Callable[[str], CodeListStatus],
    include_raw: bool,
    raw_max_bytes: int,
) -> ServiceMetadata:
    root = parse_xml(xml_text)
    processes: list[ProcessMetadata] = []

    for process in root.iter():
        if local_name(process.tag) != "Process":
            continue
        process_identifier = first_child(process, "ProcessIdentifier")
        process_value = text(process_identifier) or ""
        endpoints: list[EndpointMetadata] = []

        for endpoint in process.iter():
            if local_name(endpoint.tag) != "Endpoint":
                continue
            transport_profile = endpoint.attrib.get("transportProfile") or ""
            endpoint_ref = first_child(endpoint, "EndpointReference")
            endpoint_value = text(first_child(endpoint_ref, "Address")) or text(endpoint_ref)
            raw_certificate = text(first_child(endpoint, "Certificate"))

            endpoints.append(
                EndpointMetadata(
                    transportProfile=transport_profile,
                    transportProfileStatus=transport_evaluator(transport_profile),
                    endpointReference=endpoint_value,
                    requireBusinessLevelSignature=text(
                        first_child(endpoint, "RequireBusinessLevelSignature")
                    )
                    == "true",
                    minimumAuthenticationLevel=text(
                        first_child(endpoint, "MinimumAuthenticationLevel")
                    ),
                    serviceActivationDate=text(first_child(endpoint, "ServiceActivationDate")),
                    serviceExpirationDate=text(first_child(endpoint, "ServiceExpirationDate")),
                    certificate=parse_certificate(raw_certificate, include_raw),
                    serviceDescription=text(first_child(endpoint, "ServiceDescription")),
                    technicalContactUrl=text(first_child(endpoint, "TechnicalContactUrl")),
                    technicalInformationUrl=text(first_child(endpoint, "TechnicalInformationUrl")),
                    extensions=_extensions(endpoint),
                )
            )

        processes.append(
            ProcessMetadata(
                processIdentifier=IdentifierWithStatus(
                    scheme=process_identifier.attrib.get("scheme")
                    if process_identifier is not None
                    else None,
                    value=process_value,
                    status=process_evaluator(process_value),
                ),
                endpoints=endpoints,
                extensions=_extensions(process),
            )
        )

    return ServiceMetadata(
        documentTypeIdentifier=IdentifierWithStatus(
            scheme="busdox-docid-qns",
            value=document_type_value,
            status=document_status,
            displayName=document_name,
        ),
        processes=processes,
        rawXmlIncluded=include_raw,
        rawXml=xml_text[:raw_max_bytes] if include_raw else None,
    )


def _extensions(element) -> list[dict[str, object]]:
    return [
        element_to_dict(child)
        for child in element.iter()
        if local_name(child.tag) == "Extension"
    ]
