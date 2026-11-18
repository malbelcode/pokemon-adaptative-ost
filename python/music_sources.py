"""Music sources: interchangeable folders that use the same canonical file names.

config/music_sources.json maps a source name to a folder under the project root.
Every folder names the same song the same way (for example "05 Pallet Town.mp3";
see tools/normalize_music.py), so switching sources only changes the folder.
"""
import json
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SOURCES_FILE = BASE_DIR / "config/music_sources.json"


def load_sources():
    """Return (default source name, {source name: folder Path})."""
    with SOURCES_FILE.open(encoding="utf-8") as file:
        config = json.load(file)

    sources = {
        name: BASE_DIR / folder
        for name, folder in config["sources"].items()
    }

    if config["default"] not in sources:
        raise ValueError(
            f"Default music source {config['default']!r} is not listed in {SOURCES_FILE}"
        )

    return config["default"], sources


def find_track(folder, name):
    """Return the path of `name` in `folder`, or None. Ignores Unicode normalization."""
    path = folder / name

    if path.is_file():
        return path

    wanted = unicodedata.normalize("NFC", name)

    if folder.is_dir():
        for entry in folder.iterdir():
            if entry.is_file() and unicodedata.normalize("NFC", entry.name) == wanted:
                return entry

    return None


class TrackResolver:
    """Turn canonical track names into files in the selected source.

    A track missing from the selected source falls back to the other sources,
    in the order they are listed in the config.
    """

    def __init__(self, source=None):
        default, self.sources = load_sources()
        self.source = source or default

        if self.source not in self.sources:
            raise ValueError(
                f"Unknown music source {self.source!r}. "
                f"Choose one of: {', '.join(self.sources)}"
            )

        self.order = [self.source] + [n for n in self.sources if n != self.source]
        self._cache = {}

    @property
    def folder(self):
        return self.sources[self.source]

    def resolve(self, name):
        if name in self._cache:
            return self._cache[name]

        path = None

        for source in self.order:
            path = find_track(self.sources[source], name)

            if path:
                if source != self.source:
                    print(f"[TRACK] {name!r} is not in {self.source}, using {source}")
                break
        else:
            print(f"[TRACK] {name!r} is missing from every music source")

        self._cache[name] = path
        return path
