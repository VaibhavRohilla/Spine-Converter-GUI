"""Build an unapproved review inventory from retained captures and regression evidence."""
import hashlib
import json
from pathlib import Path

root = Path('docs/evidence/B4')
manifest = json.loads(Path('src/fnx_spine_forge/viewer/runtime_manifest.json').read_text())
revisions = {row['revision'] for row in manifest['runtimes'] if row['embeddedImplemented']}
source_hashes = {}
for path in Path('viewer/fixtures').rglob('*'):
    if path.is_file():
        source_hashes.setdefault(hashlib.sha256(path.read_bytes()).hexdigest(), []).append(str(path))
criteria = {
    'spineboy': 'Silhouette, pose, mesh deformation, atlas orientation and attachment order',
    'coin': 'Clipping boundary, alpha edges, atlas orientation and authored blend response',
    'goblins': 'Skin attachments, mesh deformation and draw order',
    'raptor': 'Mesh deformation, layering and atlas edges',
    'vine': 'Path-constrained geometry and deformation',
    'tank': 'Layering, mesh deformation and attachment order',
    'windmill': 'Constraint-driven pose and atlas edges',
    'physics': 'Physics-constrained pose at the recorded fixed-step sample',
}
records = []
for path in sorted((root / 'candidate-references').glob('*.json')):
    meta = json.loads(path.read_text())
    assert meta['status'] == 'CANDIDATE_NOT_INDEPENDENTLY_ACCEPTED'
    assert meta['runtimeRevision'] in revisions
    frame_hash = hashlib.sha256(path.with_suffix('.png').read_bytes()).hexdigest()
    assert frame_hash == meta['sha256']
    sources = json.loads(meta['sources'])
    for digest in sources['original'].values():
        assert digest in source_hashes, (path, digest)
    result = json.loads((root / 'visual-comparisons' / path.name).read_text())
    assert result['referenceSha256'] == frame_hash
    threshold = result['tolerance']
    passed = all(result['metrics'][key] <= threshold[key] for key in ('changedFraction', 'meanAbsoluteError', 'alphaMeanError', 'maximumChannelError'))
    assert passed, path
    feature = next((value for key, value in criteria.items() if key in meta['sourceSkeleton'].lower()), 'Authored pose, alpha edges, layering and texture placement')
    if path.stem.startswith('derived-blend'):
        feature = f"Derived {path.stem.rsplit('-', 1)[1]} blend on opaque [0.2, 0.3, 0.4, 1] background; clipping and alpha edges"
    records.append({
        'id': path.stem, 'status': meta['status'], 'frameSha256': frame_hash,
        'sourceAssets': {name: {'sha256': digest, 'matchingFixturePaths': source_hashes[digest]} for name, digest in sources['original'].items()},
        'renderedSkeletonSha256': sources['renderedSkeleton'],
        'runtimeRevision': meta['runtimeRevision'], 'exportVersion': meta['sourceVersion'],
        'animation': meta['animation'], 'sampledTime': meta['timestamp'], 'skin': meta['skin'],
        'camera': meta['camera'], 'viewport': meta['viewport'], 'background': meta['background'],
        'alphaPolicy': 'RGBA capture; background is the explicit value above; authored atlas PMA',
        'expectedVisualFeature': feature, 'threshold': threshold, 'actualRegression': result,
        'review': {'reviewerIdentity': None, 'date': None, 'exactFrameSha256': frame_hash,
                   'exactAssetHashes': sources['original'], 'evaluatedCriteria': [],
                   'decision': 'PENDING', 'documentedExclusions': []},
    })
assert len(records) == 44
negative = []
for path in sorted((root / 'visual-comparisons').glob('negative-*.json')):
    metrics = json.loads(path.read_text())
    threshold = json.loads(Path('viewer/tests/visual-tolerances.json').read_text())['default']
    detected = any(metrics[key] > threshold[key] for key in ('changedFraction', 'meanAbsoluteError', 'alphaMeanError', 'maximumChannelError'))
    assert detected, path
    negative.append({'id':path.stem, 'metrics':metrics, 'threshold':threshold, 'actualRegression':'BROKEN_RENDERING_DETECTED'})
assert len(negative) == 6
out = root / 'closure-20261027'
(out / 'visual-review-manifest.json').write_text(json.dumps({'status':'CANDIDATE_NOT_INDEPENDENTLY_ACCEPTED', 'candidates':records, 'negativeTests':negative}, indent=2)+'\n')
lines = ['# B4 independent visual review queue', '', 'Status: **CANDIDATE_NOT_INDEPENDENTLY_ACCEPTED**. No approvals have been supplied.', '',
 'The [review manifest](evidence/B4/closure-20261027/visual-review-manifest.json) binds all 44 retained images to exact source/frame hashes, runtime revision, animation/time/skin, camera/viewport/DPR, alpha/background, criteria, thresholds and measured regression results. All source hashes resolve to local fixtures. Six deliberately broken cases were detected.', '',
 'An authorized reviewer should inspect each linked image and its diff/overlay, evaluate the listed criteria against an independently accepted source, and submit identity, date, exact asset and frame hashes, evaluated criteria, APPROVE or REJECT, and explicit exclusions. The pending records are a submission template, not approvals. Preserve submitted review records separately; do not rewrite candidate images to secure approval.', '',
 'Repeatability is not artistic acceptance or source-to-converted visual equivalence. Derived blend fixtures are identified explicitly. Candidate 11 is a converted private asset and establishes no conversion equivalence. Hardware GPU acceptance requires separate evidence.', '',
 '| Candidate | Frame | Review criteria | Regression |', '|---|---|---|---|']
for record in records:
    ident=record['id']
    lines.append(f"| {ident} | [PNG](evidence/B4/candidate-references/{ident}.png) / [overlay](evidence/B4/visual-comparisons/{ident}-overlay.png) | {record['expectedVisualFeature']} | PASS; review PENDING |")
Path('docs/B4_VISUAL_REVIEW.md').write_text('\n'.join(lines)+'\n')
print('Verified 44 source/frame identities and candidate regressions; 6 negative cases detected; approvals: 0')
