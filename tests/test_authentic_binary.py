"""Authentic-source decoder proof. No self-roundtrip is used as its reference."""
import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from fnx_spine_forge.binary import BinaryCodecRegistry, BinaryError, BinaryLimits
from fnx_spine_forge.conversion.planner import ConversionPlanner
from fnx_spine_forge.viewer.binary_policy import admit_binary

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/binary/official42"


def codec():
    return BinaryCodecRegistry().codec("4.2.22", experimental=True)


def reference(candidate):
    return subprocess.run(
        ["node", "--max-old-space-size=256", str(ROOT / "scripts/compare_binary42.mts"),
         str(FIXTURES / "powerup-ess.skel"), str(FIXTURES / "powerup.atlas"), str(candidate)],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )


def test_authentic_provenance_and_independent_decoder(tmp_path):
    for row in json.loads((FIXTURES / "provenance.json").read_text()):
        assert hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest() == row["sha256"]
    original = (FIXTURES / "powerup-ess.skel").read_bytes()
    decoded = codec().decode(original)
    assert decoded["skeleton"]["spine"] == "4.2.22"
    path = tmp_path / "decoded.json"
    path.write_text(json.dumps(decoded))
    result = reference(path)
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["statistics"] == {"numeric": 2180, "exact": 207, "maximumError": 0}
    assert evidence["inventory"]["keyframes"] == 182
    assert evidence["inventory"]["attachments"] == {"RegionAttachment": 13}
    assert evidence["inventory"]["deformFrames"] == 0
    # The reference binary is original, independently authenticated bytes.
    assert evidence["binarySha256"] == hashlib.sha256(original).hexdigest()
    encoded = tmp_path / "output.skel"
    encoded.write_bytes(codec().encode(decoded))
    assert encoded.read_bytes() == codec().encode(decoded)
    assert reference(encoded).returncode == 0
    # Encoding decoded input is extra evidence, not an independent JSON source.
    with pytest.raises(ValueError, match="UNTRUSTED|UNAPPROVED|NOT_APPROVED"):
        admit_binary(encoded.read_bytes(), "4.2.22")
    assert (FIXTURES / "powerup-ess.skel").read_bytes() == original


def mutate(document, kind):
    if kind == "hierarchy":
        document["bones"][2]["parent"] = "root"
    elif kind == "setup":
        document["bones"][1]["x"] += 1
    elif kind == "region":
        document["skins"][0]["attachments"]["left-wing"]["wing"]["width"] += 1
    elif kind == "slot":
        document["slots"][0]["color"] = "ff0000ff"
    else:
        timelines = document["animations"]["bounce"]["bones"]
        if kind == "curve":
            frame = next(f for b in timelines.values() for frames in b.values()
                         for f in frames if isinstance(f.get("curve"), list))
            frame["curve"][1] += 10
        else:
            frames = next(frames for b in timelines.values() for name, frames in b.items()
                          if name == "rotate" and len(frames) > 1)
            if kind == "time":
                frames[1]["time"] += 0.001
            else:
                frames[0]["value"] += 5


@pytest.mark.parametrize("kind", ["hierarchy", "setup", "region", "slot", "curve", "time", "value"])
def test_reference_detects_semantic_corruption(kind, tmp_path):
    document = copy.deepcopy(codec().decode((FIXTURES / "powerup-ess.skel").read_bytes()))
    mutate(document, kind)
    path = tmp_path / "corrupted.json"
    path.write_text(json.dumps(document))
    result = reference(path)
    assert result.returncode != 0
    assert "AssertionError" in result.stderr
    assert "!=" in result.stderr or "Expected values to be strictly equal" in result.stderr


def test_authentic_version_is_experimental_and_has_no_migration_edges():
    with pytest.raises(BinaryError, match="experimental"):
        BinaryCodecRegistry().codec("4.2.22")
    for version in ("4.2.43", "4.1.56", "4.3.13"):
        assert not ConversionPlanner().structural_plan("4.2.22", version).executable
        assert not ConversionPlanner().structural_plan(version, "4.2.22").executable


@pytest.mark.parametrize("name", ["spineboy-ess", "coin-pro", "vine-pro"])
def test_authentic_advanced_content_fails_closed(name):
    with pytest.raises(BinaryError, match="Unsupported"):
        codec().decode((FIXTURES / f"{name}.skel").read_bytes())


def test_authentic_truncation_and_oversize_rejection():
    payload = (FIXTURES / "powerup-ess.skel").read_bytes()
    for length in (0, 8, 16, 100, len(payload)//2, len(payload)-1):
        with pytest.raises(BinaryError):
            codec().decode(payload[:length])
    with pytest.raises(BinaryError):
        BinaryCodecRegistry().codec(
            "4.2.22", experimental=True, limits=BinaryLimits(max_bytes=len(payload)-1)
        ).decode(payload)
