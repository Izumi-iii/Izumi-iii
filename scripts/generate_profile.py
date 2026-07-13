from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.profile_data import fetch_profile, parse_profile_payload
from scripts.svg_cards import (
    render_languages,
    render_last_sync,
    render_pending,
    render_profile_stats,
    render_projects,
)


FEATURED = ("magicState", "downing_detect", "Algorithm")


def generate_assets(profile, moment: datetime) -> dict[str, str]:
    return {
        "profile-stats.svg": render_profile_stats(profile),
        "languages.svg": render_languages(profile),
        "projects.svg": render_projects(profile),
        "last-sync.svg": render_last_sync(moment),
    }


def pending_assets() -> dict[str, str]:
    return {
        "profile-stats.svg": render_pending("PLAYER STATS", 680, 180),
        "languages.svg": render_pending("SKILL LOADOUT", 680, 220),
        "projects.svg": render_pending("FEATURED BUILDS // LIVE", 680, 190),
        "last-sync.svg": render_pending("LAST PROFILE SYNC", 680, 100),
    }


def atomic_write_assets(output_dir: Path, assets: dict[str, str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in assets.items():
        if not content.lstrip().startswith("<svg") or len(content) < 100:
            raise ValueError(f"{name} is not a non-empty SVG")

    temp_dir = Path(tempfile.mkdtemp(prefix="profile-assets-", dir=output_dir.parent))
    try:
        for name, content in assets.items():
            (temp_dir / name).write_text(content, encoding="utf-8")

        backup_dir = temp_dir / "previous"
        backup_dir.mkdir()
        existing_assets = set()
        for name in assets:
            target = output_dir / name
            if target.exists():
                shutil.copy2(target, backup_dir / name)
                existing_assets.add(name)

        try:
            for name in assets:
                os.replace(temp_dir / name, output_dir / name)
        except Exception:
            for name in assets:
                target = output_dir / name
                if name in existing_assets:
                    os.replace(backup_dir / name, target)
                else:
                    target.unlink(missing_ok=True)
            raise
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def generate_from_fixture(fixture: Path, output_dir: Path, moment: datetime) -> None:
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    profile = parse_profile_payload(payload, FEATURED)
    atomic_write_assets(output_dir, generate_assets(profile, moment))


def parse_moment(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--login", default="Izumi-iii")
    parser.add_argument("--output-dir", type=Path, default=Path("assets/generated"))
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--now")
    parser.add_argument("--pending", action="store_true")
    args = parser.parse_args()
    moment = parse_moment(args.now)

    if args.pending:
        atomic_write_assets(args.output_dir, pending_assets())
    elif args.fixture:
        generate_from_fixture(args.fixture, args.output_dir, moment)
    else:
        profile = fetch_profile(os.environ.get("GITHUB_TOKEN", ""), args.login, FEATURED)
        atomic_write_assets(args.output_dir, generate_assets(profile, moment))


if __name__ == "__main__":
    main()
