"""Rename the soundtrack sets in music/ to one shared set of canonical names.

After this runs, the same song has the same file name in every set, for example
"05 Pallet Town.mp3", so a music source is just a folder
(see config/music_sources.json).

Put each set in its folder first, with the original file names:
    music/zophar/        the zophar rip ("Pokemon Yellow (MP3).zophar")
    music/ost/           "Part I - Stereo" of "Pokémon Yellow Soundtrack MP3"
The soundtrack's "Part II - Mono" is not needed: each file is a stereo downmix.

Usage:
    python3 tools/normalize_music.py            # dry run: print the plan
    python3 tools/normalize_music.py --apply    # rename the files
    python3 tools/normalize_music.py --revert   # restore the original names

The pairing of zophar files with soundtrack files was checked by comparing the
audio (chroma similarity of the first 30 s), not only by title.
Running it again does nothing: renames that are already done are skipped.
"""
import argparse
import sys
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MUSIC_DIR = BASE_DIR / "music"

ZOPHAR_DIR = MUSIC_DIR / "zophar"
# Soundtrack file names start with the disc part: "1.05 Pallet Town.mp3" (stereo).
OST_PARTS = {
    "1": MUSIC_DIR / "ost",
}

# Unnamed zophar jingles (1-4 s each) that match no soundtrack title.
UNIDENTIFIED_DIR = "unidentified"
ZOPHAR_UNIDENTIFIED = ["46", "50"] + [str(n) for n in range(57, 99)]

# (number, canonical title, zophar file stem or None, soundtrack title or None)
# Numbers 01-55 follow the soundtrack's order; 56+ exist only in the zophar set.
TRACKS = [
    ("01", "Game Freak", None, "Game Freak"),
    ("02", "Opening Movie", "01 Opening (part 1)", "Opening Movie"),
    ("03", "Pikachu", None, "Pikachu!"),
    ("04", "Title Screen", "02 Opening (part 2)", "Title Screen"),
    ("05", "Pallet Town", "04 Pallet Town's Theme", "Pallet Town"),
    ("06", "Professor Oak", "14 Professor Oak", "Professor Oak"),
    ("07", "Professor Oak's Laboratory", "32 Oak Research Lab", "Professor Oak's Laboratory"),
    ("08", "A Rival Appears", "15 Rival Appears", "A Rival Appears"),
    ("09", "Battle (Trainer)", "24 Battle (VS Trainer)", "Battle! (Trainer)"),
    ("10", "Victory (Trainer)", "27 Victory (VS Trainer)", "Victory! (Trainer)"),
    ("11", "Road to Viridian City (Leaving Pallet Town)",
     "19 The Road to Viridian City ~ from Pallet", "Road To Viridian City- Leaving Pallet Town"),
    ("12", "Battle (Wild Pokemon)", "25 Battle (VS Wild Pokemon)", "Battle! (Wild Pokémon)"),
    ("13", "Victory (Wild Pokemon)", "28 Victory (VS Wild Pokemon)", "Victory! (Wild Pokémon)"),
    ("14", "Pewter City", "07 Pewter City's Theme", "Pewter City"),
    ("15", "Pokemon Center", "05 Pokemon Center", "Pokémon Center"),
    ("16", "Viridian Forest", "38 Viridian Forest", "Viridian Forest"),
    ("17", "A Trainer Appears (Boy Version)", "45 Trainer Appears (Boy Version)",
     "A Trainer Appears (Boy Version)"),
    ("18", "Guide", "16 Guide", "Guide"),
    ("19", "Pokemon Gym", "06 Pokemon Gym", "Pokémon Gym"),
    ("20", "Battle (Gym Leader)", "23 Battle (VS Gym Leader)", "Battle! (Gym Leader)"),
    ("21", "Victory (Gym Leader)", "29 Victory (VS Gym Leader)", "Victory! (Gym Leader)"),
    ("22", "Road to Cerulean City (Leaving Mt. Moon)",
     "20 The Road to Cerulean ~ from Mt. Moon", "Road To Cerulean City- Leaving Mt. Moon"),
    ("23", "A Trainer Appears (Girl Version)", "44 Trainer Appears (Girl Version)",
     "A Trainer Appears (Girl Version)"),
    ("24", "Caves of Mt. Moon", "39 Mt. Moon Cave", "Caves Of Mt. Moon"),
    ("25", "Theme of Jessie and James", "48 Musashi and Kojiro Theme", "Theme Of Jessie And James"),
    ("26", "Cerulean City", "08 Cerulean City's Theme", "Cerulean City"),
    ("27", "To Bill (Leaving Cerulean City)", "03 To Bill's Origin ~ From Cerulean",
     "To Bill- Leaving Cerulean City"),
    ("28", "Evolution", "17 Evolution", "Evolution"),
    ("29", "Vermilion City", "11 Vermilion City's Theme", "Vermilion City"),
    ("30", "The S.S. Anne", "13 St. Anne", "The S.S. Anne"),
    ("31", "Cycling", "34 Cycling", "Cycling"),
    ("32", "Road to Lavender Town (Leaving Vermilion City)",
     "21 The Road to Lavender Town ~ from Vermilion", "Road To Lavender Town- Leaving Vermilion City"),
    ("33", "Lavender Town", "12 Lavender Town's Theme", "Lavender Town"),
    ("34", "Pokemon Tower", "41 Pokemon Tower", "Pokémon Tower"),
    ("35", "Celadon City", "09 Celadon City's Theme", "Celadon City"),
    ("36", "Rocket Game Corner", "36 Casino", "Rocket Game Corner"),
    ("37", "Rocket Hideout", "37 Team Rocket Hideout", "Rocket Hideout"),
    ("38", "A Trainer Appears (Bad Guy Version)", "43 Trainer Appears (Bad Guy Version)",
     "A Trainer Appears (Bad Guy Version)"),
    ("39", "Pikachu's Beach", "47 Pikachu's Beach", "Pikachu's Beach"),
    ("40", "Silph Co", "42 Sylph Company", "Silph Co."),
    ("41", "The Sea", "35 Ocean", "The Sea"),
    ("42", "Cinnabar Island", "10 Cinnabar Island's Theme", "Cinnabar Island"),
    ("43", "Pokemon Mansion", "40 Pokemon Mansion", "Pokémon Mansion"),
    ("44", "The Final Road", "22 The Last Road", "The Final Road"),
    ("45", "Final Battle (Rival)", "26 Last Battle (VS Rival)", "Final Battle! (Rival)"),
    ("46", "Hall of Fame", "31 Into the Hall", "Hall Of Fame"),
    ("47", "Ending Theme", "30 Ending", "Ending Theme"),
    ("48", "Opening Movie (Red - Blue Version)", None, "Opening Movie (Red - Blue Version)"),
    ("49", "Theme of Giovanni (Unused)", "49 Unknown Song", "Theme Of Giovanni (Unused)"),
    ("50", "Diglett's Cave (Unused)", None, "Diglett's Cave (Unused)"),
    ("51", "Field Route (Unused)", None, "Field Route (Unused)"),
    ("52", "Victory (Unused)", None, "Victory! (Unused)"),
    ("53", "Tension (Unused)", None, "Tension (Unused)"),
    ("54", "Trade (Unused)", None, "Trade (Unused)"),
    ("55", "Ending Theme (Unused)", None, "Ending Theme (Unused)"),
    ("56", "Pokemon Recovery", "18 Pokemon Recovery", None),
    ("57", "Jigglypuff's Song", "33 Jigglypuff's Song", None),
    ("58", "Item Fanfare", "51 Item Fanfare", None),
    ("59", "Pokemon Received Fanfare", "52 Pokemon Received Fanfare", None),
    ("60", "Level Up Fanfare", "53 Level Up Fanfare", None),
    ("61", "Pokemon Capture Fanfare", "54 Pokemon Capture Fanfare", None),
    ("62", "Pokedex Fanfare 1", "55 Pokedex Fanfare 1", None),
    ("63", "Pokedex Fanfare 2", "56 Pokedex Fanfare 2", None),
]


def nfc(name):
    return unicodedata.normalize("NFC", name)


def find(directory, name):
    """Return the entry of `directory` whose name equals `name` (any Unicode normalization)."""
    if not directory.is_dir():
        return None

    wanted = nfc(name)

    for entry in directory.iterdir():
        if nfc(entry.name) == wanted:
            return entry

    return None


def plan():
    """Yield (directory, original relative name, canonical relative name)."""
    for number, title, zophar, ost in TRACKS:
        canonical = f"{number} {title}.mp3"

        if zophar:
            yield ZOPHAR_DIR, f"{zophar}.mp3", canonical

        if ost:
            for part, directory in OST_PARTS.items():
                yield directory, f"{part}.{number} {ost}.mp3", canonical

    for stem in ZOPHAR_UNIDENTIFIED:
        yield ZOPHAR_DIR, f"{stem}.mp3", f"{UNIDENTIFIED_DIR}/{stem}.mp3"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="rename the files")
    group.add_argument("--revert", action="store_true", help="restore the original names")
    args = parser.parse_args()

    counts = {"rename": 0, "done": 0, "missing": 0}

    for directory, original, canonical in plan():
        source, target = (canonical, original) if args.revert else (original, canonical)
        source_path = find(directory, source) if "/" not in source else find(
            directory / source.split("/")[0], source.split("/")[1])
        target_parent = directory / Path(target).parent
        target_path = find(target_parent, Path(target).name)
        label = f"{directory.relative_to(MUSIC_DIR)}: {source} -> {target}"

        if source_path is None:
            if target_path is not None:
                counts["done"] += 1
            else:
                counts["missing"] += 1
                print(f"[MISSING] {directory.relative_to(MUSIC_DIR)}: neither {source!r} nor {target!r}")
            continue

        if target_path is not None:
            sys.exit(f"[ERROR] Both names exist, refusing to overwrite: {label}")

        counts["rename"] += 1
        print(("[RENAME] " if args.apply or args.revert else "[PLAN] ") + label)

        if args.apply or args.revert:
            target_parent.mkdir(exist_ok=True)
            source_path.rename(target_parent / Path(target).name)

    if args.revert:
        unidentified = ZOPHAR_DIR / UNIDENTIFIED_DIR
        if unidentified.is_dir() and not any(unidentified.iterdir()):
            unidentified.rmdir()

    for directory in [ZOPHAR_DIR, *OST_PARTS.values()]:
        known = {nfc(c if args.revert else o) for d, o, c in plan() if d == directory}
        known |= {nfc(o if args.revert else c) for d, o, c in plan() if d == directory}
        extra = [e.name for e in directory.iterdir()
                 if e.is_file() and nfc(e.name) not in known] if directory.is_dir() else []
        for name in extra:
            print(f"[UNMAPPED] {directory.relative_to(MUSIC_DIR)}: {name}")

    verb = "renamed" if args.apply or args.revert else "to rename (dry run, pass --apply)"
    print(f"\n{counts['rename']} {verb}, {counts['done']} already done, {counts['missing']} missing")


if __name__ == "__main__":
    main()
