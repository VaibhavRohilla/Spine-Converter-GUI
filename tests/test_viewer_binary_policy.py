"""Malformed approval metadata must fail closed before binary runtime admission."""

import json
from dataclasses import FrozenInstanceError

import pytest

from fnx_spine_forge.viewer.binary_policy import MAX_BINARY_BYTES, _parse_policy

DIGEST = "a" * 64


def policy(**changes):
    record = {"bytes": 123, "version": "4.2.22", "source": "https://example.com/source.skel"}
    record.update(changes)
    return json.dumps({DIGEST: record}).encode()


@pytest.mark.parametrize("size", [True, False, 0, -1, 1.5, "123", MAX_BINARY_BYTES + 1])
def test_policy_requires_bounded_integer_length(size):
    with pytest.raises(ValueError, match="Invalid binary trust policy"):
        _parse_policy(policy(bytes=size))


@pytest.mark.parametrize("version", [None, 42, "", "4", "4.2 malicious"])
def test_policy_requires_version_identity(version):
    with pytest.raises(ValueError, match="Invalid binary trust policy"):
        _parse_policy(policy(version=version))


@pytest.mark.parametrize("source", [None, "file:///tmp/a", "http://example.com/a", "https://", "https://user:secret@example.com/a"])
def test_policy_requires_https_provenance_without_credentials(source):
    with pytest.raises(ValueError, match="Invalid binary trust policy"):
        _parse_policy(policy(source=source))


def test_policy_rejects_surplus_fields_bad_hashes_and_unmatched_bad_records():
    with pytest.raises(ValueError, match="Invalid binary trust policy"):
        _parse_policy(policy(approved=True))
    with pytest.raises(ValueError, match="Invalid binary trust policy"):
        _parse_policy(policy().replace(DIGEST.encode(), b"invalid"))
    with pytest.raises(ValueError, match="Invalid binary trust policy"):
        _parse_policy(policy()[:-1] + b', "invalid": {}}')


def test_policy_produces_immutable_domain_records():
    records = _parse_policy(policy())
    assert len(records) == 1
    assert records[0].digest == DIGEST
    assert records[0].byte_length == 123
    assert records[0].version == "4.2.22"
    with pytest.raises(FrozenInstanceError):
        records[0].version = "4.3.75-beta"


def test_runtime_capabilities_expose_binary_restriction():
    from fnx_spine_forge.viewer.registry import RuntimeFeature, RuntimeRegistry

    for runtime in RuntimeRegistry().entries():
        assert (RuntimeFeature.APPROVED_BINARY_ONLY in runtime.capabilities) == runtime.binary


@pytest.mark.parametrize("suffix", [".skel", ".SKEL", ".json", ".dat", ""])
@pytest.mark.parametrize("zipped", [False, True])
def test_explicit_binary_cannot_bypass_admission_by_path(tmp_path, monkeypatch, suffix, zipped):
    from zipfile import ZipFile

    from fnx_spine_forge.bundle import BundleService
    from fnx_spine_forge.viewer.service import BinarySelection, ViewerService

    def forbidden(*args, **kwargs):
        pytest.fail("Untrusted explicit binary reached B1/B3 inspection")

    monkeypatch.setattr(BundleService, "inspect_source", forbidden)
    name = f"nested/renamed{suffix}"
    source = tmp_path / "folder"
    (source / "nested").mkdir(parents=True)
    (source / name).write_bytes(b"\x08" + b"4.2.22" + b"\xff" * 20)
    if zipped:
        archive = tmp_path / "input.zip"
        with ZipFile(archive, "w") as output:
            output.write(source / name, name)
        source = archive
    with pytest.raises(ValueError, match="UNTRUSTED_BINARY_DISABLED"):
        ViewerService().prepare(source, name, binary=BinarySelection("4.2.22", "fake.atlas"))
