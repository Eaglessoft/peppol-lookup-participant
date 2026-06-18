import base64
import hashlib
import os
import ssl
import tempfile


def parse_certificate(raw_base64: str | None, include_raw: bool) -> dict[str, object]:
    if not raw_base64:
        return {
            "rawBase64": None if include_raw else None,
            "subject": None,
            "issuer": None,
            "serialNumber": None,
            "notBefore": None,
            "notAfter": None,
            "fingerprints": {"sha256": None},
        }

    compact = "".join(raw_base64.split())
    try:
        certificate_bytes = base64.b64decode(compact, validate=True)
        sha256 = hashlib.sha256(certificate_bytes).hexdigest()
        decoded = _decode_certificate(certificate_bytes)
    except ValueError:
        sha256 = None
        decoded = {}

    return {
        "rawBase64": compact if include_raw else None,
        "subject": decoded.get("subject"),
        "issuer": decoded.get("issuer"),
        "serialNumber": decoded.get("serialNumber"),
        "notBefore": decoded.get("notBefore"),
        "notAfter": decoded.get("notAfter"),
        "fingerprints": {"sha256": sha256},
    }


def _decode_certificate(certificate_bytes: bytes) -> dict[str, object]:
    pem = (
        b"-----BEGIN CERTIFICATE-----\n"
        + base64.encodebytes(certificate_bytes)
        + b"-----END CERTIFICATE-----\n"
    )
    path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as cert_file:
            cert_file.write(pem)
            path = cert_file.name
        decoded = ssl._ssl._test_decode_cert(path)  # type: ignore[attr-defined]
        return {
            "subject": _name_to_string(decoded.get("subject")),
            "issuer": _name_to_string(decoded.get("issuer")),
            "serialNumber": decoded.get("serialNumber"),
            "notBefore": decoded.get("notBefore"),
            "notAfter": decoded.get("notAfter"),
        }
    except Exception:
        return {}
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def _name_to_string(value: object) -> str | None:
    if not isinstance(value, tuple):
        return None
    parts = []
    for group in value:
        if not isinstance(group, tuple):
            continue
        for item in group:
            if (
                isinstance(item, tuple)
                and len(item) == 2
                and isinstance(item[0], str)
                and isinstance(item[1], str)
            ):
                parts.append(f"{item[0]}={item[1]}")
    return ", ".join(parts) or None
