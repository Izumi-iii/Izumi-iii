from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def build_gif(
    sheet_path: Path,
    output_path: Path,
    frame_count: int = 4,
    display_size: int = 256,
    duration_ms: int = 500,
) -> None:
    with Image.open(sheet_path) as source:
        sheet = source.convert("RGBA")
    if sheet.width % frame_count:
        raise ValueError("sprite-sheet width must be divisible by frame count")
    frame_width = sheet.width // frame_count
    if frame_width != sheet.height:
        raise ValueError("each sprite frame must be square")

    frames = []
    for index in range(frame_count):
        frame = sheet.crop(
            (index * frame_width, 0, (index + 1) * frame_width, sheet.height)
        )
        frame = frame.resize((display_size, display_size), Image.Resampling.NEAREST)
        transparent_pixels = frame.getchannel("A").point(
            lambda alpha: 255 if alpha == 0 else 0
        )
        frame = frame.convert("RGB").convert(
            "P", palette=Image.Palette.ADAPTIVE, colors=255
        )
        frame.paste(255, mask=transparent_pixels)
        frames.append(frame)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
        disposal=2,
        optimize=True,
        transparency=255,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sheet", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--frames", type=int, default=4)
    parser.add_argument("--size", type=int, default=256)
    parser.add_argument("--duration", type=int, default=500)
    args = parser.parse_args()
    build_gif(args.sheet, args.output, args.frames, args.size, args.duration)


if __name__ == "__main__":
    main()
