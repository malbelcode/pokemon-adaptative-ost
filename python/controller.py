import argparse
import json
import socket
import time
from pathlib import Path

from music_player import MusicPlayer
from music_sources import TrackResolver, load_sources


HOST = "127.0.0.1"
PORT = 8765

BASE_DIR = Path(__file__).resolve().parent.parent

# The Lua script sends a HEARTBEAT every 10 frames (~0.17 s). mGBA stops running
# frames while it is paused, including when "pause when inactive" pauses it in the
# background, so a silence longer than this means the game is not running.
HEARTBEAT_TIMEOUT = 0.5
POLL_INTERVAL = 0.1

MAP_MUSIC_FILE = BASE_DIR / "data/map_music.json"
DEFAULT_LOCATION_TRACK = BASE_DIR / "music/locations/default.wav"

# Canonical track names, resolved inside the selected music source
# (config/music_sources.json).
BATTLE_TRACKS = {
    "WILD_BATTLE": "12 Battle (Wild Pokemon).mp3",
    "TRAINER_BATTLE": "09 Battle (Trainer).mp3",
}

# Keyed by the "trainer_music" field of TRAINER_SPOTTED, which the Lua script
# reads from the song the game starts (MUSIC_MEET_*_TRAINER).
TRAINER_INTRO_TRACKS = {
    "MALE": "17 A Trainer Appears (Boy Version).mp3",
    "FEMALE": "23 A Trainer Appears (Girl Version).mp3",
    "EVIL": "38 A Trainer Appears (Bad Guy Version).mp3",
}

VICTORY_TRACKS = {
    "WILD_BATTLE": "13 Victory (Wild Pokemon).mp3",
    "TRAINER_BATTLE": "10 Victory (Trainer).mp3",
    "GYM_LEADER_BATTLE": "21 Victory (Gym Leader).mp3",
}

class AdaptiveOST:

    def __init__(self, source=None):
        self.tracks = TrackResolver(source)
        print(f"[TRACK] Music source: {self.tracks.source} ({self.tracks.folder.relative_to(BASE_DIR)})")

        self.player = MusicPlayer(volume=50)
        self.current_track = None
        self.current_state = None
        self.current_map = None
        self.last_battle_state = None
        self.victory_playing = False
        self.paused = False
        self.last_message_time = None

        with MAP_MUSIC_FILE.open(encoding="utf-8") as file:
            self.map_music = json.load(file)

        self.player.start()
        self.player.set_track_end_callback(self.on_victory_track_end)

    def on_victory_track_end(self):
        print("[VICTORY] Victory music finished")
        self.victory_playing = False

        if self.current_state == "OVERWORLD":
            self.play_location_music()

    def set_paused(self, paused, reason=""):
        if paused == self.paused:
            return

        self.paused = paused

        if paused:
            print(f"[PAUSE] {reason}. Pausing music")
        else:
            print("[PAUSE] mGBA is running again. Resuming music")

        self.player.set_paused(paused)

    def read_events(self, connection):
        """Handle events from one mGBA connection until it closes.

        Reads with a short timeout so the music can pause when mGBA stops
        sending messages (emulation paused, or paused in the background).
        """
        connection.settimeout(POLL_INTERVAL)
        buffer = b""
        self.last_message_time = time.monotonic()

        while True:
            try:
                data = connection.recv(4096)
            except TimeoutError:
                if time.monotonic() - self.last_message_time > HEARTBEAT_TIMEOUT:
                    self.set_paused(True, "No frames from mGBA (paused or in the background)")
                continue

            if not data:
                return

            self.last_message_time = time.monotonic()
            self.set_paused(False)

            buffer += data
            *lines, buffer = buffer.split(b"\n")

            for raw_line in lines:
                if not raw_line.strip():
                    continue

                line = raw_line.decode("utf-8", errors="replace")

                try:
                    event = json.loads(line)
                except json.JSONDecodeError as error:
                    print(f"[ERROR] {error}")
                    print(f"[ERROR] Received data: {line!r}")
                    print(f"[ERROR] Bytes: {raw_line.hex()}")
                    continue

                self.handle_event(event)

    def play_track(self, track):
        if track is None or track == self.current_track:
            return

        self.player.play(track)
        self.current_track = track

    def play_location_music(self):
        map_entry = self.map_music.get(str(self.current_map))

        track = DEFAULT_LOCATION_TRACK

        if map_entry and map_entry["track"]:
            track = self.tracks.resolve(map_entry["track"]) or DEFAULT_LOCATION_TRACK

        self.play_track(track)

    def handle_event(self, event):
        event_type = event.get("event")

        if event_type == "MAP_CHANGED":
            self.handle_map_changed(event)

        elif event_type == "BATTLE_CHANGED":
            self.handle_battle_changed(event)

        elif event_type == "MUSIC_CHANGED":
            print(f"[MUSIC] ID: {event['music_id']}")

        elif event_type == "VICTORY_STARTED":
            self.handle_victory_started(event)

        elif event_type == "TRAINER_SPOTTED":
            self.handle_trainer_spotted(event)

        elif event_type == "STATE_LOADED":
            self.handle_state_loaded(event)

        elif event_type == "HEARTBEAT":
            pass

        else:
            print(f"[EVENT] Unknown event: {event}")

    def handle_state_loaded(self, event):
        state = event["state"]
        self.current_map = event["map_id"]
        self.current_state = state
        self.victory_playing = False

        map_entry = self.map_music.get(str(self.current_map))
        location = map_entry["name"] if map_entry else f"Unknown location ({self.current_map})"
        print(f"[STATE] Savestate loaded: {location} [ID: {self.current_map}] [{state}]")

        if state in BATTLE_TRACKS:
            self.last_battle_state = state
            self.play_track(self.tracks.resolve(BATTLE_TRACKS[state]))
        else:
            self.last_battle_state = None
            self.play_location_music()

    def handle_trainer_spotted(self, event):
        kind = event.get("trainer_music")
        intro = TRAINER_INTRO_TRACKS.get(kind)

        if intro is None:
            print(f"[TRAINER] Trainer spotted, unknown intro music {kind!r}; keeping current music")
            return

        print(f"[TRAINER] Trainer spotted ({kind}). Playing the trainer intro until the battle starts")

        # Looped like the game does until the battle starts; BATTLE_CHANGED with
        # TRAINER_BATTLE then switches to the battle theme.
        self.play_track(self.tracks.resolve(intro))

    def handle_victory_started(self, event):
        victory_type = event["victory_type"]
        victory_name = VICTORY_TRACKS.get(victory_type)

        if victory_name is None:
            print(f"[VICTORY] Unknown victory type: {victory_type}")
            return

        victory_track = self.tracks.resolve(victory_name)

        if victory_track is None:
            return

        print(f"[VICTORY] Starting {victory_type}")
        self.victory_playing = True
        self.player.play(victory_track, loop=False)
        self.current_track = victory_track

    def handle_map_changed(self, event):
        map_id = event["map_id"]
        self.current_map = map_id

        map_entry = self.map_music.get(str(map_id))
        location = (
            map_entry["name"]
            if map_entry
            else f"Unknown location ({map_id})"
        )

        music_id = map_entry["music_id"] if map_entry else "UNKNOWN"

        print(f"[MAP] {location} [ID: {map_id}] [MUSIC: {music_id}]")

        if self.current_state in (None, "OVERWORLD"):
            self.play_location_music()

    def handle_battle_changed(self, event):
        state = event["state"]
        result = event.get("battle_result", "UNKNOWN")

        print(f"[BATTLE] {state} [RESULT: {result}]")

        self.current_state = state

        if state in BATTLE_TRACKS:
            self.last_battle_state = state
            self.play_track(self.tracks.resolve(BATTLE_TRACKS[state]))

        elif state == "OVERWORLD":
            self.last_battle_state = None
            self.victory_playing = False
            self.play_location_music()

    def close(self):
        self.player.close()


def parse_args():
    default_source, sources = load_sources()

    parser = argparse.ArgumentParser(description="Pokemon Yellow adaptive OST controller")
    parser.add_argument(
        "--source",
        choices=sorted(sources),
        default=default_source,
        help=f"music source to play from (default: {default_source}, set in config/music_sources.json)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    ost = AdaptiveOST(source=args.source)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((HOST, PORT))
            server.listen()

            print("================================")
            print(" Pokemon Adaptive OST")
            print("================================")
            print(f"Listening on {HOST}:{PORT}")
            print("Waiting for mGBA...")

            while True:
                connection, address = server.accept()

                print(f"\n[CONNECTED] mGBA connected from {address}")

                with connection:
                    ost.read_events(connection)

                print("[DISCONNECTED] Waiting for mGBA...")
                ost.set_paused(True, "mGBA disconnected")

    except KeyboardInterrupt:
        print("\n[OST] Shutting down...")

    finally:
        ost.close()


if __name__ == "__main__":
    main()
