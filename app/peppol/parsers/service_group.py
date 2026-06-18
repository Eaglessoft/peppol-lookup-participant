from urllib.parse import unquote, urlparse

from app.peppol.parsers.common import first_child, local_name, parse_xml, text


def _document_ref_from_href(href: str) -> str | None:
    path = urlparse(href).path.rstrip("/")
    if "/services/" not in path:
        return None
    encoded_document = path.rsplit("/services/", 1)[1]
    return unquote(encoded_document) if encoded_document else None


def _is_usable_document_ref(document_ref: str) -> bool:
    value = document_ref.strip().lower()
    return bool(value) and value not in {"null", "busdox-docid-qns::null"}


def parse_service_group(xml_text: str) -> tuple[dict[str, object], list[str]]:
    root = parse_xml(xml_text)
    participant = first_child(root, "ParticipantIdentifier")
    document_refs: list[str] = []
    document_ref_urls: dict[str, str] = {}
    for document in root.iter():
        if local_name(document.tag) == "DocumentTypeIdentifier" and document.text:
            document_ref = document.text.strip()
            if _is_usable_document_ref(document_ref):
                document_refs.append(document_ref)
        if local_name(document.tag) == "ServiceMetadataReference":
            href = document.attrib.get("href")
            if href:
                document_ref = _document_ref_from_href(href)
                if document_ref and _is_usable_document_ref(document_ref):
                    document_refs.append(document_ref)
                    document_ref_urls[document_ref] = href

    service_group = {
        "participantIdentifier": {
            "scheme": participant.attrib.get("scheme") if participant is not None else None,
            "value": text(participant),
        },
        "documentReferences": document_refs,
        "documentReferenceUrls": document_ref_urls,
    }
    return service_group, document_refs
