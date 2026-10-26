"""Start all authentic fixture sessions; stdout contains only the capability URL."""
from pathlib import Path
from fnx_spine_forge.viewer.server import ViewerServer
from fnx_spine_forge.bundle_models import DependencyMappings
from fnx_spine_forge.viewer.service import BinarySelection, ViewerService
from fnx_spine_forge.json_types import decode_json_object

service = ViewerService()
assets = []
for family in ('3.8', '4.0', '4.1', '4.2', '4.3'):
    root = Path('viewer/fixtures') / family
    asset = service.prepare(root, 'spineboy-pro.json')
    assets.append(asset)
    assets.append(service.prepare(root, 'spineboy-pro.skel', binary=BinarySelection(asset.export_version, 'spineboy.atlas')))
for root in sorted(Path('viewer/fixtures/production').glob('*')):
    if root.is_dir():
        skeletons = list(root.glob('*.json'))
        skeletons = [p for p in skeletons if 'skeleton' in decode_json_object(p.read_text(), 'fixture')]
        if len(skeletons) == 1:
            assets.append(service.prepare(root, skeletons[0].name))
for root in sorted(Path('viewer/fixtures/features').glob('*')):
    if root.is_dir():
        for skeleton in sorted(root.glob('*.json')):
            atlases = sorted(root.glob('*.atlas'))
            for atlas in atlases:
                assets.append(service.prepare(root, skeleton.name, DependencyMappings(atlases={skeleton.name: atlas.name})))
assets.append(service.prepare(Path('viewer/fixtures/source-risk'), 'golden_ingot.json'))
for root in sorted(Path('viewer/fixtures/physics').glob('*')):
    if root.is_dir():
        for skeleton in root.glob('*.json'):
            assets.append(service.prepare(root, skeleton.name))
server = ViewerServer(tuple(assets), Path('viewer/dist'))
print(server.start(), flush=True)
try:
    if server.thread:
        server.thread.join()
except KeyboardInterrupt:
    pass
finally:
    server.close()
