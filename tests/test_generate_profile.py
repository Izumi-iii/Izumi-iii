from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.generate_profile import atomic_write_assets, generate_from_fixture


def test_generate_from_fixture_writes_all_assets(tmp_path):
    generate_from_fixture(
        Path("tests/fixtures/github-profile.json"),
        tmp_path,
        datetime(2026, 7, 13, 2, 17, tzinfo=timezone.utc),
    )
    assert sorted(path.name for path in tmp_path.glob("*.svg")) == [
        "languages.svg",
        "last-sync.svg",
        "profile-stats.svg",
        "projects.svg",
    ]
    assert "42" in (tmp_path / "profile-stats.svg").read_text()


def test_atomic_write_preserves_existing_assets_when_validation_fails(tmp_path):
    target = tmp_path / "profile-stats.svg"
    target.write_text("previous")
    with pytest.raises(ValueError, match="not a non-empty SVG"):
        atomic_write_assets(tmp_path, {"profile-stats.svg": "broken"})
    assert target.read_text() == "previous"


def test_atomic_write_restores_asset_set_when_publication_fails(
    tmp_path, monkeypatch
):
    originals = {
        "profile-stats.svg": b"previous profile stats\n",
        "languages.svg": b"previous languages\n",
    }
    for name, content in originals.items():
        (tmp_path / name).write_bytes(content)

    assets = {
        "profile-stats.svg": "<svg>" + "new stats " * 12 + "</svg>",
        "projects.svg": "<svg>" + "new project " * 12 + "</svg>",
        "languages.svg": "<svg>" + "new languages " * 12 + "</svg>",
    }
    real_replace = os.replace
    publish_attempts = 0
    failure_injected = False

    def fail_third_publication(source, destination):
        nonlocal failure_injected, publish_attempts
        if Path(destination).parent == tmp_path and not failure_injected:
            publish_attempts += 1
            if publish_attempts == 3:
                failure_injected = True
                raise OSError("simulated publication failure")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_third_publication)

    with pytest.raises(OSError, match="simulated publication failure"):
        atomic_write_assets(tmp_path, assets)

    assert {
        path.name: path.read_bytes() for path in sorted(tmp_path.glob("*.svg"))
    } == originals


def test_pending_cli_writes_assets_when_invoked_by_script_path(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate_profile.py",
            "--pending",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert sorted(path.name for path in tmp_path.glob("*.svg")) == [
        "languages.svg",
        "last-sync.svg",
        "profile-stats.svg",
        "projects.svg",
    ]
