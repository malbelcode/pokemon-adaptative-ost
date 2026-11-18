# Architecture

## Overview

```text
 ┌──────────────── mGBA ────────────────┐   JSON lines    ┌──────── Python ────────┐   JSON IPC    ┌──── mpv ────┐
 │ ROM ── RAM ──► lua/pokemon_yellow.lua│ ──────────────► │ controller.py          │ ────────────► │ idle player │
 │   (polled every frame)               │  TCP :8765      │  AdaptiveOST           │ ◄──────────── │ (no video)  │
 └──────────────────────────────────────┘                 │  music_player.py       │  end-file     └──────┬──────┘
                                                          └──────────▲─────────────┘                      │
                                                                     │ data/map_music.json                │ reads
   data/map_constants.asm ─┐                                         │                                    ▼
   data/songs.asm ─────────┼──► python/generate_map_registry.py ─────┘                          music/**/*.mp3
   config/music_themes.json┘        (offline, run on demand)
```

Three processes run during play:

1. **mGBA + `lua/pokemon_yellow.lua`.** It reads a few WRAM bytes on every frame callback
   and sends a JSON event when one of them changes, plus a `HEARTBEAT` every 10 frames.
   It holds no music logic.
2. **`python/controller.py`.** A blocking TCP server that accepts one mGBA connection at a
   time and feeds each line to `AdaptiveOST.handle_event`. `AdaptiveOST` decides what
   should play. `read_events` reads with a 0.1 s timeout so it can pause the music when
   messages stop.
3. **`mpv`.** Started by `MusicPlayer.start()` with `--idle=yes --no-video
   --input-ipc-server=/tmp/pokemon-adaptive-ost-mpv.sock`. It is controlled with
   `loadfile … replace`, `set_property loop-file` and `set_property pause`.
   `send_command` holds a lock, because the mpv event thread also sends commands.

## Lua → Python protocol

Newline-delimited JSON over TCP to `127.0.0.1:8765`. Each line is one event:

| `event` | Sent when | Fields |
| --- | --- | --- |
| `MAP_CHANGED` | At script start, and whenever `wCurMap` changes | `map_id` (int, 0–248) |
| `BATTLE_CHANGED` | At script start, and whenever `wIsInBattle` changes | `state`, `value`, `map_id`, `battle_result` |
| `VICTORY_STARTED` | Music channels 0–2 all switch to a victory song id | `victory_type` |
| `TRAINER_SPOTTED` | The byte at 0xCD3D changes to 255 (a trainer has seen the player) | none |
| `HEARTBEAT` | Every 10 frames (~0.17 s at full speed). Stops while mGBA is paused. | none |
| `STATE_LOADED` | `emu:currentFrame()` does not advance by exactly 1 since the last frame (savestate load, rewind or reset; mGBA restores the frame counter from the state). That frame's other checks are skipped and all `previous` values are re-read. | `map_id`, `state`, `value`, `battle_result` |
| `MUSIC_CHANGED` | Defined in Lua (`sendMusicChanged`) but never sent | `music_id` |

`state` is derived from `wIsInBattle`:

| `value` | `state` |
| --- | --- |
| 0 | `OVERWORLD` |
| 1 | `WILD_BATTLE` |
| 2 | `TRAINER_BATTLE` |
| 255 | `LOST_BATTLE` |
| other | `UNKNOWN` |

`victory_type` is derived from the shared channel sound id:

| id | Song (`music_constants.asm`) | `victory_type` |
| --- | --- | --- |
| 246 (0xF6) | `MUSIC_DEFEATED_TRAINER` | `TRAINER_BATTLE` |
| 249 (0xF9) | `MUSIC_DEFEATED_WILD_MON` | `WILD_BATTLE` |
| 252 (0xFC) | `MUSIC_DEFEATED_GYM_LEADER` | `GYM_LEADER_BATTLE` |

Example session:

```json
{"event":"MAP_CHANGED","map_id":12}
{"event":"BATTLE_CHANGED","state":"OVERWORLD","value":0,"map_id":12,"battle_result":0}
{"event":"BATTLE_CHANGED","state":"WILD_BATTLE","value":1,"map_id":12,"battle_result":0}
{"event":"VICTORY_STARTED","victory_type":"WILD_BATTLE"}
{"event":"BATTLE_CHANGED","state":"OVERWORLD","value":0,"map_id":12,"battle_result":0}
```

## Controller state machine (`AdaptiveOST`)

State: `current_state` (last `BATTLE_CHANGED.state`), `current_map`, `current_track`.

| Event | Action |
| --- | --- |
| `MAP_CHANGED` | Store `current_map`. If `current_state` is `None` or `OVERWORLD`, play the map's track. |
| `BATTLE_CHANGED` with `WILD_BATTLE` / `TRAINER_BATTLE` | Play `BATTLE_TRACKS[state]`, looped. |
| `BATTLE_CHANGED` with `OVERWORLD` | Play the current map's track. This cuts off a victory fanfare that is still playing, as the game does. |
| `BATTLE_CHANGED` with `LOST_BATTLE` / `UNKNOWN` | Only stores the state. The current track keeps playing. |
| `VICTORY_STARTED` | Play `VICTORY_TRACKS[type]` once (`loop-file=no`). |
| `TRAINER_SPOTTED` | Play `BATTLE_TRACKS["TRAINER_BATTLE"]`, looped, and log `[TRAINER]`. `current_state` is not changed. |
| `STATE_LOADED` | Set `current_map` and `current_state`, clear `victory_playing`, log `[STATE]`. Play the battle track for `WILD_BATTLE` / `TRAINER_BATTLE`, or the map's track otherwise. |
| `HEARTBEAT` | Ignored by `handle_event`. Like every message, it resumes paused music. |
| No message for 0.5 s (`HEARTBEAT_TIMEOUT`) | Pause mpv and log `[PAUSE]`. mGBA runs no frames while paused, including when its "pause when inactive" option pauses it in the background. The next message resumes playback at the same position. |
| mGBA disconnects | Pause mpv. The next connection's first message resumes it. |
| mpv `end-file` with `reason: eof` | If `OVERWORLD`, play the map's track. This callback runs on the mpv event thread. |

`play_track` skips the request when the track is already the current one, so repeated
events don't restart the song.

Map track lookup: `data/map_music.json[str(map_id)].track` is a canonical track name, which
`TrackResolver` (`python/music_sources.py`) turns into a file in the selected source.
If it is `null`, or the name is in no source, `music/locations/default.wav` plays instead.

## Music sources

`config/music_sources.json` maps a source name to a folder and names the default.
`controller.py --source NAME` overrides the default for one run. All folders use the
same canonical file names (`NN Title.mp3`), set by `tools/normalize_music.py`, so switching
a source changes only the folder. `TrackResolver.resolve(name)` looks in the selected
source first, then in the others in config order, and logs `[TRACK]` when it falls back
or finds nothing. Results are cached per name.

Numbers 01–55 follow the official soundtrack's order. 56–63 exist only in the zophar set
(heal jingle, Jigglypuff, fanfares). Zophar's 44 unnamed 1–4 s jingles are in its
`unidentified/` subfolder.

## Map → music registry

`data/map_music.json` is generated. Don't edit it by hand.

```text
map_constants.asm  "map_const PALLET_TOWN, 10, 9 ; $00"   → id 0  ↔ PALLET_TOWN
songs.asm          "db MUSIC_PALLET_TOWN, … ; PALLET_TOWN" → PALLET_TOWN ↔ MUSIC_PALLET_TOWN
music_themes.json  "MUSIC_PALLET_TOWN": "05 Pallet Town.mp3"
                    ⇒ "0": {"name": "Pallet Town", "symbol": "PALLET_TOWN",
                            "music_id": "MUSIC_PALLET_TOWN",
                            "track": "05 Pallet Town.mp3"}
```

The `.asm` files come from the [pokeyellow](https://github.com/pret/pokeyellow)
disassembly. The map → music table they describe (`MapSongBanks`) is byte-identical in the
Spanish ROM (found at ROM offset `0xFC000`), so the mapping is valid for this cartridge.

## RAM addresses

The Lua script reads these from the Spanish ROM:

| Symbol | Address | Status in the Spanish ROM |
| --- | --- | --- |
| `wCurMap` | `0xD362` | Verified: 85 direct references in code |
| `wIsInBattle` | `0xD05B` | Verified: 99 direct references |
| `wChannelSoundIDs` | `0xC026` (+0..+2) | Verified: audio WRAM, same as English |
| `wBattleResult` | `0xCF0B` | **Suspect**: 0 references. This is likely the English address. Only logged. |
| `wCurOpponent` | `0xD05D` | In `diagnostic.lua` only |
| `wBattleType` | `0xD05E` | In `diagnostic.lua` only |
| trainer sprite offset | `0xCD3D` | Used for `TRAINER_SPOTTED` (255 = spotted). 204 references: a shared scratch byte, so other values may also appear there. |

The overworld variables (D-range WRAM) sit 4–5 bytes higher than in the English Yellow
build. Audio-engine variables (`0xC0xx`) are unchanged. When porting to another language,
re-derive the D-range addresses with `lua/diagnostic.lua`.

Music ids are **only unique within an audio bank**. For example, `0xCD` is
`MUSIC_CINNABAR` in bank `0x02` and `MUSIC_OAKS_LAB` in bank `0x1F`. Any logic keyed on
raw song ids must also know the bank.

## Audio assets

| Path | Used by | Notes |
| --- | --- | --- |
| `music/Pokemon Yellow (MP3).zophar/` | source `zophar` (default) | 98 files, 313 MB. 54 canonical tracks + `unidentified/` jingles. Most are fixed 180 s renders with a fade-out in the last ~5 s. |
| `music/Pokémon Yellow Soundtrack MP3/Part I - Stereo/` | source `ost_stereo` | 55 tracks, 48 kHz, real stereo panning, 1–1.5 min each with a fade-out in the last ~10 s |
| `music/Pokémon Yellow Soundtrack MP3/Part II - Mono/` | source `ost_mono` | The same 55 recordings, L = R |
| `music/battles/{wild,trainer}.mp3` | nothing | Byte-identical copies of zophar `12` and `09` (old names 25, 24) |
| `music/locations/*.mp3` | nothing | Copies of zophar `05`, `11` and `07` |
| `music/locations/default.wav`, `music/battles/*.wav` | default location track | Placeholders from `generate_tracks.py` |
| `music/events/` | nothing | Empty |

## Known limitations

In brief:

- All trainer battles use the regular trainer theme.
- Tracks fade out and restart every 3 minutes.
- The Lua script never reconnects.
- Pausing the music in the background depends on mGBA pausing itself
  (`pauseOnFocusLost`). If mGBA keeps running in the background, the music keeps playing.
- Read errors on the mGBA connection, mpv timeouts, and malformed events can stop the
  controller.
