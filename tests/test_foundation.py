"""Run: PYTHONPATH=src python -m unittest discover -s tests -v"""

import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from fnx_spine_forge.detection import atlas_page_names, skeleton_version
from fnx_spine_forge.inspection import InspectionService
from fnx_spine_forge.registry import Migration, MigrationRegistry, default_registry

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
        self.assertEqual(skeleton_version(SKELETON), (True, "3.8.75", None))

    def test_unrelated_json_not_skeleton(self):
        self.assertEqual(skeleton_version(b'{"tool": "report"}'), (False, None, None))

    def test_missing_version_reported(self):
        is_skeleton, version, err = skeleton_version(b'{"skeleton":{},"bones":[]}')
        self.assertTrue(is_skeleton)
        self.assertIsNone(version)
        self.assertIsNotNone(err)

    def test_atlas_pages(self):
        self.assertEqual(atlas_page_names(ATLAS), ["texture.png"])


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
            self.assertIn("BINARY_NOT_YET_SUPPORTED", [x.code for x in report.diagnostics])


class RouteTests(unittest.TestCase):
    def test_no_fake_implementation(self):
        with self.assertRaisesRegex(ValueError, "Unsupported migration"):
            default_registry().plan("3.8.75", "4.2.43")

    def test_migration_graph(self):
        registry = MigrationRegistry()
        registry.register(Migration("3.8", "4.0", "first", lambda b: b))
        registry.register(Migration("4.0", "4.2", "second", lambda b: b))
        self.assertEqual([x.label for x in registry.plan("3.8.75", "4.2.43")], ["first", "second"])

    def test_duplicate_route_rejected(self):
        registry = MigrationRegistry()
        edge = Migration("3.8", "4.2", "one", lambda b: b)
        registry.register(edge)
        with self.assertRaises(ValueError):
            registry.register(edge)


if __name__ == "__main__":
    unittest.main()
