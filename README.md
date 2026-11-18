# Pokemon Adaptive OST

Plays the Pokémon Yellow soundtrack from MP3 files, in sync with the game running in
[mGBA](https://mgba.io/). A Lua script inside mGBA watches the game's RAM. A Python
controller turns those observations into music changes, and `mpv` plays the tracks.

Built for and verified against the Spanish ROM
**Pokémon Edición Amarilla: Edición Especial Pikachu (Spain)**
(header title `POKEMON YELAPSS`, SHA-1 `1dc242039218fba50928d1afb66b70565b6b9daf`).
Other languages use different RAM addresses. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#ram-addresses).

## What it does today

| Situation in game                        | Music played                                                  |
| ---------------------------------------- | ------------------------------------------------------------- |
| Walking on any map (240 of 249 maps)     | That map's theme, looked up in `data/map_music.json`          |
| Safari Zone maps (9)                     | `music/locations/default.wav`, a synthesized placeholder      |
| Wild battle                              | `12 Battle (Wild Pokemon).mp3`                                |
| Any trainer battle (gym leaders included) | `09 Battle (Trainer).mp3`                                     |
| Victory fanfare (wild / trainer / gym)   | Matching `Victory (...)` track, played once                   |
| Back to the overworld                    | The current map's theme again                                 |
| Loading a savestate (F1–F9, rewind)      | Switches to the music of the place in the loaded state        |

Not handled yet: gym leader and champion battle themes, trainer "eyes meet" music, rival
and Oak cutscenes, bicycle, surfing, Jessie & James, the heal jingle, and the title screen.

## Requirements

- Linux or macOS. mpv IPC uses a Unix socket.
- Python 3.10 or newer. Only the standard library is used.
- `mpv` on `PATH` (`sudo apt install mpv`).
- mGBA 0.10 or newer with Lua scripting (*Tools → Scripting…*).
- The soundtrack MP3s, which are not included. Any of these folders works as a music
  source (see [Choose the music source](#choose-the-music-source)):
  - `music/Pokemon Yellow (MP3).zophar/` (zophar rip)
  - `music/Pokémon Yellow Soundtrack MP3/Part I - Stereo/` and `…/Part II - Mono/`
- After copying the MP3s in with their original names, rename them once to the shared
  names the code uses:

  ```sh
  python3 tools/normalize_music.py           # dry run: shows every rename
  python3 tools/normalize_music.py --apply   # renames (undo with --revert)
  ```

## Quick start

1. **Start the controller first.** The Lua script connects only once, when it loads.

   ```sh
   cd python
   python3 controller.py
   ```

   This starts `mpv` in the background and listens on `127.0.0.1:8765`.

2. **Open the ROM in mGBA** and load your save.

3. **Mute the emulator's own audio** (*Audio/Video → Mute*). Otherwise you hear both
   soundtracks. This also mutes sound effects and cries.

4. **Load the script:** *Tools → Scripting… → File → Load script* →
   `lua/pokemon_yellow.lua`. The scripting console should show
   `[OST] Connected to Python controller`.

5. Play. The controller terminal logs each event:

   ```text
   [MAP] Pallet Town [ID: 0] [MUSIC: MUSIC_PALLET_TOWN]
   [MPV] Playing: 05 Pallet Town.mp3
   [BATTLE] WILD_BATTLE [RESULT: 0]
   ```

To stop, press `Ctrl+C` in the controller terminal. This also shuts down mpv.

If you restart the controller, reload the Lua script in mGBA. It does not reconnect on its own.

## Repository layout

```text
lua/
  pokemon_yellow.lua        Main mGBA script: reads RAM each frame, sends JSON events over TCP
  diagnostic.lua            One-shot dump of a few RAM variables, for finding addresses
python/
  controller.py             TCP server + AdaptiveOST state machine (entry point)
  music_player.py           MusicPlayer: spawns mpv and talks to it over JSON IPC
  map_registry.py           map id → readable name, parsed from data/map_constants.asm
  generate_map_registry.py  Builds data/map_music.json (run after editing themes)
  music_sources.py          Music source config + TrackResolver (canonical name → file)
  generate_tracks.py        Synthesizes the placeholder .wav tracks
  test_music_player.py      Manual smoke test: plays a generated melody through mpv
  mpv_test.py               Manual check against an mpv started by hand
config/
  music_themes.json         Game music constant (MUSIC_*) → canonical track name
  music_sources.json        Music source name → folder, and the default source
data/                       pokeyellow files: see Credits
  map_constants.asm         From the pokeyellow disassembly: map symbols and ids
  songs.asm                 From pokeyellow: MapSongBanks, map → MUSIC_* constant
  music_constants.asm       From pokeyellow: list of music constants (reference only)
  map_music.json            Generated: map id → name, symbol, music id, track name
music/                      Audio (not tracked; see Requirements)
docs/
  ARCHITECTURE.md           How the pieces fit together, the protocol, RAM addresses
  ROM_NOTES.md              Verified RAM addresses, music id/bank table, audio measurements
tools/
  rom_inspect.py            Static ROM checks: header, RAM reference counts, map song table
  normalize_music.py        Renames the soundtrack sets to the shared track names
```

## Common tasks

### Choose the music source

Every source folder uses the same file names (for example `05 Pallet Town.mp3`), so a
source is only a folder. The sources and the default are in `config/music_sources.json`:

| Source | Folder | Notes |
| --- | --- | --- |
| `zophar` (default) | `music/Pokemon Yellow (MP3).zophar/` | 180 s renders, 44.1 kHz. Fades out every 3 minutes when looped. |
| `ost_stereo` | `music/Pokémon Yellow Soundtrack MP3/Part I - Stereo/` | Stereo, as the game sounds in mGBA. 48 kHz. Tracks are 1–1.5 min, so the fade comes sooner. |
| `ost_mono` | `music/Pokémon Yellow Soundtrack MP3/Part II - Mono/` | Same recordings mixed to mono (original Game Boy speaker). |

Change `"default"` in that file, or pick a source for one run:

```sh
cd python
python3 controller.py --source ost_stereo
```

The controller logs `[TRACK] Music source: …` at start. If a song is missing from the
selected source, it plays the same name from another source and logs it.

### Change which file a theme uses

Edit `config/music_themes.json`. Keys are the `MUSIC_*` constants from
`data/music_constants.asm`. Values are canonical track names, the same in every source
(see the table in `tools/normalize_music.py`). Then regenerate the registry:

```sh
cd python
python3 generate_map_registry.py
```

The generator stops with an error if a configured name exists in no source, and prints
which sources lack it otherwise. It also prints which themes still have no file. Today that is only `MUSIC_SAFARI_ZONE`.

### Change battle or victory tracks

These are hard-coded in `python/controller.py` (`BATTLE_TRACKS`, `VICTORY_TRACKS`,
`DEFAULT_LOCATION_TRACK`). Battle and victory entries are canonical track names, resolved
in the selected source.

### Check that mpv works

```sh
cd python
python3 test_music_player.py   # plays a 3.5 s generated melody, then exits
```

### Find RAM addresses for another ROM

Load `lua/diagnostic.lua` in mGBA at a known moment (for example during a wild battle)
and compare the printed values with what you expect. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#ram-addresses).

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `[OST] Connection failed: …` in mGBA | The controller isn't running. Start it, then reload the script. |
| `[OST] mGBA socket API unavailable` | Your mGBA build lacks Lua sockets. Use mGBA 0.10 or newer. |
| `RuntimeError: MPV IPC socket was not created` | mpv is missing or failed to start. Run `mpv --version`. |
| `OSError: [Errno 98] Address already in use` | Another controller is still running on port 8765. |
| Music fades out and restarts every ~3 minutes (1–1.5 min with `ost_*` sources) | Known: every MP3 has a fade-out at the end and is looped whole. |
| Pallet Town music on the title screen | Known: the script trusts `wCurMap` before a save is loaded. |

## Credits

The map and music data in `data/` comes from [pokeyellow](https://github.com/pret/pokeyellow),
the Pokémon Yellow disassembly by the [pret](https://github.com/pret) team:

| File here | Upstream file |
| --- | --- |
| `data/map_constants.asm` | `constants/map_constants.asm` |
| `data/songs.asm` | `data/maps/songs.asm` |
| `data/music_constants.asm` | `constants/music_constants.asm` |

These files describe the English release. The map → song table (`MapSongBanks`) they
describe is byte-identical in the Spanish ROM, which is why this project can use them.
Thanks to everyone who contributed to pret's disassemblies.

Pokémon is © Nintendo, Creatures Inc. and GAME FREAK inc. This project ships no ROM or
game audio.
