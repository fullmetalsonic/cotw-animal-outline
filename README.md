# COTW Animal Outline

A portable Windows mod for **single-player** `theHunter: Call of the Wild`. It provides seven independent, optional modes for animal outlines, AI detection, dog retrieval, weapon audio, and ATV driving.

**Current stable release: v0.4.4.**

**Download v0.4.4:** [Latest stable release](https://github.com/fullmetalsonic/cotw-animal-outline/releases/latest) · **[Validation details](VALIDATION.md)** · [한국어 안내](README.ko.md)

## v0.4.4

Mad Max adds a 2× ATV maximum-speed limit and 2× wheel drive force while retaining the existing five gears and engine RPM range. It also assists tire grip and halves base aerodynamic drag while retaining overspeed resistance. Before the drag change, logs recorded 77.8 km/h and first-to-second shifts; the user confirmed less wheelspin and sideways sliding. **Post-drag logs reached 89.5 km/h and third gear. Actual 120 km/h and fourth/fifth-gear gameplay remain PENDING USER TEST**. The pet-list read also handles lists exceeding the 1 MiB read limit.

The preserved v0.4.3 baseline fixes Hellhound transport for classes 2–9 and replaces the three separate rifle, revolver, and shotgun firing-tail events when Silencer is ON. The user confirmed that a class 5 carcass was brought to the end and its normal `E` harvest screen opened. A separate class 6 runtime capture completed 260 transport steps. These observations do not establish gameplay success for every class or obstacle condition. Ninja scent suppression, Korean/English UI, master switches, and the global shortcut remain available.

### Modes

Each mode has its own switch and is OFF by default. Use **ALL ON** or **ALL OFF** at the top of the window to change all seven together (7/7 ON, 0/7 OFF). `Ctrl+Shift+F10` toggles all seven: if any mode is ON, it turns all OFF; if all are OFF, it turns all ON. The shortcut is registered globally while the app is running. There is no F1 hotkey.

- **Live animal outline:** Choose white or blue. Applies to loaded animals, including animals loaded later. It does not spot animals automatically or reveal animal information.
- **Carcass outline:** Independently highlights loaded carcasses in a chosen color (default orange, `#FF5900`). It does not force distant, unloaded carcasses to appear.
- **Ninja:** Suppresses AI hearing of player/current ATV movement, local visual detection, and player scent detection. OFF restores the native calculations. Player audio, HUD, scent-eliminator supplies/timers, wind, and other animals' scent remain unchanged. Gunshot events use the native calculation unless **Silencer** is enabled separately. The new scent filter has not been verified with animals in the running game.
- **Keep Dog Outline:** Preserves the game's native pet outline, color, and occlusion behavior while other animal clues are hidden. **Ninja** still applies to the pet.
- **Hellhound:** Requires a dog with the Retriever job. Class 1 keeps native behavior. Classes 2–9 follow the dog's mouth as the dog returns, using the dead ragdoll body without added carrying animations. During transport, terrain contact is retained while other contacts are excluded for that carcass only. Arrival, cancellation and OFF release the carcass for normal `E` harvest. Actual class, mass, trophy and reward data are preserved, with no automatic harvesting. The user confirmed class 5 transport to the end and opening the normal `E` harvest screen. The earlier class 2/3 instant-relocation records are historical and do not validate this carry behavior.
- **Silencer:** Uses longbow firing audio and bow impact audio for all 137 supported weapons (70 rifles, 20 handguns, 28 shotguns, and 19 archery weapons), and suppresses the three separate rifle/revolver/shotgun tail events. AI fire/impact calculations use the native longbow profile: fire score 2 through 10 m falls to zero at 75 m; impact score 1 through 25 m falls to zero at 50 m. It does not change ballistics, damage, ammunition, or reload sounds. **The user confirmed bow firing/impact audio and original reload audio with an AR15 .300 rifle.** Other weapons and actual animal hearing remain untested in gameplay. Source-event distance/parameter defaults remain; exact audible-volume equivalence is not claimed. See [VALIDATION.md](VALIDATION.md).

- **Mad Max:** Doubles the current local driver's ATV maximum-speed limit and wheel drive force, with balanced grip assistance on all four tires and half base aerodynamic drag. Overspeed resistance is retained. The five native gears and engine RPM range are retained. ON waits while you are not driving an ATV; OFF restores native calculations. A stock 60 km/h limit becomes 120 km/h; the user confirmed reduced wheelspin and sideways sliding, while post-drag logs reached 89.5 km/h and third gear; actual 120 km/h remains unverified. It does not promise exactly half the slip on every surface.

Closing the app stops further updates and restores owned native hooks. Silencer OFF restores original sounds for newly started events. The app can run before or after the game. If the pet or Retriever mode should remain active while you wait for a dog, you can leave that mode ON.

## Known issues

- Hellhound can intermittently drop a large carried carcass before reaching the player. The cause is unconfirmed and this release does not fix it.
- Weapons or other held items can intermittently remain invisible after dismounting an ATV. The cause is unconfirmed and this release does not fix it.
- An unexpected compound-bow sound can occur during later actions. This predates Silencer; the cause is unconfirmed and this release does not fix it.

## Requirements and scope

- Windows 10 or 11, x64; Steam build **26051119**, game code **3366163**.
- Supported game executable SHA-256: `33c8306e52c5541a5b87e4af576f4149f3da0c23b36775372ec6c41adbab73ca`.
- Single-player only. Other game builds and executables are unsupported.
- Release checks passed: 165 unit tests, 24 source self-checks, 21 Mad Max native tests and 13 pet-list boundary tests. Gameplay coverage and remaining limits are detailed in [VALIDATION.md](VALIDATION.md).
- No Python installation is needed. The app finds the install directory from the running game process, including installations on other drives and paths containing spaces or Korean characters.
- The app does not edit game files, saves, or Steam launch options. It applies temporary hooks to the running game's memory.
- The existing external-object lifetime race is not fully eliminated, and dynamic SEH/unwind registration is not implemented.

## Run

1. Download the [v0.4.4 release](https://github.com/fullmetalsonic/cotw-animal-outline/releases/tag/v0.4.4) and extract the ZIP to a folder of your choice.
2. When replacing an existing copy, close the old program first. Then run `COTWAnimalOutline.exe` from the extracted package.
3. Start the game and enter a single-player reserve, if you have not already.
4. All seven modes start OFF. Turn on only the modes you want. Hellhound requires a Retriever dog; enable its switch separately.

The interface uses Korean when the Windows display language is Korean and English for other Windows display languages. This is independent of the Windows region setting.

## Updates

The app checks for the latest stable GitHub Release at startup without blocking use. You can also select **Check for updates**. It compares stable semantic versions and ignores pre-releases, drafts, and commits. It uses no token, does not download or install updates automatically, and network errors do not prevent the mod from running.

## Build from source

Python 3.12 x64 is required to build from source; the packaged app itself needs no Python installation. `build.ps1` uses pinned dependencies and builds with Tkinter.

```powershell
.\build.ps1
.build-venv\Scripts\python.exe -m unittest discover -v
```

Third-party license notices are included with the release.
