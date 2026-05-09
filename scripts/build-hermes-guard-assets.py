#!/usr/bin/env python3
"""Build Hermes guard stop/control assets for packaged companion pets.

The generated assets intentionally use only the Python standard library so the
release pipeline does not depend on Pillow, ImageMagick, or local editor state.
"""

from __future__ import annotations

import argparse
import struct
import zlib
from collections import deque
from pathlib import Path


PETS = ("koda", "miko", "bramble", "nyx", "pip", "atlas")
RUNUP_FRAME_COUNT = 6
RUNUP_FRAME_WIDTH = 362
RUNUP_FRAME_HEIGHT = 724
STOP_REFERENCE_NAMES = {
    "koda": "Koda stop sign.png",
    "miko": "Miko stop sign.png",
    "bramble": "Bramble stop sign.png",
    "nyx": "Nyx stop sign.png",
    "pip": "pip stop sign.png",
    "atlas": "atlas stop sign.png",
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PngError(RuntimeError):
    pass


class Image:
    def __init__(self, width: int, height: int, pixels: bytearray) -> None:
        self.width = width
        self.height = height
        self.pixels = pixels

    def offset(self, x: int, y: int) -> int:
        return (y * self.width + x) * 4

    def pixel(self, x: int, y: int) -> tuple[int, int, int, int]:
        index = self.offset(x, y)
        return tuple(self.pixels[index:index + 4])  # type: ignore[return-value]

    def set_pixel(self, x: int, y: int, pixel: tuple[int, int, int, int]) -> None:
        index = self.offset(x, y)
        self.pixels[index:index + 4] = bytes(pixel)


def paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def read_png(path: Path) -> Image:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise PngError(f"{path} is not a PNG")

    pos = len(PNG_SIGNATURE)
    width = height = bit_depth = color_type = None
    compressed = bytearray()
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        chunk_type = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += length + 12
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, compression, png_filter, interlace = struct.unpack(">IIBBBBB", chunk)
            if bit_depth != 8 or color_type not in (2, 6) or compression != 0 or png_filter != 0 or interlace != 0:
                raise PngError(f"{path} uses unsupported PNG format")
        elif chunk_type == b"IDAT":
            compressed.extend(chunk)
        elif chunk_type == b"IEND":
            break

    if width is None or height is None or color_type is None:
        raise PngError(f"{path} has no IHDR")

    channels = 4 if color_type == 6 else 3
    stride = width * channels
    raw = zlib.decompress(bytes(compressed))
    pixels = bytearray(width * height * 4)
    raw_pos = 0
    previous = [0] * stride
    for y in range(height):
        filter_type = raw[raw_pos]
        raw_pos += 1
        encoded = list(raw[raw_pos:raw_pos + stride])
        raw_pos += stride
        row = [0] * stride
        for x in range(stride):
            left = row[x - channels] if x >= channels else 0
            up = previous[x]
            up_left = previous[x - channels] if x >= channels else 0
            value = encoded[x]
            if filter_type == 0:
                decoded = value
            elif filter_type == 1:
                decoded = value + left
            elif filter_type == 2:
                decoded = value + up
            elif filter_type == 3:
                decoded = value + ((left + up) // 2)
            elif filter_type == 4:
                decoded = value + paeth(left, up, up_left)
            else:
                raise PngError(f"{path} has unsupported PNG filter {filter_type}")
            row[x] = decoded & 255
        previous = row
        for x in range(width):
            source = x * channels
            dest = (y * width + x) * 4
            pixels[dest:dest + 3] = bytes(row[source:source + 3])
            pixels[dest + 3] = row[source + 3] if channels == 4 else 255

    return Image(width, height, pixels)


def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def write_png(path: Path, image: Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = bytearray()
    stride = image.width * 4
    for y in range(image.height):
        raw.append(0)
        start = y * stride
        raw.extend(image.pixels[start:start + stride])
    ihdr = struct.pack(">IIBBBBB", image.width, image.height, 8, 6, 0, 0, 0)
    data = PNG_SIGNATURE + png_chunk(b"IHDR", ihdr) + png_chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + png_chunk(b"IEND", b"")
    path.write_bytes(data)


def background_like(pixel: tuple[int, int, int, int]) -> bool:
    r, g, b, a = pixel
    return a > 10 and r > 218 and g > 218 and b > 218 and max(r, g, b) - min(r, g, b) < 24


def clean_guard_art(image: Image) -> Image:
    cleaned = Image(image.width, image.height, bytearray(image.pixels))
    width, height = cleaned.width, cleaned.height
    seen = bytearray(width * height)

    for y in range(height):
        for x in range(width):
            start = y * width + x
            if seen[start] or not background_like(cleaned.pixel(x, y)):
                continue

            queue: deque[tuple[int, int]] = deque([(x, y)])
            seen[start] = 1
            component: list[tuple[int, int]] = []
            min_y = max_y = y
            touches_border = False
            while queue:
                cx, cy = queue.pop()
                component.append((cx, cy))
                min_y = min(min_y, cy)
                max_y = max(max_y, cy)
                if cx == 0 or cy == 0 or cx == width - 1 or cy == height - 1:
                    touches_border = True
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if nx < 0 or ny < 0 or nx >= width or ny >= height:
                        continue
                    index = ny * width + nx
                    if seen[index] or not background_like(cleaned.pixel(nx, ny)):
                        continue
                    seen[index] = 1
                    queue.append((nx, ny))

            # Border components are background. Large lower components are the
            # trapped white checkerboard holes visible under arms and around legs.
            keep_stop_sign_white = max_y < int(height * 0.25)
            remove = touches_border or (len(component) > 70 and min_y > int(height * 0.24) and not keep_stop_sign_white)
            if remove:
                for px, py in component:
                    offset = cleaned.offset(px, py)
                    cleaned.pixels[offset + 3] = 0

    return cleaned


def clean_border_background(image: Image) -> Image:
    cleaned = Image(image.width, image.height, bytearray(image.pixels))
    width, height = cleaned.width, cleaned.height
    seen = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        queue.append((width - 1, y))

    while queue:
        x, y = queue.pop()
        if x < 0 or y < 0 or x >= width or y >= height:
            continue
        index = y * width + x
        if seen[index] or not background_like(cleaned.pixel(x, y)):
            continue
        seen[index] = 1
        offset = cleaned.offset(x, y)
        cleaned.pixels[offset + 3] = 0
        queue.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    return cleaned


def alpha_bbox(image: Image, region: tuple[int, int, int, int] | None = None) -> tuple[int, int, int, int] | None:
    x0, y0, x1, y1 = region or (0, 0, image.width, image.height)
    min_x, min_y = image.width, image.height
    max_x = max_y = -1
    for y in range(max(0, y0), min(image.height, y1)):
        for x in range(max(0, x0), min(image.width, x1)):
            if image.pixel(x, y)[3] > 16:
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
    if max_x < min_x or max_y < min_y:
        return None
    return min_x, min_y, max_x + 1, max_y + 1


def red_stop_sign_bbox(image: Image, region: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
    x0, y0, x1, y1 = region
    min_x, min_y = image.width, image.height
    max_x = max_y = -1
    for y in range(max(0, y0), min(image.height, y1)):
        for x in range(max(0, x0), min(image.width, x1)):
            r, g, b, a = image.pixel(x, y)
            if a > 16 and r > 135 and g < 105 and b < 95 and r > g * 1.45 and r > b * 1.45:
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
    if max_x < min_x or max_y < min_y:
        return None
    red_width = max_x - min_x + 1
    red_height = max_y - min_y + 1
    center_x = (min_x + max_x) // 2
    # Include the pole so the sign reads as held, but avoid pulling in the
    # static character head from the reference panel.
    pole_half_width = int(red_width * 0.34)
    pad_y = min(18, int(red_height * 0.07))
    return (
        max(0, min_x - 4),
        max(0, min_y - pad_y),
        min(image.width, max_x + 18),
        min(image.height, max_y + int(red_height * 1.45)),
    )


def crop(image: Image, box: tuple[int, int, int, int]) -> Image:
    x0, y0, x1, y1 = box
    out = Image(x1 - x0, y1 - y0, bytearray((x1 - x0) * (y1 - y0) * 4))
    for y in range(out.height):
        for x in range(out.width):
            out.set_pixel(x, y, image.pixel(x0 + x, y0 + y))
    return out


def clean_running_sprite(image: Image) -> Image:
    cleaned = Image(image.width, image.height, bytearray(image.pixels))
    for y in range(cleaned.height):
        for x in range(cleaned.width):
            offset = cleaned.offset(x, y)
            r, g, b, a = cleaned.pixels[offset:offset + 4]
            if a > 0 and g > 24 and g > r * 1.35 and g > b * 1.35:
                cleaned.pixels[offset + 3] = 0
    return cleaned


def resize_nearest(image: Image, width: int, height: int) -> Image:
    out = Image(width, height, bytearray(width * height * 4))
    for y in range(height):
        sy = min(image.height - 1, int(y * image.height / height))
        for x in range(width):
            sx = min(image.width - 1, int(x * image.width / width))
            out.set_pixel(x, y, image.pixel(sx, sy))
    return out


def point_in_polygon(x: float, y: float, points: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(points) - 1
    for i, point in enumerate(points):
        xi, yi = point
        xj, yj = points[j]
        intersects = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi)
        if intersects:
            inside = not inside
        j = i
    return inside


def fill_polygon(image: Image, points: list[tuple[float, float]], color: tuple[int, int, int, int]) -> None:
    min_x = max(0, int(min(x for x, _ in points)))
    max_x = min(image.width - 1, int(max(x for x, _ in points)) + 1)
    min_y = max(0, int(min(y for _, y in points)))
    max_y = min(image.height - 1, int(max(y for _, y in points)) + 1)
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            if point_in_polygon(x + 0.5, y + 0.5, points):
                image.set_pixel(x, y, color)


def fill_rect(image: Image, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int, int]) -> None:
    for y in range(max(0, y0), min(image.height, y1)):
        for x in range(max(0, x0), min(image.width, x1)):
            image.set_pixel(x, y, color)


STOP_FONT = {
    "S": ("111", "100", "100", "111", "001", "001", "111"),
    "T": ("111", "010", "010", "010", "010", "010", "010"),
    "O": ("111", "101", "101", "101", "101", "101", "111"),
    "P": ("110", "101", "101", "110", "100", "100", "100"),
}


def draw_stop_text(image: Image, x: int, y: int, scale: int) -> None:
    cursor = x
    for char in "STOP":
        glyph = STOP_FONT[char]
        for row_index, row in enumerate(glyph):
            for col_index, value in enumerate(row):
                if value == "1":
                    fill_rect(
                        image,
                        cursor + col_index * scale,
                        y + row_index * scale,
                        cursor + (col_index + 1) * scale,
                        y + (row_index + 1) * scale,
                        (255, 255, 255, 255),
                    )
        cursor += 4 * scale


def make_stop_sign(width: int = 126, height: int = 245) -> Image:
    image = Image(width, height, bytearray(width * height * 4))
    cx = width / 2
    sign_size = min(width - 8, 116)
    x0 = (width - sign_size) / 2
    y0 = 4
    x1 = x0 + sign_size
    y1 = y0 + sign_size
    cut = sign_size * 0.29

    pole_w = max(8, int(width * 0.085))
    fill_rect(image, int(cx - pole_w / 2) - 2, int(y1 - 4), int(cx + pole_w / 2) + 2, height - 4, (18, 24, 28, 255))
    fill_rect(image, int(cx - pole_w / 2), int(y1 - 3), int(cx + pole_w / 2), height - 6, (104, 116, 124, 255))
    fill_rect(image, int(cx - 1), int(y1 - 3), int(cx + 2), height - 6, (214, 220, 224, 255))

    outer = [(x0 + cut, y0), (x1 - cut, y0), (x1, y0 + cut), (x1, y1 - cut),
             (x1 - cut, y1), (x0 + cut, y1), (x0, y1 - cut), (x0, y0 + cut)]
    white = [(x0 + cut + 5, y0 + 5), (x1 - cut - 5, y0 + 5), (x1 - 5, y0 + cut + 5), (x1 - 5, y1 - cut - 5),
             (x1 - cut - 5, y1 - 5), (x0 + cut + 5, y1 - 5), (x0 + 5, y1 - cut - 5), (x0 + 5, y0 + cut + 5)]
    red = [(x0 + cut + 12, y0 + 12), (x1 - cut - 12, y0 + 12), (x1 - 12, y0 + cut + 12), (x1 - 12, y1 - cut - 12),
           (x1 - cut - 12, y1 - 12), (x0 + cut + 12, y1 - 12), (x0 + 12, y1 - cut - 12), (x0 + 12, y0 + cut + 12)]
    fill_polygon(image, outer, (12, 14, 16, 255))
    fill_polygon(image, white, (245, 248, 248, 255))
    fill_polygon(image, red, (228, 28, 22, 255))
    text_scale = max(3, int(sign_size / 18))
    text_width = 15 * text_scale
    text_height = 7 * text_scale
    draw_stop_text(image, int(cx - text_width / 2), int(y0 + sign_size / 2 - text_height / 2), text_scale)
    return image


def scale_image(image: Image, scale: float) -> Image:
    return resize_nearest(image, max(1, int(image.width * scale + 0.5)), max(1, int(image.height * scale + 0.5)))


def pose_front_run(hero: Image, frame_index: int) -> Image:
    phase = [-1.0, -0.45, 0.45, 1.0, 0.45, -0.45][frame_index]
    out = Image(hero.width + 70, hero.height + 36, bytearray((hero.width + 70) * (hero.height + 36) * 4))
    cx = hero.width / 2.0

    for y in range(hero.height):
        ny = y / max(1, hero.height)
        for x in range(hero.width):
            pixel = hero.pixel(x, y)
            if pixel[3] <= 8:
                continue
            nx = x / max(1, hero.width)
            dx = 35
            dy = 12

            lower = ny > 0.58
            arm_band = 0.36 < ny < 0.73
            left_side = x < cx
            outer_left = nx < 0.35
            outer_right = nx > 0.65

            if lower:
                side = -1.0 if left_side else 1.0
                stride = phase * side
                dx += int(stride * 22 * (ny - 0.55) / 0.45)
                dy += int(abs(stride) * -10 + (1.0 - abs(stride)) * 8)
                if ny > 0.78:
                    dx += int(stride * 28)
                    dy += int(abs(stride) * 12)
            elif arm_band and (outer_left or outer_right):
                side = -1.0 if outer_left else 1.0
                swing = -phase * side
                dx += int(swing * 16)
                dy += int(abs(swing) * -8)
            elif ny < 0.25:
                dy += int(-abs(phase) * 4)

            out.set_pixel(max(0, min(out.width - 1, x + dx)), max(0, min(out.height - 1, y + dy)), pixel)

    return out


def alpha_composite(dest: Image, source: Image, origin_x: int, origin_y: int) -> None:
    for sy in range(source.height):
        dy = origin_y + sy
        if dy < 0 or dy >= dest.height:
            continue
        for sx in range(source.width):
            dx = origin_x + sx
            if dx < 0 or dx >= dest.width:
                continue
            sr, sg, sb, sa = source.pixel(sx, sy)
            if sa == 0:
                continue
            dest_offset = dest.offset(dx, dy)
            dr, dg, db, da = dest.pixels[dest_offset:dest_offset + 4]
            source_alpha = sa / 255.0
            dest_alpha = da / 255.0
            out_alpha = source_alpha + dest_alpha * (1.0 - source_alpha)
            if out_alpha <= 0.0:
                continue
            out_r = int((sr * source_alpha + dr * dest_alpha * (1.0 - source_alpha)) / out_alpha + 0.5)
            out_g = int((sg * source_alpha + dg * dest_alpha * (1.0 - source_alpha)) / out_alpha + 0.5)
            out_b = int((sb * source_alpha + db * dest_alpha * (1.0 - source_alpha)) / out_alpha + 0.5)
            dest.pixels[dest_offset:dest_offset + 4] = bytes((out_r, out_g, out_b, int(out_alpha * 255 + 0.5)))


def scaled_to_fit(image: Image, max_width: int, max_height: int) -> Image:
    scale = min(max_width / image.width, max_height / image.height)
    width = max(1, int(image.width * scale + 0.5))
    height = max(1, int(image.height * scale + 0.5))
    return resize_nearest(image, width, height)


def build_run_strip(pet_dir: Path, base: Image) -> Image:
    frame_count = RUNUP_FRAME_COUNT
    frame_width = RUNUP_FRAME_WIDTH
    frame_height = RUNUP_FRAME_HEIGHT
    strip = Image(frame_width * frame_count, frame_height, bytearray(frame_width * frame_count * frame_height * 4))

    base_box = alpha_bbox(base)
    if not base_box:
        raise PngError(f"no base character in {pet_dir}")
    hero = crop(base, base_box)
    hero = scaled_to_fit(hero, 255, 610)
    sign = make_stop_sign(86, 176)

    for frame_index in range(frame_count):
        frame = Image(frame_width, frame_height, bytearray(frame_width * frame_height * 4))
        # The overlay performs the big toward-screen zoom. These frames keep
        # the character front-facing and add a small run bob/stride read.
        posed = pose_front_run(hero, frame_index)
        pose = scale_image(posed, [0.92, 0.98, 1.03, 0.99, 1.05, 1.00][frame_index])
        held_sign = scale_image(sign, [0.92, 0.98, 1.03, 0.99, 1.05, 1.00][frame_index])
        bob = [-10, 8, -7, 9, -6, 7][frame_index]
        pose_x = (frame_width - pose.width) // 2
        pose_y = frame_height - pose.height - 20 + bob
        sign_x = pose_x + int(pose.width * 0.70)
        sign_y = pose_y + int(pose.height * 0.25) + [-5, 4, -4, 5, -3, 4][frame_index]
        alpha_composite(frame, held_sign, sign_x, sign_y)
        alpha_composite(frame, pose, pose_x, pose_y)
        alpha_composite(strip, frame, frame_index * frame_width, 0)

    return strip


def build_assets(repo: Path, pet_id: str, *, rebuild_run_strips: bool = False) -> None:
    reference = repo / "hermes-agent-pets" / "reference-art" / pet_id / STOP_REFERENCE_NAMES[pet_id]
    base_reference = repo / "hermes-agent-pets" / "reference-art" / pet_id / "source.png"
    character_assets = repo / "character-sets" / pet_id / "assets"
    plugin_assets = repo / "hermes-agent-pets" / "hermes-pet-agent" / "assets" / pet_id
    guard = clean_guard_art(read_png(reference))
    run_strip = None
    if rebuild_run_strips:
        base = clean_border_background(read_png(base_reference))
        run_strip = build_run_strip(repo / "character-sets" / pet_id, base)

    for asset_dir in (character_assets, plugin_assets):
        write_png(asset_dir / "guard-peek-stop-no-panel.png", guard)
        write_png(asset_dir / "panel-shell.png", guard)
        if run_strip is not None:
            write_png(asset_dir / "stop-sign-run-front-strip.png", run_strip)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pets", nargs="*", choices=PETS, default=list(PETS))
    parser.add_argument(
        "--rebuild-run-strips",
        action="store_true",
        help=(
            "Also rebuild stop-sign-run-front-strip.png from the static reference art. "
            "Leave this off to preserve generated Hermes-style front run-up strips."
        ),
    )
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    for pet_id in args.pets:
        build_assets(repo, pet_id, rebuild_run_strips=args.rebuild_run_strips)
        print(f"built guard assets for {pet_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
