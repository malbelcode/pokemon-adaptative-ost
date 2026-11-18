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
| `wChannelSoundIDs` | 0xC026 (+0..+7) | 16 | verified, audio WRAM same as English | `pokemon_yellow.lua` (channels 0–2) |
| trainer sprite offset (`TRAINER_SPOTTED`) | 0xCD3D | 204 | in use, unverified meaning. 255 = trainer spotted. Many references, so it is likely a shared scratch byte. | `pokemon_yellow.lua` |
| `wBattleResult` | 0xCF0B | **0** | **wrong**, probably the English address | `pokemon_yellow.lua` (logged only) |
| `wNewSoundID` (candidate) | 0xC0EE | 19 | unverified | — |
| `wAudioROMBank` (candidate) | 0xC0EF | 26 | unverified, needed for `(bank, id)` keys | — |
| `wAudioSavedROMBank` (candidate) | 0xC0F0 | 20 | unverified | — |
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

Victory songs, as used by the Lua victory detector. All three music channels hold the
same id. The bank has not been confirmed from the ROM.

| Constant | id |
| --- | --- |
| MUSIC_DEFEATED_TRAINER | 0xF6 (246) |
| MUSIC_DEFEATED_WILD_MON | 0xF9 (249) |
| MUSIC_DEFEATED_GYM_LEADER | 0xFC (252) |

Ids not yet extracted: battle themes, trainer intros, bike, surf, Yellow-only songs
(AUDIO_4). Getting them needs the SFX header tables or an in-game read of
`wChannelSoundIDs` and `wAudioROMBank`.

## Audio files (measured)

All sets use canonical names (`NN Title.mp3`) after `tools/normalize_music.py --apply`.
That script holds the original → canonical table for each set.

- The zophar set (`music/zophar/`, originally "Pokemon Yellow (MP3).zophar") has 98
  files, 313 MB, 44.1 kHz.
  Most are exactly 180.0 s with a fade-out: −19 dB at 170 s, −49 dB at 176 s, −66 dB at
  179 s. Its 44 unnamed 1–4 s jingles (old names 46, 50, 57–98) are in `unidentified/`.
- `music/ost/` is "Part I - Stereo" of "Pokémon Yellow Soundtrack MP3": 55 tracks,
  181 MB, 48 kHz, ~340 kbps, with cover art. Lengths vary (Pallet Town 79.5 s, Wild
  Battle 91.2 s). They fade out over the last ~10 s (Pallet Town: −15 dB at 60 s, −20 dB
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
- `music/battles/*.mp3` and `music/locations/*.mp3` are byte-identical copies of zophar
  `09`, `12`, `05`, `11` and `07`. The code no longer uses them.
- No set has a file named "Safari Zone". In Gen 1 the Safari Zone and evolution music is
  the same song, so use `28 Evolution.mp3` (not yet confirmed by listening).
