from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
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
    output = tmp_path / "generated"
    output.mkdir()
    originals = {
        "profile-stats.svg": b"previous profile stats\n",
        "languages.svg": b"previous languages\n",
    }
    for name, content in originals.items():
        (output / name).write_bytes(content)

    assets = {
        "profile-stats.svg": "<svg>" + "new stats " * 12 + "</svg>",
        "projects.svg": "<svg>" + "new project " * 12 + "</svg>",
        "languages.svg": "<svg>" + "new languages " * 12 + "</svg>",
    }
    real_replace = os.replace
    failure_injected = False

    def fail_directory_publication(source, destination):
        nonlocal failure_injected
        if (
            Path(source).name == "staged"
            and Path(destination) == output
            and not failure_injected
        ):
            failure_injected = True
            raise OSError("simulated publication failure")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_directory_publication)

    with pytest.raises(OSError, match="simulated publication failure"):
        atomic_write_assets(output, assets)

    assert {
        path.name: path.read_bytes() for path in sorted(output.glob("*.svg"))
    } == originals


def test_atomic_write_uses_directory_snapshot_and_fallback_restore(
    tmp_path, monkeypatch
):
    output = tmp_path / "generated"
    output.mkdir()
    originals = {
        "profile-stats.svg": b"previous profile stats\n",
        "languages.svg": b"previous languages\n",
    }
    for name, content in originals.items():
        (output / name).write_bytes(content)

    assets = {
        "profile-stats.svg": "<svg>" + "new stats " * 12 + "</svg>",
        "projects.svg": "<svg>" + "new projects " * 12 + "</svg>",
    }
    real_replace = os.replace
    publication_failed = False
    restoration_failed = False

    def fail_publication_then_first_restore(source, destination):
        nonlocal publication_failed, restoration_failed
        source_path = Path(source)
        destination_path = Path(destination)
        if destination_path == output and source_path.name == "staged":
            publication_failed = True
            raise OSError("simulated directory publication failure")
        if (
            publication_failed
            and destination_path == output
            and source_path.name == "snapshot"
            and not restoration_failed
        ):
            restoration_failed = True
            raise OSError("simulated first restoration failure")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_publication_then_first_restore)

    with pytest.raises(OSError, match="simulated directory publication failure") as caught:
        atomic_write_assets(output, assets)

    assert publication_failed and restoration_failed
    assert {
        path.name: path.read_bytes() for path in sorted(output.iterdir())
    } == originals
    notes = getattr(caught.value, "__notes__", [])
    assert any("rollback" in note.lower() for note in notes)


def test_atomic_write_preserves_snapshot_when_both_restore_paths_fail(
    tmp_path, monkeypatch
):
    output = tmp_path / "generated"
    output.mkdir()
    original = b"previous profile stats\n"
    (output / "profile-stats.svg").write_bytes(original)
    real_replace = os.replace
    real_copytree = shutil.copytree
    publication_failed = False

    def fail_publication_and_atomic_restore(source, destination):
        nonlocal publication_failed
        source_path = Path(source)
        if Path(destination) == output and source_path.name == "staged":
            publication_failed = True
            raise OSError("primary publication error")
        if (
            publication_failed
            and Path(destination) == output
            and source_path.name == "snapshot"
        ):
            raise OSError("atomic rollback error")
        real_replace(source, destination)

    def fail_copy_fallback(source, destination, *args, **kwargs):
        if publication_failed and Path(source).name == "snapshot":
            raise OSError("copy rollback error")
        return real_copytree(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "replace", fail_publication_and_atomic_restore)
    monkeypatch.setattr("scripts.generate_profile.shutil.copytree", fail_copy_fallback)

    with pytest.raises(OSError, match="primary publication error") as caught:
        atomic_write_assets(
            output,
            {"profile-stats.svg": "<svg>" + "new stats " * 12 + "</svg>"},
        )

    notes = getattr(caught.value, "__notes__", [])
    preserved_note = next(note for note in notes if "recoverable" in note)
    preserved_path = Path(
        preserved_note.split("preserved at ", 1)[1].split(". First", 1)[0]
    )
    assert preserved_path.is_dir()
    assert (preserved_path / "profile-stats.svg").read_bytes() == original
    assert not output.exists()


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
