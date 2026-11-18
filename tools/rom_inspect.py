"""Static checks against a Pokémon Yellow ROM (stdlib only, read-only).

Usage:
    python3 tools/rom_inspect.py ROM header
    python3 tools/rom_inspect.py ROM refs 0xD362 0xD05B [--around N]
    python3 tools/rom_inspect.py ROM songs

header  Print title, CGB/SGB flags and SHA-1.
refs    Count direct code references to WRAM addresses (ld a,[nn] / ld [nn],a / ld hl,nn).
        A real variable usually has many; 0 means the address is almost certainly wrong.
        --around N also prints counts for the N addresses on each side.
songs   Find the MapSongBanks table using data/songs.asm and print each
        MUSIC_* constant with its (id, audio bank) as stored in this ROM.
"""

import hashlib
import re
import sys
from pathlib import Path

SONGS_ASM = Path(__file__).resolve().parent.parent / "data/songs.asm"
OPCODES = (0xFA, 0xEA, 0x21)  # ld a,[nn] / ld [nn],a / ld hl,nn


def header(rom):
    title = rom[0x134:0x143].rstrip(b"\x00").decode("ascii", "replace")  # 0x143 is the CGB flag
    print(f"title  {title}")
    print(f"cgb    0x{rom[0x143]:02X}  sgb 0x{rom[0x146]:02X}  cart 0x{rom[0x147]:02X}")
    print(f"size   {len(rom)} bytes")
    print(f"sha1   {hashlib.sha1(rom).hexdigest()}")


def ref_count(rom, address):
    lo, hi = address & 0xFF, address >> 8
    return sum(rom.count(bytes([op, lo, hi])) for op in OPCODES)


def refs(rom, args):
    around = 0
    if "--around" in args:
        i = args.index("--around")
        around = int(args[i + 1])
        args = args[:i] + args[i + 2:]

    for text in args:
        address = int(text, 16)
        counts = [
            f"{a:04X}:{ref_count(rom, a)}"
            for a in range(address - around, address + around + 1)
        ]
        print("  ".join(counts))


def songs(rom):
    symbols = [
        m.group(1)
        for line in SONGS_ASM.open(encoding="utf-8")
        if (m := re.match(r"\s*db\s+(MUSIC_\w+)", line))
    ]

    for start in range(len(rom) - 2 * len(symbols)):
        values, seen = {}, {}
        for k, symbol in enumerate(symbols):
            pair = (rom[start + 2 * k], rom[start + 2 * k + 1])
            if symbol in values:
                if values[symbol] != pair:
                    break
            elif pair in seen:
                break
            else:
                values[symbol] = pair
                seen[pair] = symbol
        else:
            print(f"MapSongBanks at ROM offset 0x{start:X} ({len(symbols)} maps)")
            for symbol, (song_id, bank) in sorted(values.items(), key=lambda t: (t[1][1], t[1][0])):
                print(f"  {symbol:26s} id 0x{song_id:02X} ({song_id:3d})  bank 0x{bank:02X}")
            return

    print("MapSongBanks not found: this ROM's table differs from data/songs.asm")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    rom = Path(sys.argv[1]).expanduser().read_bytes()
    command, args = sys.argv[2], sys.argv[3:]

    if command == "header":
        header(rom)
    elif command == "refs":
        refs(rom, args)
    elif command == "songs":
        songs(rom)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
