# Validation

## v0.4.3 — release validation and gameplay observations

Checked 2026-10-30. These results describe the v0.4.3 release build.

### Hellhound

- **PASS — user gameplay confirmation:** The user confirmed that a class 5 carcass was brought to the end and the normal `E` harvest screen opened. Do not read this as a full harvest or as a test of every class.
- **PASS — runtime capture:** Class 5 (45.019866 kg, 26 physical bodies, head body 21) completed 310 transport steps with 8,060 body updates. Class 6 (216.353 kg, 31 physical bodies, head body 24) completed an additional 260 steps with 8,060 body updates; the run ended at phase 0 with two releases recorded. Total body updates were 16,120 and head updates 570. Mass remained unchanged in both captures.
- **PASS — implementation boundaries:** Classes 2–9 use the original corpse ragdoll and a shared bounded XYZ delta for every valid mapped physical body, preserving each body's rotation, relative pose, velocity, and terrain contact while excluding other obstacle contacts only for that body. Head selection uses case-insensitive Head/Skull/Neck tokens after a separator and a valid body mapping; there are no species, prefix, or index hardcodes. Class 1 and normal E/reward behavior remain native. OFF, arrival, cancellation, identity change, and expiry release the temporary behavior.
- **NOT RUN:** Separate real-game arrival/cancel/OFF recovery while overlapping an obstacle, and a dedicated all-classes 2–9 gameplay sweep. The class 5 user observation and class 5/6 captures do not prove those cases.

### Silencer

- **PASS — user gameplay confirmation:** On an AR15 .300 rifle, the user confirmed bow firing/impact audio and original reload audio.
- **PASS — runtime capture:** Two shots recorded two firing replacements, two impact replacements, and suppression of two separate firing tails; API errors and native-audio fallbacks were both zero. The supported mapping covers 137 weapons: 70 rifles, 20 handguns, 28 shotguns, and 19 archery weapons. The three separate rifle/revolver/shotgun tail events are skipped only when Silencer is ON. Instance creation calls the original create once; playback with Silencer OFF or for non-target events calls the original start once.
- Reload, magazine, firing foley, pet breathing, ballistics, and metadata remain on their original paths. AI fire/impact calculations use the native longbow profile. Original source-event distance and parameter defaults remain, so exact audible-volume equivalence is not claimed.
- **NOT RUN:** Listening tests for other weapons and actual animal reactions. Ninja scent suppression's animal response also remains unverified.
- **UNRESOLVED — earlier compound-bow sound:** The unexpected compound-bow sound during later equipment/actions was reported before Silencer was introduced. Its cause is still unresolved; this fix does not claim to address it.

### Build and interface checks

- **PASS:** 139 unit tests, 24 source checks (16+5+3), and native preflights.
- **PASS:** Hellhound native CPU checks: 19 cases. Silencer and mode integration CPU checks: 18 cases. Both assembly bundles reassemble byte-for-byte.
- **PASS:** Korean and English hidden real-Tk controls at 490×550.
- **PASS — final frozen executable:** Self-test passed. All 14 embedded application modules semantically match the sources, eight data files match exactly, both assembly bundles reassemble byte-for-byte, and the other four native binaries are unchanged from HEAD. Combined with 139 unit tests, 24 self-checks, and Korean/English UI checks, the release build checks passed.
- Current executable: 13,625,676 bytes; SHA-256 `7899ffdebc6864c41e01885f2a07d335de5074aa12f4ed6c6b87f822a31ddb8d`.
- Hellhound binary SHA-256: `1ccc9b3a0a53eac8fe07228fec3723a5823ffb89600b5eb7386f9a29ceeb3322`.
- Silencer binary SHA-256: `a750219eae4be1744c2ed3aee8d94fd4ee46c4e862d740dbc5242cf9ea876a07`.

The six modes remain independently controlled and OFF by default. Startup update checks remain nonblocking and tokenless, with manual checks, stable SemVer comparison, and no automatic download or installation. See the prior v0.4.2 section below for the earlier failed transport attempt and its then-current findings; it is historical evidence, not the current behavior description.

## v0.4.2 local carry build — historical validation

Checked 2026-10-30. Historical v0.4.2 iteration only: this earlier build replaced Hellhound's immediate class 2–9 relocation with mouth-following ragdoll transport. The failures below were reproduced in this prior iteration and led to the current fix. Its gameplay limits and results must not be read as the current v0.4.3 state.

## v0.4.2 — previous failed implementation findings

Checked 2026-10-30 during the v0.4.2 work. At that time, v0.4.1 was the published stable release. These findings describe the earlier iteration only.

- **FAIL reproduced — previous transport code:** The active physical bone name `ragdoll_Head` was not recognized, rejecting a class 3 pickup. After correcting name recognition, class 3/6 registration and terrain detection succeeded, but carcasses lagged during transport and detached. The head setter's immediate result matches the requested position; this does not establish successful transport. Actual masses stayed approximately 63.85 kg and 249.35 kg.
- **Generic bone identification:** Validate anatomical head/skull/neck tokens after name separators and a current physical-body mapping, without hardcoded species, prefixes or indices. Structural parsing of 118 internal physics assets across 86 species is distinct from verifying all exterior carry skeletons in gameplay.
- **FAIL reproduced — missing gunshot tails:** Rifle firing and impact instances were created with the target bow GUIDs, and the firing instance successfully started, while the user still heard gunfire. Official FMOD path lookup identified a separate `weapon_tails/wpn_rifle_tail` event. Three rifle/revolver/shotgun tail events were missing from the previous substitution. Reloads, firing foley and dog breathing are separate events.
- **PASS — corrected rifle gameplay:** Two AR15 .300 shots recorded two firing replacements, two impact replacements and two suppressed rifle tails, with no API failures or native-audio fallbacks. The user confirmed bow firing/impact sounds and original weapon reload audio. Listening tests for other weapons and actual animal hearing remain unrun.
- **Validation limit:** NOSOUND metadata queries with missing plugins allowed establish event paths, parameters and unstarted-instance lifetime behavior, not audible success. Corrected transport, listening and E-harvest require separate gameplay results.

### v0.4.2 local carry build — historical validation

Checked 2026-10-30 during the v0.4.2 work. This earlier build replaced Hellhound's immediate class 2–9 relocation with mouth-following ragdoll transport. At that time, v0.4.1 was the published stable release. **Actual carcass transport and E-harvest with this build had not yet been tested.**

- **PASS — build and code checks:** 131 unit tests, 24 source self-checks and frozen EXE self-checks. All 14 embedded application modules and eight data files match the source. The other five native binaries are unchanged. The combined Hellhound ASM, including both new source includes, reassembles to the exact 24,576-byte runtime bundle.
- **PASS — native CPU boundaries:** 14 targeted x64 tests cover all classes 2–9, native class 1 behavior, pickup registration, one physical head-bone update, symmetric/self/terrain pair handling, native return-state preservation, partial installation rollback and release on OFF/cancel/identity changes. These are controlled CPU tests, not full engine physics.
- **PASS — installed data and live reads:** The supported EXE and 16 function preimages match. All 86 class 2–9 species in the inspected resource catalog have a Head/internal_skull bone name; this does not prove every active ragdoll layout. The actual Labrador has 114 animation bones, with Jaw hash `70B05DB4` present. The earlier fJaw assumption was rejected by the live data.
- **PASS — terrain identity:** The current world's typed terrain owner and its complete collision filter match 64 static terrain bodies. Other static object groups differ. The runtime predicate resolves the current owner and complete filter; it does not hardcode the observed world's group ID or guess terrain from a shape name.
- **PASS — real-game idle smoke:** With no fetch command and no active carried corpse, the new dog-tick path ran 330 more times and the native collision-filter path 41 more times over 12 seconds. OFF returned phase 0, the game remained alive and no errors were recorded. No screen, keyboard or mouse automation was used. This proves idle execution and expiry, not transport.
- **PASS — native contracts:** The head setter explicitly returns AL=1/0 for valid/invalid mapping. Contact invalidation includes a sleeping-island wake queue. The code waits for a real terrain pair and native carrying state; missing prerequisites produce a reason code and cleanup rather than player-front teleportation.
- **PASS — UI:** Updated Korean/English help and all master/individual controls were exercised in hidden real-Tk windows at 490×550.
- **NOT RUN — carcass gameplay:** Ground dragging, visible limp posture, arrival/cancellation/OFF with a corpse, E-harvest, and collision restoration while overlapping an obstacle still need a real class 2+ specimen. No dead animal was present in the observed scene. Zeroing velocities does not establish that obstacle-overlap release is stable.

EXE: 13,623,471 bytes, SHA-256 `9d6dcbe24262b42a81cc8da4f5a7433d76bb3fb0803aefa73c94c1eb79255abd`. Hellhound runtime bundle SHA-256: `9e78b23ef221603a58238d4ec4d7db4b97d9ab178c29017caba70c254c246d3e`.

## v0.4.1 release — previous validation

Checked 2026-10-29. v0.4.1 adds player scent suppression to the existing Ninja switch. The tested executable is the one included in the v0.4.1 release.

- **PASS — native scent calculation:** The installed `5ECD40` function bytes were executed in a controlled CPU fixture for four stances, three wind speeds, three angles and three distances: 108 conditions, each ON and OFF (216 executions). Skill, region and weather services use controlled neutral returns; this is not a complete running-game simulation.
- **PASS — native caller:** The actual caller's instructions skip adding a scent entry when the filtered score is zero. The seven original arguments, one original call, register/flag return state and upper 96 bits of XMM0 are preserved. Only the local player's scalar scent score changes; wildlife and pet receivers use the same rule. Other animals' scent keeps the native score.
- **PASS — existing code:** The original 8,192-byte hearing/vision bundle is unchanged. Scent has its own additional page and lease. No scent-eliminator stock/timer, wind, weapon or audio state is written.
- **PASS — Ninja tests:** All 24 targeted tests pass, including native scent/caller execution, local and foreign sources, existing two-page reuse, install/write/flush failures, transitions and all three leases expiring together on failure. The 12,288-byte bundle SHA-256 is `2315f1844652c438df8dbabf37d31603d58344c28df9cd334e90e7d6bbaa4f2d`.
- **PASS — released build:** All 128 unit tests, 24 source self-checks and frozen EXE self-checks pass. All 14 embedded application modules and eight bundled data files match the current source. The other five native binaries are unchanged, and rebuilding the Ninja ASM reproduces the bundle exactly. EXE: 13,616,577 bytes, SHA-256 `8cb3fe57dec069c78dc515a6aa01eb90d9567847ed3c0fbc3cc1f0763e0d0b4e`.
- **PASS — UI:** Hidden real-Tk Korean/English windows at 490×550 include the updated Ninja help. Individual buttons, master switches and the hotkey queue route remain operational without game input.
- **NOT RUN — gameplay:** Actual animal responses to the new scent filter have not been tested. Existing alertness and remembered detections are not cleared by enabling Ninja.
- **UNRESOLVED — reported audio behavior:** An unexpected compound-bow firing sound during later equipment/actions was reported before Silencer was added. The existing capture does not reproduce it; it lacks stop/release/parameter and output-audio data. No cause or fix is claimed in this release.

## v0.4.0 — previously released baseline

Checked 2026-10-29. [한국어 및 이전 배포 기록](VALIDATION.ko.md)

PASS applies only to the scope described below. **The new Silencer mode has not yet been heard or tested with animals in the running game.**

## Silencer

| Check | Result |
|---|---|
| Installed resource catalog | PASS — 137 real weapons: 70 rifles, 20 handguns, 28 shotguns, 19 bows/crossbows. Seven file-name/item-ID mismatches were corrected. |
| Audio mapping | PASS — 73 firing GUIDs and 12 impact GUIDs map to longbow fire/pure bow impacts; 13 existing target sounds pass unchanged. All 137 resource definitions and Fire/Fire_1/Fire_2/Fire_3/Fire_410/Fire_45c variants are covered. Seven multi-ammunition weapons contributed six additional firing GUIDs. |
| AI calculation | PASS — actual engine attenuation-function bytes, 137 weapons × 8 distances × fire/impact = 2,192 cases; full native return state matches the longbow calculation. OFF/unlisted sources keep their original result. |
| Ownership and boundaries | PASS — 50 AI binding/lease boundaries and 20 patch/restore fault cases, including current-tree reachability and a complete binding recheck after the clock call. |
| Native audio wrapper | PASS — assembled instructions, all 85 mappings and 13 identity cases; original create called once; ABI, metadata preservation, lookup/create errors, ownership and rollback checked. |
| ON/OFF integration | PASS — both Silencer halves disable together on error. An OFF-interval historical-error counter bug was reproduced and corrected without weakening first-shot failure detection. |
| Pre-patch game recording | PASS — compound-bow and AR15 .300 fire/impact GUIDs and successful original playback were recorded. This is baseline evidence, not playback of the new patch. |
| Shared bank | PASS — all 13 target GUIDs are in the same installed weapons bank as existing rifle and compound-bow sounds. Bank SHA-256: 2af95e1cea7a1eff4eb4a950a1d8c7de2cfb9ebe7be9e4346d8150ec074c01d8. |
| Standalone FMOD host | ENVIRONMENT FAILURE — creation, NOSOUND initialization and release succeeded; bank loading returned 54, FMOD_ERR_PLUGIN_MISSING. The game registers 16 DSPs implemented inside its EXE. The independent host lacks them; no dummy DSP or relaxed assertion was used. [FMOD error definition](https://www.fmod.com/docs/2.00/api/core-api-common.html#fmod_result). |
| Patched game playback/listening/animal behavior | NOT RUN. A CPU/resource PASS does not prove live playback or behavior. |

The native longbow AI profile uses a fire score of 2 through 10 m, falling to zero at 75 m; impact score is 1 through 25 m, falling to zero at 50 m. These are AI calculation distances. Ballistics, damage, ammunition, reload sounds and actual weapon records are preserved. Existing audio distance/parameter defaults remain those of the source event, so exact audible-volume equivalence is not claimed. One original longbow material entry points at a gun-impact sound; this mode consistently uses a bow impact instead.

## Controls and language

- PASS — all 64 combinations of six independent modes, master ON/OFF, partial-selection toggle, shutdown and state-transition recovery.
- PASS — Korean display-language LANGIDs choose Korean; other languages and query failures choose English. Region/locale does not override the Windows display-language choice.
- PASS — real hidden Tk widgets in Korean and English at 590×950 and 490×550; labels, dynamic status, master/individual buttons and hotkey dispatch checked. English output is checked for untranslated Korean text. No game input or screenshots were used.
- PASS — actual Windows Ctrl+Shift+F10 registration, owned-message delivery, unregister and re-register. Physical keyboard input was not tested. A registration conflict leaves the buttons available.

## Earlier gameplay evidence retained

- The user confirmed live white and blue animal outlines and occluded corpse outlines.
- Dog-outline and Ninja transition records are retained. Actual positive visual-score/ATV visual animal behavior remains outside the verified gameplay scope.
- Hellhound moved class-2 and class-3 original corpses; the user opened their normal E harvest screens. Classes 4–9 have code/CPU coverage only. It does not implement natural carrying poses or automatic harvest.
- The four earlier native binaries remain unchanged from v0.3.0. Cancelled vehicle-shooting experiments are excluded.

## Release verification and limits

PASS — final v0.4.0 build: 123 unit tests, 24 source self-checks and the frozen EXE self-checks. All 14 application modules, six native binaries, mapping data and notices match the sources; the earlier four native binaries are unchanged. The new native assembly sources were reassembled and matched byte for byte. No private paths, cancelled vehicle-shooting backend or test-only native dependencies were found in the application bundle. EXE size: 13,616,642 bytes; SHA-256: `9a07fa11c4696c5f2a2b1caf1529cfef9f3a9b5edce086bc68449ebceae01359`.

The release build runs the complete source test suite and self-checks, verifies native hashes/mapping data, and bundles no game banks, FMOD DLL, save data or raw gameplay logs. Release EXE/ZIP hashes are supplied in SHA256SUMS.txt; published assets are downloaded again for comparison. The package also includes English and Korean documentation and third-party notices.

Latest-stable update checks are tokenless, asynchronous and manually repeatable; drafts, prereleases and commits are excluded. Network errors do not block the app, and no automatic download/install occurs.

Unloaded animal/corpse models are not forced to stream. All species/maps, multiplayer, long sessions and another physical PC are unverified. External object-lifetime races are reduced rather than eliminated, and dynamic native SEH/unwind registration is not implemented. Full historical Korean records remain in VALIDATION.ko.md.
