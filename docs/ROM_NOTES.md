# ROM notes (Spanish Pokémon Yellow)

These facts were checked statically against the ROM. They are recorded here so they don't
have to be re-derived. Re-check them with `tools/rom_inspect.py`.

## Cartridge

| Field | Value |
| --- | --- |
| Name | Pokémon Edición Amarilla: Edición Especial Pikachu (Spain) |
| Header title | `POKEMON YELAPSS` |
| SHA-1 | `1dc242039218fba50928d1afb66b70565b6b9daf` |
| Size / cart type | 1 MiB, MBC5+RAM+BATTERY (0x1B), CGB-compatible (0x80), SGB (0x03) |

## WRAM addresses

The reference count is the number of `ld a,[nn]` / `ld [nn],a` / `ld hl,nn` instructions
in the ROM (`rom_inspect.py ROM refs ADDR`). A real variable usually has more than 10.

| Symbol (pokeyellow name) | Address | Refs | Status | Used by |
| --- | --- | --- | --- | --- |
| `wCurMap` | 0xD362 | 85 | verified | `pokemon_yellow.lua` |
| `wIsInBattle` | 0xD05B | 99 | verified (0 overworld, 1 wild, 2 trainer, 0xFF lost) | `pokemon_yellow.lua` |
| `wCurOpponent` | 0xD05D | 30 | plausible | `diagnostic.lua` |
| `wBattleType` | 0xD05E | 35 | plausible | `diagnostic.lua` |
| `wChannelSoundIDs` | 0xC026 (+0..+7) | 16 | verified, audio WRAM same as English | `pokemon_yellow.lua` (channels 0, 1 and 4) |
| trainer sprite offset (`TRAINER_SPOTTED`) | 0xCD3D | 204 | in use, unverified meaning. 255 = trainer spotted. Many references, so it is likely a shared scratch byte. | `pokemon_yellow.lua` |
| `wBattleResult` | 0xCF0B | **0** | **wrong**, probably the English address | `pokemon_yellow.lua` (logged only) |
| `wNewSoundID` | 0xC0EE | 19 | verified: read in `PlaySound` (ROM 0x223B) just before it clears C02A–C02D | — |
| `wAudioROMBank` | 0xC0EF | 26 | verified: read and compared with 0x08 (ROM 0x96C3) and 0x1F (0x6191F); 9 reads, 17 writes. 16 bytes above the address computed from pokeyellow's `wram.asm`, like `wChannelSoundIDs` | `pokemon_yellow.lua` (`SFX_CHANGED`) |
| `wAudioSavedROMBank` | 0xC0F0 | 20 | plausible: copied into 0xC0EF (ROM 0x2804) | — |
| `wMapMusicSoundID` / `wMapMusicROMBank` (candidates) | 0xD35F / 0xD360 | 4 / 2 | unverified, inferred as 3 and 2 bytes before `wCurMap`, as in pokered | — |

Rule of thumb: in the D-range (overworld and battle variables), Spanish addresses are
4–5 bytes higher than English Yellow. The audio engine's C0xx variables are unchanged.
Candidates are confirmed by running `lua/diagnostic.lua` (add the address to its table)
at a known moment in game.

## Music ids

Song ids are **bank-relative**. The same id means different songs in different audio
banks, so any lookup by id must also use the bank.

Map songs, read from the ROM's `MapSongBanks` table at ROM offset **0xFC000**. It is
identical to `data/songs.asm`, all 249 maps.

| Constant | id | bank |
| --- | --- | --- |
| MUSIC_PALLET_TOWN | 0xBA | 0x02 |
| MUSIC_POKECENTER | 0xBD | 0x02 |
| MUSIC_GYM | 0xC0 | 0x02 |
| MUSIC_CITIES1 | 0xC3 | 0x02 |
| MUSIC_CITIES2 | 0xC7 | 0x02 |
| MUSIC_CELADON | 0xCA | 0x02 |
| MUSIC_CINNABAR | 0xCD | 0x02 |
| MUSIC_VERMILION | 0xD0 | 0x02 |
| MUSIC_LAVENDER | 0xD4 | 0x02 |
| MUSIC_SS_ANNE | 0xD8 | 0x02 |
| MUSIC_SAFARI_ZONE | 0xE5 | 0x02 |
| MUSIC_ROUTES1 | 0xEB | 0x02 |
| MUSIC_ROUTES2 | 0xEF | 0x02 |
| MUSIC_ROUTES3 | 0xF3 | 0x02 |
| MUSIC_ROUTES4 | 0xF7 | 0x02 |
| MUSIC_INDIGO_PLATEAU | 0xFB | 0x02 |
| MUSIC_OAKS_LAB | 0xCD | 0x1F |
| MUSIC_GAME_CORNER | 0xD9 | 0x1F |
| MUSIC_DUNGEON1 | 0xDF | 0x1F |
| MUSIC_DUNGEON2 | 0xE3 | 0x1F |
| MUSIC_DUNGEON3 | 0xE7 | 0x1F |
| MUSIC_CINNABAR_MANSION | 0xEB | 0x1F |
| MUSIC_POKEMON_TOWER | 0xEF | 0x1F |
| MUSIC_SILPH_CO | 0xF2 | 0x1F |

Collisions in the table above: 0xCD (Cinnabar / Oak's Lab), 0xEB (Routes1 / Cinnabar
Mansion), 0xEF (Routes2 / Pokémon Tower).

### Song ids from the ROM's music headers

Each audio bank starts with its `SFX_Headers` table at `bank * 0x4000`. A song's id is
the index of its first 3-byte channel header. The top 2 bits of that header's first byte
are the channel count − 1, so the next song's id is id + channel count. Walking the table
reproduces every map song id above, and the songs follow the constant order in
`data/music_constants.asm`. Re-check with a short script: read `rom[bank*0x4000 + id*3]`.

While a song plays, the audio engine stores its id in `wChannelSoundIDs` for each of its
channels. Every song header walked starts with channels 1 and 2, so the Lua script
reports a song when channels 0 and 1 change to the same id (2-channel songs such as
Jigglypuff's leave channel 2 unchanged).

Bank 0x02 (AUDIO_1), songs that are not map songs:

| Constant | id | Used by |
| --- | --- | --- |
| MUSIC_MEET_PROF_OAK | 0xDB | controller `SONGS` |
| MUSIC_MEET_RIVAL | 0xDE | controller `SONGS` |
| MUSIC_MUSEUM_GUY | 0xE1 | controller `SONGS` |
| MUSIC_SAFARI_ZONE | 0xE5 | controller `SONGS` as evolution, except on Safari Zone maps |
| MUSIC_PKMN_HEALED | 0xE8 | controller `SONGS` |

Bank 0x08 (AUDIO_2, battle):

| Constant | id | Used by |
| --- | --- | --- |
| MUSIC_GYM_LEADER_BATTLE | 0xEA | controller `SONGS` |
| MUSIC_TRAINER_BATTLE | 0xED | controller `SONGS` |
| MUSIC_WILD_BATTLE | 0xF0 | controller `SONGS` |
| MUSIC_FINAL_BATTLE | 0xF3 | controller `SONGS`, only on `CHAMPIONS_ROOM` (0xF3 is also `MUSIC_ROUTES3`) |
| MUSIC_DEFEATED_TRAINER | 0xF6 (246) | controller `SONGS` |
| MUSIC_DEFEATED_WILD_MON | 0xF9 (249) | controller `SONGS` |
| MUSIC_DEFEATED_GYM_LEADER | 0xFC (252) | controller `SONGS` |

Bank 0x1F (AUDIO_3). The first songs are found by the only 3-song header chain that ends
at Oak's Lab (0xCD):

| Constant | id | Used by |
| --- | --- | --- |
| MUSIC_TITLE_SCREEN | 0xC3 (4 ch) | controller `SONGS`, except on `MUSIC_CITIES1` maps |
| MUSIC_CREDITS | 0xC7 | controller `SONGS`, only on `HALL_OF_FAME` |
| MUSIC_HALL_OF_FAME | 0xCA | controller `SONGS`, only on `HALL_OF_FAME` |
| MUSIC_OAKS_LAB | 0xCD | map song |
| MUSIC_JIGGLYPUFF_SONG | 0xD0 | controller `SONGS`, except on `MUSIC_VERMILION` maps |
| MUSIC_BIKE_RIDING | 0xD2 | controller `SONGS` |
| MUSIC_SURFING | 0xD6 | controller `SONGS` |
| MUSIC_YELLOW_INTRO | 0xDC | controller `SONGS` |
| MUSIC_MEET_EVIL_TRAINER | 0xF5 | controller `SONGS`, within 3 s of a spot |
| MUSIC_MEET_FEMALE_TRAINER | 0xF8 | controller `SONGS`, within 3 s of a spot |
| MUSIC_MEET_MALE_TRAINER | 0xFB | controller `SONGS`, within 3 s of a spot |

Collisions between song starts in different banks, all resolved by `Song.only_maps` /
`unless_map_music` or the trainer window in `controller.py`:

| id | Songs |
| --- | --- |
| 0xC3 | `MUSIC_TITLE_SCREEN` (0x1F) / `MUSIC_CITIES1` (0x02) |
| 0xC7 | `MUSIC_CREDITS` (0x1F) / `MUSIC_CITIES2` (0x02) |
| 0xCA | `MUSIC_HALL_OF_FAME` (0x1F) / `MUSIC_CELADON` (0x02) |
| 0xCD | `MUSIC_OAKS_LAB` (0x1F) / `MUSIC_CINNABAR` (0x02), both map songs |
| 0xD0 | `MUSIC_JIGGLYPUFF_SONG` (0x1F) / `MUSIC_VERMILION` (0x02) |
| 0xEB | `MUSIC_CINNABAR_MANSION` (0x1F) / `MUSIC_ROUTES1` (0x02), both map songs |
| 0xEF | `MUSIC_POKEMON_TOWER` (0x1F) / `MUSIC_ROUTES2` (0x02), both map songs |
| 0xF3 | `MUSIC_FINAL_BATTLE` (0x08) / `MUSIC_ROUTES3` (0x02) |
| 0xFB | `MUSIC_MEET_MALE_TRAINER` (0x1F) / `MUSIC_INDIGO_PLATEAU` (0x02) |

Every other id in `SONGS` starts a song in only one bank.

Bank 0x20 (AUDIO_4, Yellow only). Found as the only other bank whose header table starts
with the 3-byte 0xFF padding and holds a valid song chain:

| Constant | id | Used by |
| --- | --- | --- |
| MUSIC_SURFING_PIKACHU | 0x99 | controller `SONGS` |
| MUSIC_MEET_JESSIE_JAMES | 0x9C | controller `SONGS` |
| MUSIC_YELLOW_UNUSED_SONG | 0x9F (4 ch) | — |

In banks 0x02, 0x08 and 0x1F, ids 0x99/0x9C/0x9F are sound effects on channels 4–6, so
they never appear on music channels 0–1. All audio banks are now walked: 0x02, 0x08,
0x1F and 0x20.

## Fanfare sound effect ids

Sound effect ids were assigned by walking pokeyellow's `audio/headers/sfxheaders{1-4}.asm`
in order (one id per channel entry, from 1). Every channel byte matched the ROM's header
tables at `bank*0x4000`: 0 mismatches in all four banks (95, 119, 103 and 70 effects).

| Sound effect | Bank 0x02 | Bank 0x08 | Bank 0x1F | Bank 0x20 | Channels |
| --- | --- | --- | --- | --- | --- |
| `SFX_GET_ITEM_1` | 0x86 | — (0x86 is `SFX_LEVEL_UP`) | 0x86 | 0x86 | 4–6 |
| `SFX_GET_ITEM_2` | 0x89 | 0x89 | 0x89 | 0x89, 0x96 (`SFX_GET_ITEM2_4_2`, same notes) | 4–6 |
| `SFX_POKEDEX_RATING` | 0x91 | — | 0x91 | — | 4–6 |
| `SFX_GET_KEY_ITEM` | 0x94 | — | 0x94 | — | 4–6 |
| `SFX_LEVEL_UP` | — | 0x86 | — | — | 4–6 |
| `SFX_DEX_PAGE_ADDED` | — | 0x98 | — | — | 4–5 (0.5 s beep, no recording) |
| `SFX_CAUGHT_MON` | — | 0x9A | — | — | 4–6 |

In bank 0x08, 0x91 and 0x94 are battle sound effects, so the bank is needed. The text
command `sound_get_item_1` plays 0x86 from the loaded bank: the item fanfare in the
overworld (also for Rare Candy in the party menu) and the level-up fanfare in battle.
When a sound effect ends, the engine writes 0 to its `wChannelSoundIDs` entry
(`engine_1.asm`, `.skipCry`). While a sound-effect channel is busy, the matching music
channel stops counting down (`Audio1_ApplyMusicAffects`), so the music pauses.

Zophar's fanfare titles do not match the sounds. Each recording was matched by melody:
the chroma of the MP3 against the notes of each sound effect's channels (from
`audio/sfx/*.asm`). The best match scored 0.88–0.96, and the runner-up at most 0.49.

| File (new name) | Zophar title | Sound effect |
| --- | --- | --- |
| `58 Level Up Fanfare` | Item Fanfare | `SFX_LEVEL_UP` |
| `59 Pokemon Caught Fanfare` | Pokemon Received Fanfare | `SFX_CAUGHT_MON` |
| `60 Item Fanfare` | Level Up Fanfare | `SFX_GET_ITEM_1` |
| `61 Hidden Item Fanfare` | Pokemon Capture Fanfare | `SFX_GET_ITEM_2` |
| `62 Pokedex Rating Fanfare` | Pokedex Fanfare 1 | `SFX_POKEDEX_RATING` |
| `63 Key Item Fanfare` | Pokedex Fanfare 2 | `SFX_GET_KEY_ITEM` |

The recordings have about 1 s of silence at the end. Their audible length (0.98–3.11 s)
matches the game's note lengths, so the music resumes on the game's signal (id back to 0).

## Audio files (measured)

All sets use canonical names (`NN Title.mp3`) after `tools/normalize_music.py --apply`.
That script holds the original → canonical table for each set.

- The zophar set (`music/zophar/`, originally "Pokemon Yellow (MP3).zophar") had 98
  files, 313 MB, 44.1 kHz. 53 are kept.
  Most are exactly 180.0 s with a fade-out: −19 dB at 170 s, −49 dB at 176 s, −66 dB at
  179 s. Its 44 unnamed 1–4 s jingles (old names 46, 50, 57–98) and "Unknown Song"
  (Giovanni, unused) were deleted.
- `music/ost/` is "Part I - Stereo" of "Pokémon Yellow Soundtrack MP3": 55 tracks,
  181 MB, 48 kHz. 45 are kept: Game Freak, Pikachu, the Red/Blue opening and the 7
  "(Unused)" songs were deleted, since the game never plays them as music. ~340 kbps,
  with cover art. Lengths vary (Pallet Town 79.5 s, Wild Battle 91.2 s). They fade out over the last ~10 s (Pallet Town: −15 dB at 60 s, −20 dB
  at 70 s, −36 dB at 77.5 s). Real panning: L−R peak −3 to −4 dB.
- The rip's "Part II - Mono" was deleted because it adds nothing. Each file is 2-channel
  with L = R (L−R peak −91 dB) and equals g·(L+R) of the stereo file, with no time
  offset. g is 0.6–0.77 per track, and the residual is −36 to −39 dB, which is MP3
  coding noise. `mpv --audio-channels=mono` gives the same result.
- Zophar ↔ soundtrack pairing was checked by audio, not by title: chroma similarity of
  the first 30 s is 0.82–0.97 for every pair and at most 0.46 for the runner-up. Zophar
  "Opening (part 1/2)" = "Opening Movie" / "Title Screen", "Unknown Song" = "Theme Of
  Giovanni (Unused)", and "Into the Hall" = "Hall Of Fame".
- Route songs by map (`data/songs.asm`): `MUSIC_ROUTES1` Routes 1–2, `MUSIC_ROUTES2`
  Routes 24–25 → `27 To Bill`, `MUSIC_ROUTES3` Routes 3–10 and 16–22 → `22 Road to
  Cerulean City`, `MUSIC_ROUTES4` Routes 11–15 → `32 Road to Lavender Town`,
  `MUSIC_INDIGO_PLATEAU` Route 23 and the League → `44 The Final Road`. Inferred from
  geography and titles, not yet confirmed by listening in game.
- No set has a file named "Safari Zone". In Gen 1 the Safari Zone and evolution music is
  the same song (`MUSIC_SAFARI_ZONE`, 0xE5), so `config/music_themes.json` maps it to
  `28 Evolution.mp3`.
