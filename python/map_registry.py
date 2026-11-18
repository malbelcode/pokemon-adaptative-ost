import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
MAP_CONSTANTS_FILE = BASE_DIR / "data/map_constants.asm"

MAP_NAME_OVERRIDES = {
    "OAKS_LAB": "Professor Oak's Laboratory",
    "POKEMON_CENTER": "Pokémon Center",
    "POKEMON_MART": "Pokémon Mart",
}

def load_map_names():
    map_names = {}

    pattern = re.compile(
        r"^\s*map_const\s+([A-Z0-9_]+),.*;\s*\$([0-9A-Fa-f]+)"
    )

    with MAP_CONSTANTS_FILE.open(encoding="utf-8") as file:
        for line in file:
            match = pattern.match(line)

            if not match:
                continue

            name = match.group(1)
            map_id = int(match.group(2), 16)

            readable_name = MAP_NAME_OVERRIDES.get(
                name,
                name.replace("_", " ").title()
            )

            map_names[map_id] = readable_name

    return map_names


MAP_NAMES = load_map_names()


def get_map_name(map_id):
    return MAP_NAMES.get(map_id, f"Unknown location ({map_id})")
