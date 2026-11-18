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
| Walking on any map (all 249 maps)        | That map's theme, looked up in `data/map_music.json`. The Safari Zone uses `28 Evolution.mp3`, the same song in Gen 1. |
| A trainer spots you                      | That trainer's "A Trainer Appears" theme (boy, girl or bad guy), until the battle starts |
| Wild battle                              | `12 Battle (Wild Pokemon).mp3`, from the start of the battle transition animation |
| Trainer battle                           | `09 Battle (Trainer).mp3`, from the start of the transition    |
| Gym leader or Elite Four battle          | `20 Battle (Gym Leader).mp3`, from the start of the transition |
| Champion battle                          | `45 Final Battle (Rival).mp3`, from the start of the transition |
| Victory fanfare (wild / trainer / gym)   | Matching `Victory (...)` track, played once                   |
| Back to the overworld                    | The current map's theme again                                 |
| Healing at a Pokémon Center              | `56 Pokemon Recovery.mp3` once (zophar only; used with any source), then the map's theme |
| Jigglypuff sings (Pewter Pokémon Center) | `57 Jigglypuff's Song.mp3` once (zophar only), then the map's theme |
| Riding the bicycle / surfing             | `31 Cycling.mp3` / `41 The Sea.mp3`, across maps, until you get off |
| Professor Oak / your rival appears       | `06 Professor Oak.mp3` / `08 A Rival Appears.mp3`, until the game changes song |
| The museum guide                         | `18 Guide.mp3`                                                |
| Jessie & James appear                    | `25 Theme of Jessie and James.mp3`, until the battle starts   |
| Pikachu surfing (Summer Beach House)     | `39 Pikachu's Beach.mp3`                                      |
| A Pokémon evolves                        | `28 Evolution.mp3`, then the map's theme                      |
| Intro movie / title screen               | `02 Opening Movie.mp3` / `04 Title Screen.mp3`                |
| Hall of Fame / credits                   | `46 Hall of Fame.mp3` / `47 Ending Theme.mp3`                 |
| Item, key item or hidden item received   | `60 Item Fanfare.mp3` / `63 Key Item Fanfare.mp3` / `61 Hidden Item Fanfare.mp3` (also when an evolution ends) |
| Level up / Pokémon caught                | `58 Level Up Fanfare.mp3` / `59 Pokemon Caught Fanfare.mp3`   |
| Oak rates your Pokédex                   | One of the fanfares, or `62 Pokedex Rating Fanfare.mp3`       |
| Loading a savestate (F1–F9, rewind)      | Switches to the music of the place in the loaded state        |
| mGBA paused, in the background, or closed | Music pauses within ~0.5 s and resumes where it stopped       |

These follow the song the game itself starts, so they begin and end when the game's own
music would. Track switches fade out and in over about half a second instead of cutting.
Fanfares (zophar only; used with any source) pause the music, as the game
does, and it resumes where it stopped when the game's fanfare ends.

## Requirements

- Linux or macOS. mpv IPC uses a Unix socket.
- Python 3.10 or newer. Only the standard library is used.
- `mpv` on `PATH` (`sudo apt install mpv`).
- mGBA 0.10 or newer with Lua scripting (*Tools → Scripting…*).
- For the music to pause when mGBA is in the background, enable mGBA's option to pause
  when the window is inactive (`pauseOnFocusLost=1` in `~/.config/mgba/config.ini`). The
  controller pauses the music whenever the game stops running frames.
- The soundtrack MP3s, which are not included. Each of these folders works as a music
  source (see [Choose the music source](#choose-the-music-source)):
  - `music/zophar/`: the files of the zophar rip "Pokemon Yellow (MP3)"
  - `music/ost/`: the files of "Part I - Stereo" from "Pokémon Yellow Soundtrack
    MP3". Its "Part II - Mono" isn't needed: each mono file is a downmix of the stereo one.
- After copying the MP3s in with their original names, rename them once to the shared
  names the code uses:

  ```sh
  python3 tools/normalize_music.py           # dry run: shows every rename
  python3 tools/normalize_music.py --apply   # renames (undo with --revert)
  ```

  Some files are never played as music: the soundtrack's 01, 03 and 48–55, and zophar's
  unnamed jingles (`46.mp3`, `50.mp3`, `57.mp3`–`98.mp3`). You can delete them; the tool
  reports them as "not needed".

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
   [MUSIC] Game started song 0xf0 (MUSIC_WILD_BATTLE)
   [BATTLE] Battle music: MUSIC_WILD_BATTLE
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
| `zophar` (default) | `music/zophar/` | 180 s renders, 44.1 kHz. Fades out every 3 minutes when looped. |
| `ost` | `music/ost/` | Stereo, as the game sounds in mGBA. 48 kHz. Tracks are 1–1.5 min, so the fade comes sooner. |

Change `"default"` in that file, or pick a source for one run:

```sh
cd python
python3 controller.py --source ost
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
which sources lack it otherwise. It also prints which themes still have no file (none today).

### Change battle or victory tracks

These are hard-coded in `python/controller.py`: `SONGS` (battle, victory and event songs
by song id), `FANFARES` and the `BATTLE_TRACKS` fallback. Entries are canonical track
names, resolved in the selected source.

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
| Music fades out and restarts every ~3 minutes (1–1.5 min with the `ost` source) | Known: every MP3 has a fade-out at the end and is looped whole. |
| Viridian/Pewter music on the title screen after a soft reset there | Known: `wCurMap` keeps the old map, and the title song shares its id with that music. |

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
