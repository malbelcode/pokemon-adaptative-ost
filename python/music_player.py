import json
import socket
import subprocess
import time
import threading
from pathlib import Path


class MusicPlayer:
    SOCKET_PATH = "/tmp/pokemon-adaptive-ost-mpv.sock"

    def __init__(self, volume=70):
        self.volume = volume
        self.process = None
        self.connection = None
        self.reader = None
        self.request_id = 0
        self.event_connection = None
        self.event_thread = None
        self.on_track_end = None

    def start(self):
        """Start MPV in idle mode with IPC enabled."""

        socket_path = Path(self.SOCKET_PATH)

        if socket_path.exists():
            socket_path.unlink()

        self.process = subprocess.Popen([
            "mpv",
            f"--input-ipc-server={self.SOCKET_PATH}",
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
        self.connection.connect(self.SOCKET_PATH)

        self.reader = self.connection.makefile(
            "r",
            encoding="utf-8"
        )
        self.event_connection = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM
        )

        self.event_connection.connect(self.SOCKET_PATH)

        self.event_thread = threading.Thread(
            target=self._listen_for_events,
            daemon=True
        )

        self.event_thread.start()

        print("[MPV] Music player started")

    def send_command(self, command):
        """Send a command and wait for its corresponding response."""

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
                print(f"[MPV] Invalid IPC response: {line!r}")
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
            print(f"[MPV] Track not found: {track}")
            return

        loop_mode = "inf" if loop else "no"
        self.send_command(["set_property", "loop-file", loop_mode])
        self.send_command(["loadfile", str(track), "replace"])

        print(f"[MPV] Playing: {track.name}")

    def stop(self):
        """Stop current playback."""

        self.send_command(["stop"])
        print("[MPV] Playback stopped")

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
                print(f"[MPV] Graceful shutdown failed: {error}")

        if self.process:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("[MPV] Shutdown timed out; terminating process")
                self.process.terminate()
                self.process.wait(timeout=5)

            self.process = None

        if self.reader:
            self.reader.close()