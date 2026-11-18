import math
import struct
import wave
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent / "music"

SAMPLE_RATE = 22050
NOTE_DURATION = 0.30

TRACKS = {
    "locations/default.wav": [
        523, 659, 784, 659,
        587, 698, 880, 698,
        523, 659, 784, 1047,
        880, 784, 659, 523
    ],
    "battles/wild.wav": [
        784, 784, 880, 784,
        659, 659, 784, 880,
        988, 880, 784, 659,
        784, 880, 988, 1175
    ],
    "battles/trainer.wav": [
        659, 784, 988, 784,
        880, 988, 1175, 988,
        784, 880, 1047, 880,
        988, 1175, 1319, 1175
    ]
}


def generate_track(filename, notes):
    path = BASE_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(path), "w") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)

        for frequency in notes:
            sample_count = int(SAMPLE_RATE * NOTE_DURATION)

            for i in range(sample_count):
                t = i / SAMPLE_RATE

                envelope = min(
                    1.0,
                    i / 300,
                    (sample_count - i) / 500
                )

                # Square-wave chiptune sound
                value = math.sin(2 * math.pi * frequency * t)
                sample = int(10000 * envelope * (1 if value >= 0 else -1))

                audio.writeframes(struct.pack("<h", sample))

    print(f"Generated: {path}")


def main():
    for filename, notes in TRACKS.items():
        generate_track(filename, notes)


if __name__ == "__main__":
    main()
