import argparse
import json
import socket
import time
from collections import namedtuple
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

# Canonical track names, resolved inside the selected music source
# (config/music_sources.json).

# Fallback when wIsInBattle changes but no battle song id was seen.
BATTLE_TRACKS = {
    "WILD_BATTLE": "12 Battle (Wild Pokemon).mp3",
    "TRAINER_BATTLE": "09 Battle (Trainer).mp3",
}

# How a song the game starts is handled:
#   battle   loop; the battle has started (its transition animation)
#   victory  once; the fanfare after a won battle
#   intro    loop; a trainer intro, only right after TRAINER_SPOTTED
#   event    loop; an overworld song that replaces map music until the game changes song
#   jingle   once; a short overworld song, then the map music again
#   evolution  loop; like event, but also while the battle state has not ended yet
# Any other song id in the overworld means the game went back to map music.
#
# Song ids are bank-relative (see docs/ROM_NOTES.md). An id shared with another bank's
# map song is resolved by the current map:
#   only_maps          map symbols where the id means this song
#   unless_map_music   the map song (MUSIC_*) the id means on maps that use it
Song = namedtuple(
    "Song", "constant track kind only_maps unless_map_music", defaults=(None, None)
)

SONGS = {
    # bank 0x08, battle
    0xEA: Song("MUSIC_GYM_LEADER_BATTLE", "20 Battle (Gym Leader).mp3", "battle"),
    0xED: Song("MUSIC_TRAINER_BATTLE", "09 Battle (Trainer).mp3", "battle"),
    0xF0: Song("MUSIC_WILD_BATTLE", "12 Battle (Wild Pokemon).mp3", "battle"),
    0xF3: Song("MUSIC_FINAL_BATTLE", "45 Final Battle (Rival).mp3", "battle", only_maps={"CHAMPIONS_ROOM"}),  # also MUSIC_ROUTES3
    0xF6: Song("MUSIC_DEFEATED_TRAINER", "10 Victory (Trainer).mp3", "victory"),
    0xF9: Song("MUSIC_DEFEATED_WILD_MON", "13 Victory (Wild Pokemon).mp3", "victory"),
    0xFC: Song("MUSIC_DEFEATED_GYM_LEADER", "21 Victory (Gym Leader).mp3", "victory"),
    # bank 0x1F
    0xC3: Song("MUSIC_TITLE_SCREEN", "04 Title Screen.mp3", "event", unless_map_music="MUSIC_CITIES1"),
    0xC7: Song("MUSIC_CREDITS", "47 Ending Theme.mp3", "event", only_maps={"HALL_OF_FAME"}),  # also MUSIC_CITIES2
    0xCA: Song("MUSIC_HALL_OF_FAME", "46 Hall of Fame.mp3", "event", only_maps={"HALL_OF_FAME"}),  # also MUSIC_CELADON
    0xD0: Song("MUSIC_JIGGLYPUFF_SONG", "57 Jigglypuff's Song.mp3", "jingle", unless_map_music="MUSIC_VERMILION"),
    0xDC: Song("MUSIC_YELLOW_INTRO", "02 Opening Movie.mp3", "event"),
    0xD2: Song("MUSIC_BIKE_RIDING", "31 Cycling.mp3", "event"),
    0xD6: Song("MUSIC_SURFING", "41 The Sea.mp3", "event"),
    0xF5: Song("MUSIC_MEET_EVIL_TRAINER", "38 A Trainer Appears (Bad Guy Version).mp3", "intro"),
    0xF8: Song("MUSIC_MEET_FEMALE_TRAINER", "23 A Trainer Appears (Girl Version).mp3", "intro"),
    0xFB: Song("MUSIC_MEET_MALE_TRAINER", "17 A Trainer Appears (Boy Version).mp3", "intro"),  # also MUSIC_INDIGO_PLATEAU
    # bank 0x02
    0xDB: Song("MUSIC_MEET_PROF_OAK", "06 Professor Oak.mp3", "event"),
    0xDE: Song("MUSIC_MEET_RIVAL", "08 A Rival Appears.mp3", "event"),
    0xE1: Song("MUSIC_MUSEUM_GUY", "18 Guide.mp3", "event"),
    0xE5: Song("MUSIC_SAFARI_ZONE", "28 Evolution.mp3", "evolution", unless_map_music="MUSIC_SAFARI_ZONE"),  # the evolution song
    0xE8: Song("MUSIC_PKMN_HEALED", "56 Pokemon Recovery.mp3", "jingle"),
    # bank 0x20 (AUDIO_4, Yellow only)
    0x99: Song("MUSIC_SURFING_PIKACHU", "39 Pikachu's Beach.mp3", "event"),
    0x9C: Song("MUSIC_MEET_JESSIE_JAMES", "25 Theme of Jessie and James.mp3", "event"),
}

# Fanfares are sound effects (channels 4-7), so their ids are keyed by
# (wAudioROMBank, sound id): 0x86 is the item fanfare in the overworld banks and the
# level-up fanfare in the battle bank 0x08. While one plays, the game pauses the music
# channels under it; the music track pauses too and resumes when the game's sound ends
# (or the recording does). Oak's Pokedex rating plays them too, from fixed banks.
Fanfare = namedtuple("Fanfare", "constant track")

FANFARES = {
    (bank, sound_id): fanfare
    for fanfare, keys in [
        (Fanfare("SFX_GET_ITEM_1", "60 Item Fanfare.mp3"), [(0x02, 0x86), (0x1F, 0x86), (0x20, 0x86)]),
        (Fanfare("SFX_GET_ITEM_2", "61 Hidden Item Fanfare.mp3"),
         [(0x02, 0x89), (0x08, 0x89), (0x1F, 0x89), (0x20, 0x89), (0x20, 0x96)]),  # 0x96: SFX_GET_ITEM2_4_2
        (Fanfare("SFX_GET_KEY_ITEM", "63 Key Item Fanfare.mp3"), [(0x02, 0x94), (0x1F, 0x94)]),
        (Fanfare("SFX_POKEDEX_RATING", "62 Pokedex Rating Fanfare.mp3"), [(0x02, 0x91), (0x1F, 0x91)]),
        (Fanfare("SFX_LEVEL_UP", "58 Level Up Fanfare.mp3"), [(0x08, 0x86)]),
        (Fanfare("SFX_CAUGHT_MON", "59 Pokemon Caught Fanfare.mp3"), [(0x08, 0x9A)]),
    ]
    for bank, sound_id in keys
}

FANFARE_SOCKET_PATH = "/tmp/pokemon-adaptive-ost-mpv-fanfare.sock"

# Seconds for each volume ramp when the music switches track. Fanfares start hard,
# as in the game.
MUSIC_FADE = 0.25

# A trainer intro song counts only this long after (or before) TRAINER_SPOTTED.
TRAINER_INTRO_WINDOW = 3.0


class AdaptiveOST:

    def __init__(self, source=None):
        self.tracks = TrackResolver(source)
        print(f"[TRACK] Music source: {self.tracks.source} ({self.tracks.folder.relative_to(BASE_DIR)})")

        # Track switches fade out and back in instead of cutting hard.
        self.player = MusicPlayer(volume=50, fade=MUSIC_FADE)
        # Fanfares play in a second mpv, so the music keeps its position under them.
        self.fanfare_player = MusicPlayer(volume=50, socket_path=FANFARE_SOCKET_PATH, name="FANFARE")
        self.current_track = None
        self.current_state = None
        self.current_map = None
        self.paused = False
        self.last_message_time = None
        # True from the battle song (transition animation) until back in the overworld,
        # so BATTLE_CHANGED does not replace it and map songs are ignored meanwhile.
        self.battle_music_started = False
        self.victory_playing = False
        # The overworld Song (intro, event or jingle) currently replacing map music.
        self.song_override = None
        self.last_song_id = None
        self.last_song_time = None
        self.trainer_spotted_time = None
        # (bank, sound id) of the fanfare the game is playing, or None.
        self.fanfare = None

        with MAP_MUSIC_FILE.open(encoding="utf-8") as file:
            self.map_music = json.load(file)

        self.player.start()
        self.player.set_track_end_callback(self.on_track_end)
        self.fanfare_player.start()
        self.fanfare_player.set_track_end_callback(self.on_fanfare_end)

    def on_track_end(self):
        """Called from the mpv event thread when a track played once (loop=no) ends."""
        if self.victory_playing:
            print("[VICTORY] Victory music finished")
            self.victory_playing = False
        elif self.song_override and self.song_override.kind == "jingle":
            print(f"[MUSIC] {self.song_override.constant} finished")
            self.song_override = None
        else:
            return

        if self.in_overworld():
            self.play_location_music()

    def on_fanfare_end(self):
        """Called from the fanfare mpv's event thread when the recording ends."""
        self.end_fanfare("recording finished")

    def in_overworld(self):
        return self.current_state in (None, "OVERWORLD") and not self.battle_music_started

    def map_entry(self):
        return self.map_music.get(str(self.current_map)) or {}

    def set_paused(self, paused, reason=""):
        if paused == self.paused:
            return

        self.paused = paused

        if paused:
            print(f"[PAUSE] {reason}. Pausing music")
        else:
            print("[PAUSE] mGBA is running again. Resuming music")

        self.update_pause()

    def update_pause(self):
        """The music pauses while mGBA is paused or a fanfare plays over it."""
        self.player.set_paused(self.paused or self.fanfare is not None)
        self.fanfare_player.set_paused(self.paused)

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
        name = self.map_entry().get("track")
        track = self.tracks.resolve(name) if name else None

        if track is None:
            print(f"[MAP] No track for map {self.current_map}. Keeping the current music")
            return

        self.play_track(track)

    def handle_event(self, event):
        event_type = event.get("event")

        if event_type == "MAP_CHANGED":
            self.handle_map_changed(event)

        elif event_type == "BATTLE_CHANGED":
            self.handle_battle_changed(event)

        elif event_type == "MUSIC_CHANGED":
            self.handle_music_changed(event)

        elif event_type == "SFX_CHANGED":
            self.handle_sfx_changed(event)

        elif event_type == "TRAINER_SPOTTED":
            self.handle_trainer_spotted()

        elif event_type == "STATE_LOADED":
            self.handle_state_loaded(event)

        elif event_type == "HEARTBEAT":
            pass

        else:
            print(f"[EVENT] Unknown event: {event}")

    def identify_song(self, song_id):
        """Return the Song for an id the game started, or None for map music."""
        song = SONGS.get(song_id)

        if song is None:
            return None

        map_entry = self.map_entry()

        if song.only_maps and map_entry.get("symbol") not in song.only_maps:
            return None

        if song.unless_map_music and map_entry.get("music_id") == song.unless_map_music:
            return None

        if song.kind == "intro":
            spotted = self.trainer_spotted_time
            if spotted is None or abs(time.monotonic() - spotted) > TRAINER_INTRO_WINDOW:
                return None  # 0xFB outside the window is MUSIC_INDIGO_PLATEAU

        return song

    def handle_music_changed(self, event):
        song_id = event["music_id"]

        if song_id == self.last_song_id:
            return

        self.last_song_id = song_id
        self.last_song_time = time.monotonic()
        self.play_song(song_id)

    def play_song(self, song_id):
        song = self.identify_song(song_id)
        label = song.constant if song else "map music"
        print(f"[MUSIC] Game started song {song_id:#04x} ({label})")

        if song is None:
            # The game went back to map music (or started a song with no track here).
            jingle_playing = self.song_override and self.song_override.kind == "jingle"
            if self.in_overworld() and not jingle_playing:
                self.song_override = None
                self.play_location_music()
            return

        track = self.tracks.resolve(song.track)

        if song.kind == "battle":
            print(f"[BATTLE] Battle music: {song.constant}")
            self.battle_music_started = True
            self.victory_playing = False
            self.song_override = None
            self.play_track(track)

        elif song.kind == "victory":
            if track is None:
                return
            print(f"[VICTORY] Starting {song.constant}")
            self.victory_playing = True
            self.player.play(track, loop=False)
            self.current_track = track

        elif track is not None and (self.in_overworld() or song.kind == "evolution"):
            if song.kind == "intro":
                print(f"[TRAINER] Trainer intro: {song.constant}. Playing it until the battle starts")

            self.song_override = song

            if song.kind == "jingle":
                self.player.play(track, loop=False)
                self.current_track = track
            else:
                self.play_track(track)

    def handle_sfx_changed(self, event):
        key = (event["bank"], event["sound_id"])

        if key == self.fanfare:
            return

        # Any other sound on the channel means the game's fanfare ended (or was cut).
        self.end_fanfare("the game's sound effect ended")

        fanfare = FANFARES.get(key)
        track = self.tracks.resolve(fanfare.track) if fanfare else None

        if track is None:
            return

        print(f"[FANFARE] {fanfare.constant} (bank {key[0]:#04x}, id {key[1]:#04x}). Pausing the music under it")
        self.fanfare = key
        self.update_pause()
        self.fanfare_player.play(track, loop=False)

    def end_fanfare(self, reason):
        if self.fanfare is None:
            return

        print(f"[FANFARE] {FANFARES[self.fanfare].constant} done ({reason}). Resuming the music")
        self.fanfare = None
        self.update_pause()

    def handle_trainer_spotted(self):
        print("[TRAINER] Trainer spotted")
        self.trainer_spotted_time = time.monotonic()

        # The intro song may have started a moment before the spotted flag.
        last = SONGS.get(self.last_song_id)
        if last and last.kind == "intro" and time.monotonic() - self.last_song_time <= TRAINER_INTRO_WINDOW:
            self.play_song(self.last_song_id)

    def handle_state_loaded(self, event):
        state = event["state"]
        self.current_map = event["map_id"]
        self.current_state = state
        self.victory_playing = False
        self.battle_music_started = False
        self.song_override = None
        # The Lua script re-reports the current song and sound on the next frame.
        self.last_song_id = None

        if self.fanfare is not None:
            self.fanfare = None
            self.fanfare_player.stop()
            self.update_pause()

        location = self.map_entry().get("name", f"Unknown location ({self.current_map})")
        print(f"[STATE] Savestate loaded: {location} [ID: {self.current_map}] [{state}]")

        if state in BATTLE_TRACKS:
            self.play_track(self.tracks.resolve(BATTLE_TRACKS[state]))
        else:
            self.play_location_music()

    def handle_map_changed(self, event):
        self.current_map = event["map_id"]

        map_entry = self.map_entry()
        location = map_entry.get("name", f"Unknown location ({self.current_map})")
        music_id = map_entry.get("music_id", "UNKNOWN")

        print(f"[MAP] {location} [ID: {self.current_map}] [MUSIC: {music_id}]")

        # While an overworld song (bike, surf, intro...) plays, the game keeps it
        # across maps; if it switches back to map music, MUSIC_CHANGED says so.
        if self.in_overworld() and self.song_override is None:
            self.play_location_music()

    def handle_battle_changed(self, event):
        state = event["state"]
        result = event.get("battle_result", "UNKNOWN")

        print(f"[BATTLE] {state} [RESULT: {result}]")

        self.current_state = state

        if state in BATTLE_TRACKS:
            self.song_override = None

            # Normally the battle music already started with the transition
            # animation (MUSIC_CHANGED with a battle song). This is the fallback.
            if not self.battle_music_started:
                self.play_track(self.tracks.resolve(BATTLE_TRACKS[state]))

        elif state == "OVERWORLD":
            self.victory_playing = False
            self.battle_music_started = False
            self.song_override = None
            self.play_location_music()

    def close(self):
        self.player.close()
        self.fanfare_player.close()


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
