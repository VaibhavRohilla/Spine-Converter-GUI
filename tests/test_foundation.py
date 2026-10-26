"""Run: PYTHONPATH=src python -m unittest discover -s tests -v"""

import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from fnx_spine_forge.conversion import ConversionPlanner, ConversionQualificationRegistry
from fnx_spine_forge.conversion.registry import EXACT_ROUTE_PAIRS
from fnx_spine_forge.detection import recognize_skeleton
from fnx_spine_forge.inspection import InspectionService
from fnx_spine_forge.json_types import decode_json_object
from fnx_spine_forge.parsers import parse_atlas

SKELETON = json.dumps(
    {
        "skeleton": {"spine": "3.8.75"},
        "bones": [{"name": "root"}],
        "slots": [],
        "skins": {},
        "animations": {"idle": {}},
    }
).encode()
ATLAS = (
    b"texture.png\nsize: 32,32\n"
    b"format: RGBA8888\nfilter: Linear,Linear\n"
    b"repeat: none\n\n"
    b"body\n  rotate: false\n"
    b"  xy: 0, 0\n  size: 8, 8\n"
    b""
)


class DetectionTests(unittest.TestCase):
    def test_detect_spine_version(self):
        recognition = recognize_skeleton(decode_json_object(SKELETON, "fixture"))
        self.assertIsNotNone(recognition)
        self.assertEqual(recognition.version, "3.8.75")

    def test_unrelated_json_not_skeleton(self):
        self.assertIsNone(recognize_skeleton({"tool": "report"}))

    def test_missing_version_reported(self):
        recognition = recognize_skeleton({"skeleton": {}, "bones": []})
        self.assertIsNotNone(recognition)
        self.assertIsNone(recognition.version)
        self.assertIsNotNone(recognition.diagnostic)

    def test_atlas_pages(self):
        self.assertEqual(parse_atlas(ATLAS).pages, ("texture.png",))


class InspectionTests(unittest.TestCase):
    def test_folder_valid(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            (path / "GCT.json").write_bytes(SKELETON)
            (path / "GCT.atlas").write_bytes(ATLAS)
            (path / "texture.png").write_bytes(b"not actual image, scanner only")
            result = InspectionService().inspect(d)
            self.assertTrue(result.ok)
            self.assertEqual(len([a for a in result.assets if a.kind == "skeleton_json"]), 1)
            self.assertEqual(len([dep for dep in result.dependencies if dep.resolved]), 2)

    def test_missing_page_is_error(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "GCT.json").write_bytes(SKELETON)
            (Path(d) / "GCT.atlas").write_bytes(ATLAS)
            report = InspectionService().inspect(d)
            self.assertFalse(report.ok)
            self.assertIn("MISSING_TEXTURE", [x.code for x in report.diagnostics])

    def test_zip_and_fallback_nested_texture(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "asset.zip"
            with ZipFile(path, "w") as z:
                z.writestr("export/GCT.json", SKELETON)
                z.writestr("export/GCT.atlas", ATLAS)
                z.writestr("textures/texture.png", b"data")
            report = InspectionService().inspect(str(path))
            self.assertTrue(report.ok)
            self.assertTrue(any(x.resolved == "textures/texture.png" for x in report.dependencies))

    def test_ambiguous_texture_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            (path / "GCT.json").write_bytes(SKELETON)
            (path / "GCT.atlas").write_bytes(ATLAS)
            (path / "a").mkdir()
            (path / "b").mkdir()
            (path / "a" / "texture.png").write_bytes(b"a")
            (path / "b" / "texture.png").write_bytes(b"b")
            report = InspectionService().inspect(d)
            self.assertIn("AMBIGUOUS_TEXTURE", [x.code for x in report.diagnostics])

    def test_zip_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "evil.zip"
            with ZipFile(path, "w") as z:
                z.writestr("../outside.txt", "bad")
            report = InspectionService().inspect(str(path))
            self.assertIn("INPUT_ERROR", [x.code for x in report.diagnostics])

    def test_zip_duplicate_rejected(self):
        import warnings

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "duplicated.zip"
            with ZipFile(path, "w") as z:
                z.writestr("file.atlas", "one")
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    z.writestr("file.atlas", "two")
            report = InspectionService().inspect(str(path))
            self.assertFalse(report.ok)

    def test_binary_not_misclassified_as_json(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "symbol.skel").write_bytes(b"\x00\x00\x03\x08")
            report = InspectionService().inspect(d)
            self.assertEqual(report.assets[0].kind, "skeleton_binary")
            self.assertIn("BINARY_TRUNCATED", [x.code for x in report.diagnostics])
            self.assertFalse(report.ok)


class RouteTests(unittest.TestCase):
    def test_no_fake_implementation(self):
        planned = ConversionPlanner().plan("3.8.75", "4.2.43")
        self.assertFalse(planned.executable)
        self.assertFalse(planned.qualification.qualified)
        self.assertEqual(ConversionPlanner().structural_plan("3.8.999", "4.2.43").route, ())

    def test_migration_graph(self):
        routes = ConversionPlanner().candidate_routes("3.5.51", "4.3.13")
        self.assertTrue(routes)
        for route in routes:
            self.assertEqual((route[0], route[-1]), ("3.5.51", "4.3.13"))
            self.assertTrue(all(edge in EXACT_ROUTE_PAIRS for edge in zip(route, route[1:])))

    def test_duplicate_route_rejected(self):
        record = ConversionQualificationRegistry().record(("3.8.99", "4.2.43"))
        with self.assertRaises(ValueError):
            ConversionQualificationRegistry((record, record))


if __name__ == "__main__":
    unittest.main()
