// Isolated, bounded fixture auditor. Never imported by the B4 production viewer.
// Reference semantics are extracted ONLY from the official binary reader.
import {readFileSync, statSync} from 'node:fs';
import {resolve} from 'node:path';
import * as r from '../node_modules/spine42/node_modules/@esotericsoftware/spine-core/dist/index.js';
import {z} from 'zod';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';

type Value = null | boolean | number | string | Value[] | {[key: string]: Value};
type Comparison = {numeric: number; exact: number; maximumError: number};
type Bone = {name:string; parent:string|null; setup:number[]; inherit:number; skin:boolean; color:number[]|null};
type Slot = {name:string; bone:string; color:number[]|null; dark:number[]|null; attachment:string|null; blend:number; visible:boolean};
type Region = {slotIndex:number; name:string; path:string; attachmentName:string; transform:number[]; color:number[]|null; offset:number[]; uvs:number[]};
type Timeline = {kind:string; owner:number; frames:number[]; curves:number[]};
type Snapshot = {version:string; bounds:number[]; bones:Bone[]; slots:Slot[];
  skins:{name:string; attachments:Region[]}[];
  animations:{name:string; duration:number; timelines:Timeline[]}[]};
const [binaryPath, atlasPath, jsonPath] = process.argv.slice(2);
function read(path: string) {
  assert.ok(statSync(path).isFile() && statSync(path).size <= 4 * 1024 * 1024);
  return readFileSync(path);
}
const root = resolve('node_modules/spine42/node_modules/@esotericsoftware/spine-core');
const pkg = z.object({name:z.string(),version:z.string()}).parse(JSON.parse(read(resolve(root, 'package.json')).toString()));
assert.equal(pkg.name, '@esotericsoftware/spine-core');
assert.equal(pkg.version, '4.2.43');
assert.ok(binaryPath && atlasPath, 'Explicit binary and atlas paths required');
const bytes = read(binaryPath);
const atlas = new r.TextureAtlas(read(atlasPath).toString());
const loader = new r.AtlasAttachmentLoader(atlas);
const referenceData = binaryPath.endsWith('.json')
  ? new r.SkeletonJson(loader).readSkeletonData(bytes.toString())
  : new r.SkeletonBinary(loader).readSkeletonData(Uint8Array.from(bytes));
const sha = (value: Uint8Array) => createHash('sha256').update(value).digest('hex');
const color = (c: r.Color | null) => c ? [c.r, c.g, c.b, c.a] : null;
const counts = (values: string[]) => Object.fromEntries([...new Set(values)].sort().map(k => [k, values.filter(v => v === k).length]));
function inventory(data: r.SkeletonData) {
  const attachments = data.skins.flatMap(s => s.getAttachments().map(a => a.attachment));
  const timelines = data.animations.flatMap(a => a.timelines);
  let vertices = 0, influences = 0;
  for (const a of attachments) {
    if (!(a instanceof r.MeshAttachment)) continue;
    vertices += a.worldVerticesLength / 2;
    if (a.bones) {
      for (let i = 0; i < a.bones.length;) { const n = a.bones[i]!; influences += n; i += n + 1; }
    }
  }
  return {version: data.version, bones: data.bones.length, slots: data.slots.length,
    skins: data.skins.map(s => s.name), attachments: counts(attachments.map(a => a.constructor.name)),
    constraints: {ik: data.ikConstraints.length, transform: data.transformConstraints.length,
      path: data.pathConstraints.length, physics: data.physicsConstraints.length},
    animations: data.animations.map(a => ({name: a.name, duration: a.duration})),
    timelines: counts(timelines.map(t => t.constructor.name)),
    keyframes: timelines.reduce((n,t) => n + t.getFrameCount(), 0), meshVertices: vertices,
    weightedInfluences: influences,
    deformFrames: timelines.filter(t => t instanceof r.DeformTimeline).reduce((n,t) => n + t.getFrameCount(), 0),
    eventDefinitions: data.events.length,
    eventFrames: timelines.filter(t => t instanceof r.EventTimeline).reduce((n,t) => n + t.getFrameCount(), 0)};
}
// This deliberately narrow comparable model rejects advanced content. Inventory
// of an advanced fixture is not a semantic comparison or an FNX qualification.
function semantics(data: r.SkeletonData): Snapshot {
  assert.ok(data.version);
  assert.ok(data.bones.length <= 500 && data.animations.length <= 50 && data.skins.length <= 20);
  for (const key of ['ikConstraints','transformConstraints','pathConstraints','physicsConstraints','events'] as const) {
    assert.equal(data[key].length, 0, 'Unverified category: ' + key);
  }
  return {
    version: data.version, bounds: [data.x,data.y,data.width,data.height,data.referenceScale],
    bones: data.bones.map(b => ({name:b.name,parent:b.parent?.name ?? null,
      setup:[b.length,b.x,b.y,b.rotation,b.scaleX,b.scaleY,b.shearX,b.shearY],
      inherit:b.inherit,skin:b.skinRequired,color:color(b.color)})),
    slots: data.slots.map(s => ({name:s.name,bone:s.boneData.name,color:color(s.color),
      dark:color(s.darkColor),attachment:s.attachmentName,blend:s.blendMode,visible:s.visible})),
    skins: data.skins.map(s => {
      assert.equal(s.bones.length, 0); assert.equal(s.constraints.length, 0);
      return {name:s.name,attachments:s.getAttachments().map(({slotIndex,name,attachment:a}) => {
        assert.ok(a instanceof r.RegionAttachment, 'Unverified attachment: ' + a.constructor.name);
        assert.equal(a.sequence, null, 'Unverified sequence');
        return {slotIndex,name,path:a.path,attachmentName:a.name,
          transform:[a.x,a.y,a.scaleX,a.scaleY,a.rotation,a.width,a.height],
          color:color(a.color),offset:Array.from(a.offset),uvs:Array.from(a.uvs)};
      })};
    }),
    animations: data.animations.map((a: r.Animation) => ({name:a.name,duration:a.duration,timelines:a.timelines.map((t: r.Timeline) => {
      assert.ok(t instanceof r.RotateTimeline || t instanceof r.TranslateTimeline || t instanceof r.ScaleTimeline || t instanceof r.ShearTimeline || t instanceof r.RGBATimeline,
        'Unverified timeline: ' + t.constructor.name);
      return {kind:t.constructor.name,owner:t instanceof r.RGBATimeline ? t.slotIndex : t.boneIndex,
        frames:Array.from(t.frames),curves:Array.from(z.union([z.array(z.number().finite()).max(100000),z.instanceof(Float32Array)]).parse(Reflect.get(t, "curves")))};
    })}))
  };
}
function compare(expected: Value, actual: Value, path: string, stats: Comparison): void {
  if (typeof expected === 'number') {
    assert.ok(typeof actual === 'number', path);
    assert.ok(Number.isFinite(expected) && Number.isFinite(actual), path);
    const error = Math.abs(expected - actual);
    stats.maximumError = Math.max(stats.maximumError, error); stats.numeric++;
    assert.ok(error <= 1e-6 + 2e-6 * Math.abs(expected), `${path}: ${expected} != ${actual}`);
  } else if (Array.isArray(expected)) {
    assert.ok(Array.isArray(actual), path); assert.equal(actual.length, expected.length, path);
    expected.forEach((v,i) => compare(v,actual[i]!,path+'/'+i,stats));
  } else if (expected !== null && typeof expected === 'object') {
    assert.ok(actual !== null && typeof actual === 'object' && !Array.isArray(actual),path);
    assert.deepEqual(Object.keys(actual),Object.keys(expected),path);
    for (const k of Object.keys(expected)) compare(expected[k]!,actual[k]!,path+'/'+k,stats);
  } else { assert.equal(actual,expected,path); stats.exact++; }
}
const result = {runtime:pkg.name+'@'+pkg.version,
  runtimeReaderSha256:sha(read(resolve(root,'dist/SkeletonBinary.js'))),
  ...(binaryPath.endsWith('.skel') ? {binarySha256:sha(bytes)} : {}),
  referenceInputSha256:sha(bytes),referenceFormat:binaryPath.endsWith('.json')?'official-json':'official-binary',
  atlasSha256:sha(read(atlasPath)),inventory:inventory(referenceData),
  semanticCompared:false,unverified:['serialized Bezier control handles (runtime exposes evaluated curve tables)',
    'bone icon and editor visibility (official JSON reader does not expose them)',
    'binary header hash representation and nonessential metadata',
    'all attachment, constraint, event and timeline categories not exercised by the restricted comparison']};
if (jsonPath) {
  const jsonBytes = read(jsonPath);
  const json = jsonPath.endsWith(".skel")
    ? new r.SkeletonBinary(loader).readSkeletonData(Uint8Array.from(jsonBytes))
    : new r.SkeletonJson(loader).readSkeletonData(jsonBytes.toString());
  const reference = semantics(referenceData), actual = semantics(json);
  const statistics = {numeric:0,exact:0,maximumError:0};
  compare(reference,actual,'',statistics);
  Object.assign(result,{semanticCompared:true,candidateSha256:sha(jsonBytes),statistics,reference});
}
console.log(JSON.stringify(result));
