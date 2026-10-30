"""Fail-closed binary admission; no platform currently qualifies untrusted parsing.

The packaged manifest identifies previously verified official fixtures, not transport
checksums or user claims. Adding approval requires a reviewed release change.
"""

import re
from dataclasses import dataclass
from hashlib import sha256
from importlib.resources import files
from urllib.parse import urlsplit

from ..json_types import decode_json_object, is_document
from ..versions import valid_version

MAX_BINARY_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class ApprovedBinary:
    digest: str
    byte_length: int
    version: str
    source: str


def _parse_policy(payload: bytes) -> tuple[ApprovedBinary, ...]:
    document = decode_json_object(payload, "Binary trust policy")
    approvals: list[ApprovedBinary] = []
    for digest, record in document.items():
        if (
            re.fullmatch(r"[a-f0-9]{64}", digest) is None
            or not is_document(record)
            or set(record) != {"bytes", "version", "source"}
        ):
            raise ValueError("Invalid binary trust policy record")
        length, version, source = record["bytes"], record["version"], record["source"]
        if (
            type(length) is not int
            or not 0 < length <= MAX_BINARY_BYTES
            or not isinstance(version, str)
            or not valid_version(version)
            or not isinstance(source, str)
        ):
            raise ValueError("Invalid binary trust policy identity")
        origin = urlsplit(source)
        if origin.scheme != "https" or not origin.hostname or origin.username or origin.password:
            raise ValueError("Invalid binary trust policy provenance")
        approvals.append(ApprovedBinary(digest, length, version, source))
    return tuple(approvals)


def admit_binary(payload: bytes, version: str | None = None) -> None:
    if len(payload) > MAX_BINARY_BYTES:
        raise ValueError("VIEWER_RESOURCE_LIMIT_EXCEEDED: binary exceeds 32 MiB")
    policy = _parse_policy(files(__package__).joinpath("trusted_binary.json").read_bytes())
    digest = sha256(payload).hexdigest()
    record = next((entry for entry in policy if entry.digest == digest), None)
    if record is None or record.byte_length != len(payload):
        raise ValueError(
            "UNTRUSTED_BINARY_DISABLED: no qualified process resource isolation; "
            "only immutable approved fixture bytes are admitted"
        )
    if version is not None and version != record.version:
        raise ValueError("RUNTIME_VERSION_MISMATCH: binary approval version differs")
