import json
import socket
import subprocess
import time
import threading
from pathlib import Path


class MusicPlayer:
    SOCKET_PATH = "/tmp/pokemon-adaptive-ost-mpv.sock"
    # Time between volume steps while fading.
    FADE_STEP = 0.02
    # How long to wait for a new file to start playing before fading it in anyway.
    START_TIMEOUT = 1.0

    def __init__(self, volume=70, socket_path=SOCKET_PATH, name="MPV", fade=0.0):
        self.volume = volume
        # Seconds for each volume ramp on a track switch (out, then in). 0 cuts hard.
        self.fade = fade
        self.socket_path = socket_path
        # Log tag, so a second player (fanfares) is told apart from the music.
        self.name = name
        self.paused = False
        self.process = None
        self.connection = None
        self.reader = None
        self.request_id = 0
        self.event_connection = None
        self.event_thread = None
        self.on_track_end = None
        # send_command is called from the controller thread and from the mpv event
        # thread (track-end callback), so request/response pairs must not interleave.
        self.command_lock = threading.Lock()
        # A track switch (fade out, load, fade in) is one step: two switches from
        # different threads must not interleave their volume ramps.
        self.play_lock = threading.RLock()
        # Set by the event thread when a newly loaded file starts playing.
        self.playback_started = threading.Event()
        self.loading_file = False

    def start(self):
        """Start MPV in idle mode with IPC enabled."""

        socket_path = Path(self.socket_path)

        if socket_path.exists():
            socket_path.unlink()

        self.process = subprocess.Popen([
            "mpv",
            f"--input-ipc-server={self.socket_path}",
            "--no-video",
            "--idle=yes",
            "--loop-file=inf",
            "--force-window=no",
            "--volume=" + str(self.volume)
        ])

        # Wait for MPV to create its IPC socket.
        for _ in range(50):
            if socket_path.exists():
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("MPV IPC socket was not created")

        self.connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.connection.settimeout(2)
        self.connection.connect(self.socket_path)

        self.reader = self.connection.makefile(
            "r",
            encoding="utf-8"
        )
        self.event_connection = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM
        )

        self.event_connection.connect(self.socket_path)

        self.event_thread = threading.Thread(
            target=self._listen_for_events,
            daemon=True
        )

        self.event_thread.start()

        print(f"[{self.name}] Player started")

    def send_command(self, command):
        """Send a command and wait for its corresponding response."""

        with self.command_lock:
            return self._send_command(command)

    def _send_command(self, command):
        if not self.connection:
            raise RuntimeError("MPV is not connected")

        self.request_id += 1
        request_id = self.request_id

        message = {
            "command": command,
            "request_id": request_id
        }

        self.connection.sendall(
            (json.dumps(message) + "\n").encode("utf-8")
        )

        while True:
            line = self.reader.readline()

            if not line:
                raise ConnectionError("MPV closed the IPC connection")

            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                print(f"[{self.name}] Invalid IPC response: {line!r}")
                continue

            # Ignore asynchronous notifications.
            if "request_id" not in response:
                continue

            # Ignore responses to other requests.
            if response["request_id"] != request_id:
                continue

            if response.get("error") != "success":
                raise RuntimeError(f"MPV error: {response}")

            return response

    def _listen_for_events(self):
        """Listen for MPV playback events."""

        buffer = ""

        while self.event_connection:
            try:
                data = self.event_connection.recv(4096)

                if not data:
                    break

                buffer += data.decode("utf-8")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)

                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    name = event.get("event")

                    if name == "start-file":
                        self.loading_file = True
                    elif name == "playback-restart" and self.loading_file:
                        # Also sent after seeks (loop-file); only the first one
                        # after start-file means the new track is audible.
                        self.loading_file = False
                        self.playback_started.set()

                    if name == "end-file":
                        reason = event.get("reason")

                        if reason == "eof" and self.on_track_end:
                            self.on_track_end()

            except OSError:
                break

    def set_track_end_callback(self, callback):
        self.on_track_end = callback

    def play(self, track, loop=True):
        """Play a music file, optionally looping it."""

        track = Path(track).resolve()

        if not track.is_file():
            print(f"[{self.name}] Track not found: {track}")
            return

        loop_mode = "inf" if loop else "no"

        with self.play_lock:
            # Paused music is silent, so there is nothing to fade.
            fading = self.fade > 0 and not self.paused

            if fading:
                if self._is_playing():
                    self._ramp_volume(self.volume, 0)
                else:
                    self.send_command(["set_property", "volume", 0])

            self.playback_started.clear()
            self.send_command(["set_property", "loop-file", loop_mode])
            self.send_command(["loadfile", str(track), "replace"])

            if fading:
                self._wait_for_playback()
                self._ramp_volume(0, self.volume)

        print(f"[{self.name}] Playing: {track.name}")

    def _is_playing(self):
        """True while a file is loaded (mpv is not idle)."""

        response = self.send_command(["get_property", "idle-active"])
        return not response.get("data")

    def _wait_for_playback(self):
        """Wait until the file just loaded is playing, so the fade-in is heard.

        The event thread sets the flag, so it cannot wait for itself: when it starts
        a track (track-end callback) the fade-in simply starts right away.
        """

        if threading.current_thread() is self.event_thread:
            return

        if not self.playback_started.wait(self.START_TIMEOUT):
            print(f"[{self.name}] Track did not start within {self.START_TIMEOUT} s; fading in anyway")

    def _ramp_volume(self, start, end):
        """Move the mpv volume from start to end over self.fade seconds."""

        steps = max(1, round(self.fade / self.FADE_STEP))

        for step in range(1, steps + 1):
            volume = start + (end - start) * step / steps
            self.send_command(["set_property", "volume", volume])

            if step < steps:
                time.sleep(self.FADE_STEP)

    def set_paused(self, paused):
        """Pause or resume playback, keeping the current position.

        mpv keeps the pause state across loadfile, so a track loaded while paused
        waits until playback is resumed.
        """

        if paused == self.paused:
            return

        self.paused = paused
        self.send_command(["set_property", "pause", paused])
        print(f"[{self.name}] Paused" if paused else f"[{self.name}] Resumed")

    def stop(self):
        """Stop current playback."""

        self.send_command(["stop"])
        print(f"[{self.name}] Playback stopped")

    def set_volume(self, volume):
        """Change playback volume."""

        with self.play_lock:
            self.volume = max(0, min(100, volume))
            self.send_command(["set_property", "volume", self.volume])

    def close(self):
        if self.event_connection:
            self.event_connection.close()
            self.event_connection = None
        """Shut down MPV gracefully."""

        if self.connection:
            try:
                self.send_command(["quit"])
            except (ConnectionError, OSError, RuntimeError, TimeoutError) as error:
                print(f"[{self.name}] Graceful shutdown failed: {error}")

        if self.process:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(f"[{self.name}] Shutdown timed out; terminating process")
                self.process.terminate()
                self.process.wait(timeout=5)

            self.process = None

        if self.reader:
            self.reader.close()