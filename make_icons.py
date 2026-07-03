import struct, zlib, os

def make_icon(size, path):
    w = h = size
    rows = []
    # Colors: dark bg (#1a1d27), purple border (#6c72cb)
    bg = bytes([26, 29, 39])
    border_color = bytes([108, 114, 203])
    border_w = max(2, int(size * 0.06))
    corner_r = int(size * 0.18)

    for y in range(h):
        row = b'\x00'  # filter byte
        for x in range(w):
            # Rounded corners check
            in_corner_zone = (x < corner_r and y < corner_r) or \
                             (x >= w - corner_r and y < corner_r) or \
                             (x < corner_r and y >= h - corner_r) or \
                             (x >= w - corner_r and y >= h - corner_r)

            # Check if in border (with rounded corners)
            is_border = False
            if x < border_w or x >= w - border_w or y < border_w or y >= h - border_w:
                if in_corner_zone:
                    # Distance from corner center
                    cx = corner_r if x < w // 2 else w - corner_r - 1
                    cy = corner_r if y < h // 2 else h - corner_r - 1
                    dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                    if dist <= corner_r:
                        is_border = True
                else:
                    is_border = True

            row += (border_color if is_border else bg)
        rows.append(row)

    raw = b''.join(rows)
    compressed = zlib.compress(raw)

    def chunk(ctype, data):
        c = ctype + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)

    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', ihdr)
    png += chunk(b'IDAT', compressed)
    png += chunk(b'IEND', b'')

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(png)
    print(f"Created {path} ({os.path.getsize(path)} bytes)")

make_icon(192, 'mobile-app/icon-192.png')
make_icon(512, 'mobile-app/icon-512.png')
print("Done!")
