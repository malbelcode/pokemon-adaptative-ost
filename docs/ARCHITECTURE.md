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
   It holds no music logic: it reports raw song ids.
2. **`python/controller.py`.** A blocking TCP server that accepts one mGBA connection at a
   time and feeds each line to `AdaptiveOST.handle_event`. `AdaptiveOST` decides what
   should play. `read_events` reads with a 0.1 s timeout so it can pause the music when
   messages stop.
3. **`mpv`.** Started by `MusicPlayer.start()` with `--idle=yes --no-video
   --input-ipc-server=/tmp/pokemon-adaptive-ost-mpv.sock`. It is controlled with
   `loadfile … replace`, `set_property loop-file` and `set_property pause`.
   `send_command` holds a lock, because the mpv event thread also sends commands.
   With `fade` set (the music player: `MUSIC_FADE` = 0.25 s), `play()` ramps `volume`
   down to 0 over `fade` seconds, loads the file, waits for its first `playback-restart`
   event after `start-file`, and ramps back up. `play_lock` keeps two switches from
   interleaving. No fade runs while paused, and none on the fanfare player.

## Lua → Python protocol

Newline-delimited JSON over TCP to `127.0.0.1:8765`. Each line is one event:

| `event` | Sent when | Fields |
| --- | --- | --- |
| `MAP_CHANGED` | At script start, and whenever `wCurMap` changes | `map_id` (int, 0–248) |
| `BATTLE_CHANGED` | At script start, and whenever `wIsInBattle` changes | `state`, `value`, `map_id`, `battle_result` |
| `MUSIC_CHANGED` | The game starts a new song: music channels 0 and 1 (`wChannelSoundIDs`) change to the same non-zero id. Every song uses both channels, so this catches 2-channel songs too. Channels 4–7 are sound effects. | `music_id` (bank-relative, not interpreted by Lua) |
| `SFX_CHANGED` | The sound effect on channel 4 (`wChannelSoundIDs + 4`, 0xC02A) changes, including back to 0 when it ends. Every fanfare starts on channel 4. | `sound_id` (0 = none), `bank` (`wAudioROMBank`, 0xC0EF) |
| `TRAINER_SPOTTED` | The byte at 0xCD3D changes to 255 (a trainer has seen the player) | none |
| `HEARTBEAT` | Every 10 frames (~0.17 s at full speed). Stops while mGBA is paused. | none |
| `STATE_LOADED` | `emu:currentFrame()` does not advance by exactly 1 since the last frame (savestate load, rewind or reset; mGBA restores the frame counter from the state). That frame's other checks are skipped and all `previous` values are re-read. | `map_id`, `state`, `value`, `battle_result` |

`state` is derived from `wIsInBattle`:

| `value` | `state` |
| --- | --- |
| 0 | `OVERWORLD` |
| 1 | `WILD_BATTLE` |
| 2 | `TRAINER_BATTLE` |
| 255 | `LOST_BATTLE` |
| other | `UNKNOWN` |

The Lua script has no song table. `MUSIC_CHANGED` ids are interpreted by the controller
(`SONGS` in `controller.py`), because ids are bank-relative and some need context.

Example session:

```json
{"event":"MAP_CHANGED","map_id":12}
{"event":"BATTLE_CHANGED","state":"OVERWORLD","value":0,"map_id":12,"battle_result":0}
{"event":"MUSIC_CHANGED","music_id":240}
{"event":"BATTLE_CHANGED","state":"WILD_BATTLE","value":1,"map_id":12,"battle_result":0}
{"event":"MUSIC_CHANGED","music_id":249}
{"event":"BATTLE_CHANGED","state":"OVERWORLD","value":0,"map_id":12,"battle_result":0}
```

## Controller state machine (`AdaptiveOST`)

State: `current_state` (last `BATTLE_CHANGED.state`), `current_map`, `current_track`,
`battle_music_started` (from the battle song until back in the overworld), `victory_playing`,
`song_override` (the overworld song replacing map music), `last_song_id`,
`trainer_spotted_time`. "In the overworld" means `current_state` is `None`/`OVERWORLD` and
`battle_music_started` is false.

`SONGS` maps a song id to a canonical track and a kind:

| Kind | Songs (id) | Action |
| --- | --- | --- |
| `battle` | gym leader 0xEA, trainer 0xED, wild 0xF0, final 0xF3 | Play looped, set `battle_music_started`. Starts with the battle transition animation. |
| `victory` | trainer 0xF6, wild 0xF9, gym leader 0xFC | Play once, set `victory_playing`. |
| `intro` | evil 0xF5, female 0xF8, male 0xFB | In the overworld: play looped until the battle song. |
| `event` | bike 0xD2, surf 0xD6, Oak 0xDB, rival 0xDE, museum guide 0xE1, Jessie & James 0x9C, Pikachu surfing 0x99, intro movie 0xDC, title screen 0xC3, Hall of Fame 0xCA, credits 0xC7 | In the overworld: play looped and keep it across `MAP_CHANGED` until the game starts another song. |
| `evolution` | evolution 0xE5 (`MUSIC_SAFARI_ZONE`) | Like `event`, but also while the battle state is still set (evolution follows a battle). |
| `jingle` | Pokémon healed 0xE8, Jigglypuff 0xD0 | In the overworld: play once, then the map's track (mpv `end-file`). |

Shared ids are resolved from the `Song` entry: `only_maps` (map symbols where the id means
this song) or `unless_map_music` (the map song the id means on maps that use it).

| id | Song | Rule | Otherwise |
| --- | --- | --- | --- |
| 0xF3 | final battle | `only_maps` `CHAMPIONS_ROOM` | `MUSIC_ROUTES3` |
| 0xCA / 0xC7 | Hall of Fame / credits | `only_maps` `HALL_OF_FAME` | `MUSIC_CELADON` / `MUSIC_CITIES2` |
| 0xC3 | title screen | `unless_map_music` `MUSIC_CITIES1` | Viridian/Pewter music |
| 0xD0 | Jigglypuff | `unless_map_music` `MUSIC_VERMILION` | Vermilion music |
| 0xE5 | evolution | `unless_map_music` `MUSIC_SAFARI_ZONE` | Safari Zone music (same song) |
| 0xF5/0xF8/0xFB | trainer intros | within 3 s of `TRAINER_SPOTTED` | 0xFB is `MUSIC_INDIGO_PLATEAU` |

 Any other id in the overworld means the game went
back to map music: clear `song_override` and play the map's track, unless a jingle is
still playing.

| Event | Action |
| --- | --- |
| `MAP_CHANGED` | Store `current_map`. In the overworld with no `song_override`, play the map's track. |
| `MUSIC_CHANGED` | Ignore a repeat of `last_song_id`. Otherwise act on `SONGS` as above and log `[MUSIC]`. |
| `SFX_CHANGED` | Look up `(bank, sound_id)` in `FANFARES`. A fanfare pauses the music player and plays once in the second mpv (`[FANFARE]`). Any other value, including 0, ends the current fanfare and resumes the music where it stopped. |
| `TRAINER_SPOTTED` | Store `trainer_spotted_time`. If the last song was an intro id within 3 s, play it now (the song can start just before the flag). |
| `BATTLE_CHANGED` with `WILD_BATTLE` / `TRAINER_BATTLE` | Clear `song_override`. Keep the music if `battle_music_started`. Otherwise (no battle id seen) play `BATTLE_TRACKS[state]`, looped. |
| `BATTLE_CHANGED` with `OVERWORLD` | Clear `battle_music_started`, `victory_playing` and `song_override`, and play the map's track. This cuts off a victory fanfare that is still playing, as the game does. |
| `BATTLE_CHANGED` with `LOST_BATTLE` / `UNKNOWN` | Only stores the state. The current track keeps playing. |
| `STATE_LOADED` | Set `current_map` and `current_state`, clear the flags and `last_song_id`, stop a fanfare, log `[STATE]`. Play the battle track for `WILD_BATTLE` / `TRAINER_BATTLE`, or the map's track. Lua re-reports the current song on the next frame, so a bike ride or gym battle is restored. |
| `HEARTBEAT` | Ignored by `handle_event`. Like every message, it resumes paused music. |
| No message for 0.5 s (`HEARTBEAT_TIMEOUT`) | Pause both mpv players and log `[PAUSE]`. mGBA runs no frames while paused, including when its "pause when inactive" option pauses it in the background. The next message resumes playback at the same position. |
| mGBA disconnects | Pause mpv. The next connection's first message resumes it. |
| mpv `end-file` with `reason: eof` | After a victory fanfare or a jingle, play the map's track if in the overworld. On the fanfare player, end the fanfare (if the game has not already). These callbacks run on the mpv event threads. |

### Fanfares

Fanfares are sound effects, not songs. While one plays on channels 4–6, the engine stops
advancing music channels 0–2 and resumes them afterwards. The controller does the same:
a second `MusicPlayer` (socket `/tmp/pokemon-adaptive-ost-mpv-fanfare.sock`, log tag
`[FANFARE]`) plays the recording, and the music player stays paused while `fanfare` is
set or mGBA is paused (`update_pause`). mpv keeps the pause across `loadfile`, so a track
that starts during a fanfare (the battle ends, for example) waits for it. The fanfare ends
when the game's sound id changes, or when the recording ends, whichever comes first.

| `(bank, id)` | Sound effect | Track |
| --- | --- | --- |
| (0x02/0x1F/0x20, 0x86) | `SFX_GET_ITEM_1`: an item received, a move learned (party menu) | `60 Item Fanfare` |
| (0x02/0x08/0x1F/0x20, 0x89), (0x20, 0x96) | `SFX_GET_ITEM_2`: a hidden item, an evolution done, slots ×300 | `61 Hidden Item Fanfare` |
| (0x02/0x1F, 0x94) | `SFX_GET_KEY_ITEM`: a key item, an in-game trade, slots ×100 | `63 Key Item Fanfare` |
| (0x02/0x1F, 0x91) | `SFX_POKEDEX_RATING`: Oak's rating at 10–39 owned | `62 Pokedex Rating Fanfare` |
| (0x08, 0x86) | `SFX_LEVEL_UP`: level up or move learned in battle (the same text command as the item fanfare) | `58 Level Up Fanfare` |
| (0x08, 0x9A) | `SFX_CAUGHT_MON`: a Pokémon caught | `59 Pokemon Caught Fanfare` |

Oak's rating (`PlayPokedexRatingSfx`) stops the music, plays one of these from a fixed
bank, then restarts the map song. The restart has the same id, so the map track resumes.

`play_track` skips the request when the track is already the current one, so repeated
events don't restart the song.

Map track lookup: `data/map_music.json[str(map_id)].track` is a canonical track name, which
`TrackResolver` (`python/music_sources.py`) turns into a file in the selected source.
If it is `null`, or the name is in no source, the current music keeps playing and `[MAP]` logs it.

## Music sources

`config/music_sources.json` maps a source name to a folder and names the default.
`controller.py --source NAME` overrides the default for one run. All folders use the
same canonical file names (`NN Title.mp3`), set by `tools/normalize_music.py`, so switching
a source changes only the folder. `TrackResolver.resolve(name)` looks in the selected
source first, then in the others in config order, and logs `[TRACK]` when it falls back
or finds nothing. Results are cached per name.

Numbers 01–55 follow the official soundtrack's order. 56–63 exist only in the zophar set
(heal jingle, Jigglypuff, fanfares). Zophar's fanfare titles were wrong; 58–63 are named
after the sound effect each recording matched by melody. Files the game never plays as music were deleted:
01, 03, 48–55 and zophar's 44 unnamed 1–4 s jingles (`NOT_NEEDED` in the tool).

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
| `wChannelSoundIDs` | `0xC026` (+0, +1, +4) | Verified: audio WRAM, same as English. +4 is the first sound-effect channel. |
| `wAudioROMBank` | `0xC0EF` | Verified: compared with banks 0x08 and 0x1F in code. Sent with `SFX_CHANGED`. |
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
| `music/zophar/` | source `zophar` (default) | 53 tracks. Most are fixed 180 s renders with a fade-out in the last ~5 s. 56–63 are zophar-only jingles and fanfares. |
| `music/ost/` | source `ost` | 45 tracks, 48 kHz, real stereo panning, 1–1.5 min each with a fade-out in the last ~10 s |

## Known limitations

In brief:

- The title screen after a soft reset in Viridian or Pewter plays that city's music: `wCurMap` still holds the old map, and 0xC3 is also `MUSIC_CITIES1`.
- The script polls channel 4 once per frame. If a sound ends and the same fanfare starts again within one frame, it is not seen as new.
- Fanfares have not been heard in mGBA yet. Ids and banks come from the ROM and the disassembly.
- Tracks fade out and restart every 3 minutes.
- The Lua script never reconnects.
- Pausing the music in the background depends on mGBA pausing itself
  (`pauseOnFocusLost`). If mGBA keeps running in the background, the music keeps playing.
- Read errors on the mGBA connection, mpv timeouts, and malformed events can stop the
  controller.
