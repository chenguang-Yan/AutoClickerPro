# -*- coding: utf-8 -*-
"""生成科技感应用图标 app.ico（纯标准库，64x64 BGRA）"""
import math
import struct
import os

SIZE = 64
SS = 3  # 超采样倍数


def color_at(px, py):
    cx = cy = SIZE / 2.0
    r = 14  # 圆角半径
    # 圆角矩形遮罩
    x, y = px, py
    inside = True
    if x < r and y < r:
        inside = (x - r) ** 2 + (y - r) ** 2 <= r * r
    elif x > SIZE - r and y < r:
        inside = (x - (SIZE - r)) ** 2 + (y - r) ** 2 <= r * r
    elif x < r and y > SIZE - r:
        inside = (x - r) ** 2 + (y - (SIZE - r)) ** 2 <= r * r
    elif x > SIZE - r and y > SIZE - r:
        inside = (x - (SIZE - r)) ** 2 + (y - (SIZE - r)) ** 2 <= r * r
    if not inside:
        return (0, 0, 0, 0)

    # 背景渐变（左上偏亮）
    t = (x + y) / (2.0 * SIZE)
    bg = (int(8 + 10 * (1 - t)), int(13 + 16 * (1 - t)), int(20 + 24 * (1 - t)), 255)

    d = math.hypot(x - cx, y - cy)
    rings = [(25.0, 2.0, (0, 90, 110)), (18.0, 2.4, (0, 140, 170)), (10.5, 2.6, (0, 229, 255))]
    for rr, w, col in rings:
        if abs(d - rr) <= w / 2.0 + 0.4:
            edge = 1.0 - (abs(d - rr) / (w / 2.0 + 0.4)) * 0.35
            return (int(col[0] * edge), int(col[1] * edge), int(col[2] * edge), 255)
    if d <= 5.2:
        return (0, 229, 255, 255)
    if d <= 7.0:
        return (int(0 * 0.4), int(229 * 0.4), int(255 * 0.4), 255)
    return bg


rows = []
for y in range(SIZE - 1, -1, -1):  # ICO/BMP 自下而上
    row = bytearray()
    for x in range(SIZE):
        acc = [0, 0, 0, 0]
        for sy in range(SS):
            for sx in range(SS):
                c = color_at(x + (sx + 0.5) / SS, y + (sy + 0.5) / SS)
                for i in range(4):
                    acc[i] += c[i]
        n = SS * SS
        r, g, b, a = [int(v / n) for v in acc]
        row += bytes((b, g, r, a))
    rows.append(bytes(row))
xor_data = b"".join(rows)

mask_row_bytes = ((SIZE + 31) // 32) * 4
and_data = bytes(mask_row_bytes * SIZE)

bih = struct.pack("<IiiHHIIiiII", 40, SIZE, SIZE * 2, 1, 32, 0,
                  len(xor_data) + len(and_data), 0, 0, 0, 0)
image = bih + xor_data + and_data

ico = struct.pack("<HHH", 0, 1, 1)
ico += struct.pack("<BBBBHHII", SIZE, SIZE, 0, 0, 1, 32, len(image), 22)
ico += image

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
with open(out, "wb") as f:
    f.write(ico)
print("wrote", out, len(ico), "bytes")
