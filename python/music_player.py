import json
import socket
import subprocess
import time
import threading
from pathlib import Path


class MusicPlayer:
    SOCKET_PATH = "/tmp/pokemon-adaptive-ost-mpv.sock"

    def __init__(self, volume=70, socket_path=SOCKET_PATH, name="MPV"):
        self.volume = volume
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

                    if event.get("event") == "end-file":
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
        self.send_command(["set_property", "loop-file", loop_mode])
        self.send_command(["loadfile", str(track), "replace"])

        print(f"[{self.name}] Playing: {track.name}")

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