import json
import re
from pathlib import Path

from map_registry import get_map_name

BASE_DIR = Path(__file__).resolve().parent.parent

MAP_CONSTANTS_FILE = BASE_DIR / "data/map_constants.asm"
SONGS_FILE = BASE_DIR / "data/songs.asm"
THEMES_FILE = BASE_DIR / "config/music_themes.json"
OST_DIR = BASE_DIR / "music/Pokemon Yellow (MP3).zophar"
OUTPUT_FILE = BASE_DIR / "data/map_music.json"


def load_maps():
    maps = {}

    pattern = re.compile(
        r"^\s*map_const\s+([A-Z0-9_]+),.*;\s*\$([0-9A-Fa-f]+)"
    )

    with MAP_CONSTANTS_FILE.open(encoding="utf-8") as file:
        for line in file:
            match = pattern.match(line)

            if match:
                name = match.group(1)
                map_id = int(match.group(2), 16)

                if map_id in maps:
                    raise ValueError(f"Duplicate map ID: {map_id}")

                maps[map_id] = name

    return maps


def load_map_songs():
    songs = {}

    pattern = re.compile(
        r"^\s*db\s+(MUSIC_[A-Z0-9_]+),.*;\s*([A-Z0-9_]+)\s*$"
    )

    with SONGS_FILE.open(encoding="utf-8") as file:
        for line in file:
            match = pattern.match(line)

            if match:
                music_id = match.group(1)
                map_name = match.group(2)

                if map_name in songs:
                    raise ValueError(f"Duplicate song entry: {map_name}")

                songs[map_name] = music_id

    return songs


def main():
    maps = load_maps()
    map_songs = load_map_songs()

    with THEMES_FILE.open(encoding="utf-8") as file:
        themes = json.load(file)

    map_symbols = set(maps.values())
    song_symbols = set(map_songs)

    if map_symbols != song_symbols:
        missing_songs = map_symbols - song_symbols
        missing_maps = song_symbols - map_symbols

        raise ValueError(
            f"Map/song mismatch.\n"
            f"Maps without song entries: {sorted(missing_songs)}\n"
            f"Song entries without maps: {sorted(missing_maps)}"
        )

    registry = {}
    unresolved = set()

    for map_id, map_symbol in sorted(maps.items()):
        music_id = map_songs[map_symbol]
        filename = themes.get(music_id)

        track = None

        if filename:
            track_path = OST_DIR / filename

            if not track_path.is_file():
                raise FileNotFoundError(
                    f"Missing OST file for {music_id}: {track_path}"
                )

            track = str(track_path.relative_to(BASE_DIR))
        else:
            unresolved.add(music_id)

        registry[str(map_id)] = {
            "name": get_map_name(map_id),
            "symbol": map_symbol,
            "music_id": music_id,
            "track": track
        }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(registry, file, indent=4, ensure_ascii=False)
        file.write("\n")

    print(f"Generated: {OUTPUT_FILE}")
    print(f"Maps registered: {len(registry)}")
    print(f"Music themes configured: {len(themes)}")
    print(f"Unresolved music themes: {sorted(unresolved)}")

    unresolved_maps = sum(
        1 for entry in registry.values()
        if entry["track"] is None
    )

    print(f"Maps without assigned tracks: {unresolved_maps}")


if __name__ == "__main__":
    main()
