import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [packageRoot, skeletonPath, atlasPath] = process.argv.slice(2);
const pkg = JSON.parse(await readFile(resolve(packageRoot, "package.json"), "utf8"));
if (pkg.name !== "@esotericsoftware/spine-core" || pkg.version !== "4.2.43") {
  throw new Error(`Expected official @esotericsoftware/spine-core 4.2.43, got ${pkg.name}@${pkg.version}`);
}
const spine = await import(pathToFileURL(resolve(packageRoot, pkg.main)).href);
const skeletonDocument = JSON.parse(await readFile(skeletonPath, "utf8"));
if (skeletonDocument.skeleton?.spine !== "4.2.43") {
  throw new Error(`Expected Spine 4.2.43 skeleton data, got ${skeletonDocument.skeleton?.spine}`);
}
const atlasText = await readFile(atlasPath, "utf8");
const atlas = new spine.TextureAtlas(atlasText);
for (const page of atlas.pages) {
  const texturePath = resolve(dirname(atlasPath), page.name);
  await readFile(texturePath);
}
const attachmentLoader = new spine.AtlasAttachmentLoader(atlas);
const skeletonData = new spine.SkeletonJson(attachmentLoader).readSkeletonData(skeletonDocument);
const skeleton = new spine.Skeleton(skeletonData);
skeleton.setToSetupPose();
skeleton.updateWorldTransform(spine.Physics.update);
const state = new spine.AnimationState(new spine.AnimationStateData(skeletonData));
let evaluatedSamples = 0;
for (const animation of skeletonData.animations) {
  state.setAnimation(0, animation.name, false);
  const duration = Math.max(0, animation.duration);
  const samples = [...new Set([0, duration * 0.25, duration * 0.5, duration])];
  let prior = 0;
  for (const time of samples) {
    state.update(time - prior);
    state.apply(skeleton);
    skeleton.updateWorldTransform(spine.Physics.update);
    for (const bone of skeleton.bones) {
      for (const value of [bone.worldX, bone.worldY, bone.a, bone.b, bone.c, bone.d]) {
        if (!Number.isFinite(value)) throw new Error(`Non-finite world transform in ${animation.name}`);
      }
    }
    evaluatedSamples++;
    prior = time;
  }
}
console.log(JSON.stringify({
  status: "animation_state_evaluated",
  runtime: `${pkg.name}@${pkg.version}`,
  skeletonVersion: skeletonData.version,
  bones: skeletonData.bones.length,
  slots: skeletonData.slots.length,
  skins: skeletonData.skins.length,
  animations: skeletonData.animations.map((animation) => animation.name),
  atlasPages: atlas.pages.map((page) => page.name),
  atlasRegions: atlas.regions.length,
  evaluatedSamples,
  parsing: "passed",
  animationStateEvaluation: "passed",
  visualEquivalence: "not_assessed"
}));
