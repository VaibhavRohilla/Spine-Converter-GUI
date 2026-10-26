# B4 developer viewer

Scope: English-language engineering harness for local Spine bundles. The user's B4
brief is authoritative: functional controls and evidence, no B5 desktop design system.
The characteristic visual is the actual skeleton against a transparency checkerboard.
Native controls deliberately keep platform keyboard and selection behavior.

`viewer/viewer.css` owns runtime tokens (Model B): surface `#20242a`, text `#eeeeee`,
border `#596270`, warning `#ffbd90`, focus `#8bc4ff`. System UI type for controls;
monospace for diagnostic JSON. Canvas and controls keep stable bounds. No external
fonts, animation decoration, marketing content, or network design dependencies.

Canonical owners: `SpineViewer` owns playback, camera, render lifecycle and captures;
`protocol.ts` owns frontend validation; Python ViewerService owns asset selection;
`frame.ts` only binds native controls. The pair host embeds two isolated documents,
uses a shared camera for comparison, and never treats a difference image as approval.
Disabled controls reflect load/failure/disposed states. Errors remain visible and
separate from captured images. Playback starts only by explicit action. Arrow keys,
plus/minus and zero provide camera alternatives to drag and wheel. Focus is visible.
The main frame and comparison host share the same stylesheet and native primitives.

Verification: Playwright real WebGL pixels, error and cancellation states, keyboard
camera operation, narrow viewport, runtime isolation, captures, and comparison tests.
B5 may replace this harness's visual design while retaining component and protocol APIs.
