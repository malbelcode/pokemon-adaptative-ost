import math
import struct
import time
import wave

from music_player import MusicPlayer


def generate_test_audio(filename):
    """Generate a short melody as a WAV file."""

    sample_rate = 44100
    notes = [440, 523, 587, 659, 587, 523, 440]
    note_duration = 0.5

    with wave.open(filename, "w") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)

        for frequency in notes:
            for i in range(int(sample_rate * note_duration)):
                t = i / sample_rate

                # Smooth fade at the beginning and end of each note.
                envelope = min(1, i / 500, (sample_rate * note_duration - i) / 500)
                sample = int(
                    16000 * envelope * math.sin(2 * math.pi * frequency * t)
                )

                audio.writeframes(struct.pack("<h", sample))


def main():
    filename = "/tmp/pokemon-ost-test.wav"

    generate_test_audio(filename)

    player = MusicPlayer(volume=50)

    try:
        player.start()

        def on_track_end():
            print("[TEST] Track finished! Callback received.")

        player.set_track_end_callback(on_track_end)
        player.play(filename, loop=False)
        player.play(filename, loop=False)

        print("[TEST] Playing test melody for 5 seconds...")
        time.sleep(5)

    finally:
        player.close()


if __name__ == "__main__":
    main()
