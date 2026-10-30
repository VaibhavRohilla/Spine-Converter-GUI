"""Run with the isolated installed wheel Python and a new output directory.

Uses public CLI, API and BundleService; never substitutes a test converter.
"""

import hashlib
import json
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from zipfile import ZipFile

import fnx_spine_forge.binary as binary
from fnx_spine_forge.bundle import BundleService
from fnx_spine_forge.bundle_models import BundleRequest, SkeletonFormat

root = Path(__file__).resolve().parents[1]
out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=False)
cli = Path(sys.executable).with_name("spine-forge")


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def command(*args):
    r = subprocess.run(
        [str(cli), *map(str, args)], cwd="/tmp", capture_output=True, text=True, timeout=30
    )
    return {
        "command": [str(cli), *map(str, args)],
        "exit_code": r.returncode,
        "stdout": json.loads(r.stdout),
        "stderr": r.stderr,
    }


source = out / "source"
source.mkdir()
fixtures = root / "tests/fixtures/binary"
for src, dst in [
    ("animated_region_4_2_43.json", "asset.json"),
    ("animated_region.atlas", "asset.atlas"),
]:
    shutil.copyfile(fixtures / src, source / dst)
# Independently specified 64x32 test texture; no image conversion is performed.


def chunk(kind, payload):
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload))
    )


(source / "page.png").write_bytes(
    b"\x89PNG\r\n\x1a\n"
    + chunk(b"IHDR", struct.pack(">IIBBBBB", 64, 32, 8, 6, 0, 0, 0))
    + chunk(b"IDAT", zlib.compress((b"\0" + b"\xff" * 256) * 32))
    + chunk(b"IEND", b"")
)
before = {p.name: sha(p) for p in source.iterdir()}
results = [command("binary-capabilities")]
for name in ["one.zip", "two.zip"]:
    r = command(
        "bundle",
        "convert",
        "--input",
        source,
        "--target",
        "4.2.43",
        "--container",
        "zip",
        "--skeleton-format",
        "binary",
        "--output",
        out / name,
        "--experimental-structural",
    )
    assert r["exit_code"] == 0, r
    results.append(r)
assert (out / "one.zip").read_bytes() == (out / "two.zip").read_bytes()
with ZipFile(out / "one.zip") as z:
    assert hashlib.sha256(z.read("page.png")).hexdigest() == before["page.png"]
    assert hashlib.sha256(z.read("asset.skel")).hexdigest() == json.loads(
        (root / "docs/evidence/B3_binary_hardening/qualification.json").read_text()
    )["encoder_comparisons"][0]["binarySha256"]
for container in ["folder", "zip"]:
    r = command(
        "bundle",
        "convert",
        "--input",
        out / "one.zip",
        "--target",
        "4.2.43",
        "--container",
        container,
        "--output",
        out / (f"json-{container}.zip" if container == "zip" else "json-folder"),
        "--experimental-structural",
    )
    assert r["exit_code"] == 0, r
    results.append(r)
assert sha(out / "json-folder" / "page.png") == before["page.png"]
api = BundleService().convert_bundle(
    BundleRequest(
        source,
        "4.2.43",
        out / "api.zip",
        skeleton_format=SkeletonFormat.BINARY,
        experimental_structural=True,
    )
)
assert api.published, api.report
assert (out / "api.zip").read_bytes() == (out / "one.zip").read_bytes()
official = fixtures / "official42"
for skeleton_name in ["powerup-ess.skel", "powerup-ess.json"]:
    authentic = out / f"authentic-{skeleton_name.rsplit('.', 1)[-1]}"
    authentic.mkdir()
    for name in [skeleton_name, "powerup.atlas", "powerup.png"]:
        shutil.copyfile(official / name, authentic / name)
    folder_before = {p.name: sha(p) for p in authentic.iterdir()}
    zip_path = out / f"{authentic.name}.zip"
    with ZipFile(zip_path, "w") as archive:
        for path in authentic.iterdir():
            archive.write(path, path.name)
    output_format = "json" if skeleton_name.endswith(".skel") else "binary"
    for input_index, input_path in enumerate([authentic, zip_path]):
        outputs = []
        for index in range(2):
            output_path = out / f"{output_format}-{input_path.stem}-{input_index}-{index}.zip"
            r = command(
                "bundle",
                "convert",
                "--input",
                input_path,
                "--target",
                "4.2.22",
                "--container",
                "zip",
                "--skeleton-format",
                output_format,
                "--output",
                output_path,
            )
            assert r["exit_code"] == 0, r
            results.append(r)
            outputs.append(output_path)
        assert outputs[-1].read_bytes() == outputs[-2].read_bytes()
        with ZipFile(outputs[-1]) as archive:
            assert "powerup.atlas" in archive.namelist()
            assert archive.read("powerup.png") == (official / "powerup.png").read_bytes()
            skeleton_output = "powerup-ess.json" if output_format == "json" else "powerup-ess.skel"
            assert skeleton_output in archive.namelist()
            if output_format == "binary":
                assert archive.read(skeleton_output)[:8].hex() == "48c29958a44b830f"
    assert folder_before == {p.name: sha(p) for p in authentic.iterdir()}
    api_source = authentic
    api_result = BundleService().convert_bundle(
        BundleRequest(
            api_source,
            "4.2.22",
            out / f"api-{output_format}.zip",
            skeleton_format=SkeletonFormat(output_format),
        )
    )
    assert api_result.published, api_result.report
    assert (out / f"api-{output_format}.zip").read_bytes() == outputs[0].read_bytes()
    assert BundleService().inspect_source(out / f"api-{output_format}.zip").manifest.ok
assert before == {p.name: sha(p) for p in source.iterdir()}
module = Path(binary.__file__)
assert module.read_bytes() == (root / "src/fnx_spine_forge/binary.py").read_bytes()
evidence = {
    "wheel": sha(root / "dist/fnx_spine_forge-0.2.0-py3-none-any.whl"),
    "sdist": sha(root / "dist/fnx_spine_forge-0.2.0.tar.gz"),
    "installed_module": str(module),
    "module_matches_checkout": True,
    "source_immutable": True,
    "png_identity": True,
    "experimental_4_2_43_zip_folder_determinism": True,
    "authentic_qualified_4_2_22_workflow": (
        "PASS; installed CLI and API convert ZIP/folder inputs both directions"
    ),
    "commands": results,
    "api": api.report.to_dict(),
}
(out / "installed-wheel.json").write_text(json.dumps(evidence, indent=2) + "\n")
print(json.dumps({k: v for k, v in evidence.items() if k not in ["commands", "api"]}, indent=2))
