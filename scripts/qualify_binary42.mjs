// Test-only explicit local fixture runner. Never imported by the production viewer.
// Run in a bounded child process: node --max-old-space-size=256 ... (timeout 30s).
import {readFileSync, statSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const [jsonPath, binaryPath, atlasPath] = process.argv.slice(2);
assert.ok(jsonPath && binaryPath && atlasPath, 'Explicit JSON, binary and atlas fixtures required');
function read(path) {
  assert.ok(statSync(path).isFile() && statSync(path).size <= 4 * 1024 * 1024, 'Fixture size limit');
  return readFileSync(path);
}
const root = resolve('node_modules/spine42/node_modules/@esotericsoftware/spine-core');
const pkg = JSON.parse(read(resolve(root, 'package.json')));
assert.equal(pkg.name, '@esotericsoftware/spine-core');
assert.equal(pkg.version, '4.2.43');
const runtime = await import(pathToFileURL(resolve(root, pkg.main)));
const jsonBytes = read(jsonPath), binaryBytes = read(binaryPath), atlasBytes = read(atlasPath);
const atlas = new runtime.TextureAtlas(atlasBytes.toString());
const loader = new runtime.AtlasAttachmentLoader(atlas);
// Copy to a zero-offset buffer: the official reader uses DataView(data.buffer).
const binary = new runtime.SkeletonBinary(loader).readSkeletonData(Uint8Array.from(binaryBytes));
const json = new runtime.SkeletonJson(loader).readSkeletonData(JSON.parse(jsonBytes));
assert.equal(binary.version, json.version);
assert.deepEqual(binary.bones.map(b => [b.name, b.parent?.name]), json.bones.map(b => [b.name, b.parent?.name]));
assert.deepEqual(binary.slots.map(s => [s.name, s.boneData.name]), json.slots.map(s => [s.name, s.boneData.name]));
assert.deepEqual(binary.skins.map(s => s.name), json.skins.map(s => s.name));
assert.deepEqual(binary.animations.map(a => a.name), json.animations.map(a => a.name));
assert.ok(json.bones.length <= 500 && json.animations.length <= 50 && json.skins.length <= 20);
let maximumError = 0, comparisons = 0, samples = 0;
function compare(a, b, path = '') {
  if (typeof a === 'number') {
    assert.ok(Number.isFinite(a) && Number.isFinite(b), path + ' nonfinite');
    const error = Math.abs(a - b);
    maximumError = Math.max(maximumError, error);
    comparisons++;
    assert.ok(error <= 0.0003 + Math.abs(a) * 0.000002, `${path}: ${a} != ${b}`);
  } else if (Array.isArray(a)) {
    assert.equal(a.length, b.length, path);
    a.forEach((value, i) => compare(value, b[i], path + '/' + i));
  } else assert.deepEqual(a, b, path);
}
function pose(data, skin, animation, time) {
  const skeleton = new runtime.Skeleton(data);
  if (skin) skeleton.setSkinByName(skin);
  skeleton.setToSetupPose();
  const events = [];
  if (animation) {
    const state = new runtime.AnimationState(new runtime.AnimationStateData(data));
    state.addListener({event: (_entry, e) => events.push([e.data.name, e.time, e.intValue, e.floatValue, e.stringValue])});
    state.setAnimation(0, animation, false);
    state.update(time);
    state.apply(skeleton);
  }
  skeleton.updateWorldTransform(runtime.Physics.update);
  return [skeleton.bones.map(b => [b.a,b.b,b.c,b.d,b.worldX,b.worldY]),
    skeleton.slots.map(s => {
      const a = s.getAttachment();
      let vertices = [];
      if (a instanceof runtime.RegionAttachment) {
        vertices = Array(8).fill(0); a.computeWorldVertices(s, vertices, 0, 2);
      } else if (a instanceof runtime.VertexAttachment) {
        vertices = Array(a.worldVerticesLength).fill(0); a.computeWorldVertices(s,0,a.worldVerticesLength,vertices,0,2);
      }
      return [s.data.name, a?.name ?? null, [s.color.r,s.color.g,s.color.b,s.color.a],
        s.darkColor ? [s.darkColor.r,s.darkColor.g,s.darkColor.b] : null, vertices, Array.from(s.deform)];
    }), skeleton.drawOrder.map(s => s.data.name), events];
}
for (const skin of json.skins.length ? json.skins.map(s => s.name) : [null]) {
  compare(pose(json,skin,null,0),pose(binary,skin,null,0),'setup'); samples++;
  for (let i=0; i<json.animations.length; i++) {
    const animation = json.animations[i];
    compare(animation.duration, binary.animations[i].duration, 'duration');
    assert.ok(animation.duration <= 60);
    for (let sample=0; sample<=40; sample++) {
      const time = animation.duration * sample / 40;
      compare(pose(json,skin,animation.name,time),pose(binary,skin,animation.name,time),animation.name+'/'+time);
      samples++;
    }
  }
}
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
console.log(JSON.stringify({readerSuccess:true,animationEvaluation:true,runtime:pkg.name+'@'+pkg.version,
 runtimeReaderSha256:sha(read(resolve(root,'dist/SkeletonBinary.js'))),
 jsonSha256:sha(jsonBytes),binarySha256:sha(binaryBytes),atlasSha256:sha(atlasBytes),
 exportVersion:json.version,animations:json.animations.map(a=>({name:a.name,duration:a.duration,timelines:a.timelines.length})),
 samples,comparisons,maximumError}));
