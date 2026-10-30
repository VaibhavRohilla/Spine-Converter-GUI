// Read-only external reference check. No runtime code is bundled by FNX.
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const [root, input, expectedFile] = process.argv.slice(2);
const pkg = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8'));
if (pkg.name !== '@esotericsoftware/spine-core' || pkg.version !== '4.2.43') {
  throw new Error('Requires exact official @esotericsoftware/spine-core@4.2.43');
}
const {SkeletonBinary} = await import(pathToFileURL(resolve(root, pkg.main)));
const data = new SkeletonBinary(null).readSkeletonData(new Uint8Array(readFileSync(input)));
const bones = data.bones.map(b => ({name:b.name, parent:b.parent?.name ?? null,
  rotation:b.rotation,x:b.x,y:b.y,scaleX:b.scaleX,scaleY:b.scaleY,
  shearX:b.shearX,shearY:b.shearY,length:b.length,inherit:b.inherit,skin:b.skinRequired}));
if (expectedFile) {
  const expected = JSON.parse(readFileSync(expectedFile, 'utf8'));
  assert.equal(data.version, expected.version);
  assert.deepEqual(bones, expected.bones);
  assert.equal(data.slots.length, expected.slots);
  assert.equal(data.skins.length, expected.skins);
  assert.equal(data.animations.length, expected.animations);
}
console.log(JSON.stringify({reference:pkg.name+'@'+pkg.version,version:data.version,
  bones,slots:data.slots.length,skins:data.skins.length,animations:data.animations.length}));
