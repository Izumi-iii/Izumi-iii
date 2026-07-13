from pathlib import Path

from PIL import Image, ImageSequence

from scripts.build_hero_gif import build_gif


def alpha_mask_center_x(image):
    alpha = image.convert("RGBA").getchannel("A")
    visible_x = [
        offset % alpha.width
        for offset, value in enumerate(alpha.tobytes())
        if value > 0
    ]
    assert visible_x
    return sum(visible_x) / len(visible_x)


def test_build_gif_slices_equal_horizontal_frames(tmp_path):
    sheet = Image.new("RGBA", (32, 8))
    colors = ("#39F6D2", "#FF4FD8", "#0D0A20", "#E9E4FF")
    for index, color in enumerate(colors):
        sheet.paste(color, (index * 8, 0, (index + 1) * 8, 8))
    source = tmp_path / "sheet.png"
    output = tmp_path / "idle.gif"
    sheet.save(source)

    build_gif(source, output, frame_count=4, display_size=64, duration_ms=500)

    with Image.open(output) as gif:
        frames = list(ImageSequence.Iterator(gif))
        assert len(frames) == 4
        assert gif.size == (64, 64)
        assert gif.info["loop"] == 0
        assert gif.info["duration"] == 500


def test_build_gif_preserves_transparent_corners_in_every_frame(tmp_path):
    source = Path("assets/hero/miku-idle-sheet.png")
    output = tmp_path / "transparent-idle.gif"

    build_gif(source, output, frame_count=4, display_size=256, duration_ms=500)

    with Image.open(output) as gif:
        assert "transparency" in gif.info
        corner_alphas = [
            frame.convert("RGBA").getpixel((0, 0))[3]
            for frame in ImageSequence.Iterator(gif)
        ]
        assert corner_alphas == [0, 0, 0, 0]


def test_build_gif_aligns_loop_endpoints(tmp_path):
    source = Path("assets/hero/miku-idle-sheet.png")
    output = tmp_path / "aligned-idle.gif"

    build_gif(source, output, frame_count=4, display_size=256, duration_ms=500)

    with Image.open(output) as gif:
        frames = [frame.convert("RGBA") for frame in ImageSequence.Iterator(gif)]
    loop_center_delta = abs(
        alpha_mask_center_x(frames[-1]) - alpha_mask_center_x(frames[0])
    )
    assert loop_center_delta <= 0.25


def test_committed_hero_is_small_and_animated():
    hero = Path("assets/hero/miku-idle.gif")
    assert hero.exists()
    assert hero.stat().st_size <= 3 * 1024 * 1024
    with Image.open(hero) as gif:
        assert gif.size == (256, 256)
        assert gif.n_frames == 4
        assert gif.info["loop"] == 0
        assert "transparency" in gif.info
        frames = [frame.convert("RGBA") for frame in ImageSequence.Iterator(gif)]
        assert [frame.info["duration"] for frame in frames] == [500, 500, 500, 500]
        assert [frame.getpixel((0, 0))[3] for frame in frames] == [0, 0, 0, 0]
