import json
import socket
from pathlib import Path

from music_player import MusicPlayer


HOST = "127.0.0.1"
PORT = 8765

BASE_DIR = Path(__file__).resolve().parent.parent

MAP_MUSIC_FILE = BASE_DIR / "data/map_music.json"
DEFAULT_LOCATION_TRACK = BASE_DIR / "music/locations/default.wav"

BATTLE_TRACKS = {
    "WILD_BATTLE": BASE_DIR / "music/battles/wild.mp3",
    "TRAINER_BATTLE": BASE_DIR / "music/battles/trainer.mp3",
}

VICTORY_TRACKS = {
    "WILD_BATTLE": BASE_DIR / "music/Pokemon Yellow (MP3).zophar/28 Victory (VS Wild Pokemon).mp3",
    "TRAINER_BATTLE": BASE_DIR / "music/Pokemon Yellow (MP3).zophar/27 Victory (VS Trainer).mp3",
    "GYM_LEADER_BATTLE": BASE_DIR / "music/Pokemon Yellow (MP3).zophar/29 Victory (VS Gym Leader).mp3"
}

class AdaptiveOST:

    def __init__(self):
        self.player = MusicPlayer(volume=50)
        self.current_track = None
        self.current_state = None
        self.current_map = None
        self.last_battle_state = None
        self.victory_playing = False

        with MAP_MUSIC_FILE.open(encoding="utf-8") as file:
            self.map_music = json.load(file)

        self.player.start()
        self.player.set_track_end_callback(self.on_victory_track_end)

    def on_victory_track_end(self):
        print("[VICTORY] Victory music finished")
        self.victory_playing = False

        if self.current_state == "OVERWORLD":
            self.play_location_music()

    def play_track(self, track):
        if track == self.current_track:
            return

        self.player.play(track)
        self.current_track = track

    def play_location_music(self):
        map_entry = self.map_music.get(str(self.current_map))

        track = DEFAULT_LOCATION_TRACK

        if map_entry and map_entry["track"]:
            track = BASE_DIR / map_entry["track"]

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
            self.handle_trainer_spotted()

        elif event_type == "STATE_LOADED":
            self.handle_state_loaded(event)

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
            self.play_track(BATTLE_TRACKS[state])
        else:
            self.last_battle_state = None
            self.play_location_music()

    def handle_trainer_spotted(self):
        print("[TRAINER] Trainer spotted! Starting trainer music")

        self.play_track(BATTLE_TRACKS["TRAINER_BATTLE"])

    def handle_victory_started(self, event):
        victory_type = event["victory_type"]
        victory_track = VICTORY_TRACKS.get(victory_type)

        if victory_track is None:
            print(f"[VICTORY] Unknown victory type: {victory_type}")
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
            self.play_track(BATTLE_TRACKS[state])

        elif state == "OVERWORLD":
            self.last_battle_state = None
            self.victory_playing = False
            self.play_location_music()

    def close(self):
        self.player.close()


def main():
    ost = AdaptiveOST()

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
                    stream = connection.makefile("r", encoding="utf-8")

                    for line in stream:
                        try:
                            event = json.loads(line)
                            ost.handle_event(event)

                        except json.JSONDecodeError as error:
                            print(f"[ERROR] {error}")
                            print(f"[ERROR] Received data: {line!r}")
                            print(f"[ERROR] Bytes: {line.encode('utf-8').hex()}")

                print("[DISCONNECTED] Waiting for mGBA...")

    except KeyboardInterrupt:
        print("\n[OST] Shutting down...")

    finally:
        ost.close()


if __name__ == "__main__":
    main()
