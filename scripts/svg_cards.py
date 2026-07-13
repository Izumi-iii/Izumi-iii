from __future__ import annotations

from datetime import datetime
from html import escape

from scripts.profile_data import ProfileData


BG = "#0D0A20"
TEAL = "#39F6D2"
BRIGHT = "#4FFFE1"
MAGENTA = "#FF4FD8"
TEXT = "#E9E4FF"
MUTED = "#A89BCF"
FONT = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"


def _shell(title: str, body: str, width: int, height: int) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
<rect x="2" y="2" width="{width - 8}" height="{height - 8}" rx="6" fill="{BG}" stroke="{BRIGHT}" stroke-width="3"/>
<path d="M18 16h38M18 22h20" stroke="{MAGENTA}" stroke-width="3"/>
<text x="24" y="46" fill="{TEAL}" font-family="{FONT}" font-size="16" font-weight="700">{escape(title)}</text>
{body}
</svg>'''


def _text(x: int, y: int, value: str, size: int = 14, color: str = TEXT, weight: int = 400) -> str:
    return f'<text x="{x}" y="{y}" fill="{color}" font-family="{FONT}" font-size="{size}" font-weight="{weight}">{escape(str(value))}</text>'


def render_profile_stats(profile: ProfileData) -> str:
    metrics = (
        ("COMMITS / YEAR", profile.commits),
        ("PRS / YEAR", profile.pull_requests),
        ("CONTRIBUTIONS / YEAR", profile.contributions),
        ("STARS EARNED", profile.total_stars),
    )
    body = _text(24, 72, f"PLAYER // {profile.login}", 12, MUTED)
    for index, (label, value) in enumerate(metrics):
        x = 24 + (index % 2) * 320
        y = 112 + (index // 2) * 48
        body += _text(x, y, value, 24, MAGENTA, 700)
        body += _text(x + 72, y, label, 12, TEXT)
    return _shell("PLAYER STATS", body, 680, 180)


def render_languages(profile: ProfileData) -> str:
    total = sum(size for _, size in profile.languages) or 1
    body = ""
    y = 78
    for name, size in profile.languages[:5]:
        ratio = size / total
        width = max(8, round(470 * ratio))
        body += _text(24, y, name, 13)
        body += f'<rect x="150" y="{y - 13}" width="470" height="12" fill="#211B45"/>'
        body += f'<rect x="150" y="{y - 13}" width="{width}" height="12" fill="{TEAL}"/>'
        body += _text(630, y, f"{ratio:.0%}", 11, MUTED)
        y += 26
    return _shell("SKILL LOADOUT", body, 680, 220)


def render_projects(profile: ProfileData) -> str:
    body = ""
    y = 78
    for index, project in enumerate(profile.projects, start=1):
        body += _text(24, y, f"0{index}", 14, MAGENTA, 700)
        body += _text(64, y, project.name, 15, TEAL, 700)
        body += _text(350, y, f"★ {project.stars}", 12, TEXT)
        body += _text(470, y, project.updated_at[:10], 12, MUTED)
        y += 38
    return _shell("FEATURED BUILDS // LIVE", body, 680, 190)


def render_last_sync(moment: datetime) -> str:
    label = moment.strftime("%Y-%m-%d %H:%M UTC")
    body = _text(24, 75, label, 15, TEXT, 700)
    body += _text(430, 75, "STATUS: ONLINE", 13, TEAL, 700)
    return _shell("LAST PROFILE SYNC", body, 680, 100)


def render_pending(title: str, width: int, height: int) -> str:
    body = _text(24, 82, "SYNC PENDING // RUN DAILY PROFILE WORKFLOW", 14, MAGENTA, 700)
    return _shell(title, body, width, height)
