"""Build the original bicycle icon with the standard library; no image dependencies."""
import math
from pathlib import Path
import struct
import zlib


def build():
    size = 256
    teal, paper = (6, 82, 92), (247, 249, 248)
    segments = [(66, 151, 104, 88), (104, 88, 143, 151), (66, 151, 143, 151),
                (104, 88, 173, 88), (173, 88, 191, 151), (143, 151, 173, 88),
                (88, 88, 118, 88), (165, 70, 181, 70), (181, 70, 181, 87)]

    def distance(x, y, seg):
        a, b, c, d = seg
        t = max(0, min(1, ((x-a)*(c-a)+(y-b)*(d-b))/((c-a)**2+(d-b)**2)))
        return math.hypot(x-a-t*(c-a), y-b-t*(d-b))

    rows = []
    for y in range(size):
        row = bytearray(b"\0")
        for x in range(size):
            coverage = 0
            for dx, dy in ((.25, .25), (.75, .25), (.25, .75), (.75, .75)):
                px, py = x+dx, y+dy
                wheels = min(abs(math.hypot(px-66, py-151)-41), abs(math.hypot(px-191, py-151)-41))
                if wheels < 3.4 or any(distance(px, py, s) < 3.4 for s in segments):
                    coverage += 1
            rgb = tuple(round(a+(b-a)*coverage/4) for a, b in zip(teal, paper))
            row.extend((*rgb, 255))
        rows.append(row)

    def chunk(name, data):
        return struct.pack(">I", len(data))+name+data+struct.pack(">I", zlib.crc32(name+data)&0xffffffff)
    png = b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))+chunk(b"IDAT", zlib.compress(b"".join(rows), 9))+chunk(b"IEND", b"")
    assets = Path(__file__).parent / "assets"
    assets.mkdir(exist_ok=True)
    (assets / "app.png").write_bytes(png)
    (assets / "app.ico").write_bytes(struct.pack("<HHH", 0, 1, 1)+struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22)+png)


if __name__ == "__main__":
    build()
