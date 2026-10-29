# Validation — v0.4.0

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
