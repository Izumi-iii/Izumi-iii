from datetime import datetime, timezone
import xml.etree.ElementTree as ET

from scripts.profile_data import ProfileData, ProjectData
from scripts.svg_cards import (
    render_languages,
    render_last_sync,
    render_pending,
    render_profile_stats,
    render_projects,
)


PROFILE = ProfileData(
    login="Izumi-iii",
    commits=42,
    pull_requests=7,
    contributions=81,
    total_stars=10,
    languages=(("Python", 1200), ("C++", 800), ("Swift", 700)),
    projects=(
        ProjectData("magicState", "https://github.com/Izumi-iii/magicState", 5, "2026-07-12T02:00:00Z"),
        ProjectData("downing_detect", "https://github.com/Izumi-iii/downing_detect", 3, "2026-06-20T02:00:00Z"),
        ProjectData("Algorithm", "https://github.com/Izumi-iii/Algorithm", 2, "2026-05-10T02:00:00Z"),
    ),
)


def assert_safe_svg(svg: str):
    ET.fromstring(svg)
    assert "<script" not in svg.lower()
    assert "#0D0A20" in svg
    assert "#39F6D2" in svg
    assert "#FF4FD8" in svg


def test_render_all_cards_are_valid_and_thematic():
    cards = (
        render_profile_stats(PROFILE),
        render_languages(PROFILE),
        render_projects(PROFILE),
        render_last_sync(datetime(2026, 7, 13, 2, 17, tzinfo=timezone.utc)),
        render_pending("PLAYER STATS", 680, 180),
    )
    for card in cards:
        assert_safe_svg(card)

    assert "42" in cards[0] and "COMMITS" in cards[0]
    assert "Python" in cards[1] and "Swift" in cards[1]
    assert "magicState" in cards[2] and "2026-07-12" in cards[2]
    assert "2026-07-13 02:17 UTC" in cards[3]
    assert "SYNC PENDING" in cards[4]


def test_renderer_escapes_untrusted_text():
    hostile = ProfileData(**{**PROFILE.__dict__, "login": "<script>alert(1)</script>"})
    svg = render_profile_stats(hostile)
    assert "&lt;script&gt;" in svg
    assert "<script>" not in svg
