from copy import deepcopy
from pathlib import Path
import re

import pytest
import yaml


WORKFLOWS = Path(".github/workflows")
WORKFLOW_NAMES = {"daily-profile.yml", "snake.yml"}
MAIN_GUARD = (
    "(github.event_name == 'schedule' || "
    "github.event_name == 'workflow_dispatch') && "
    "github.ref == 'refs/heads/main'"
)
CHECKOUT = "actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10"
SETUP_PYTHON = "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1"
UPLOAD_ARTIFACT = "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
DOWNLOAD_ARTIFACT = "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"
SNAKE_ACTION = "Platane/snk/svg-only@d8f6715049803e982ee5ff501b6b9b7d5deeb09b"
SNAKE_OUTPUTS = [
    "dist/contribution-snake.svg?color_snake=#39F6D2&color_dots="
    "#EEEAFB,#B7F7EC,#65E9D2,#39CDB5,#FF4FD8",
    "dist/contribution-snake-dark.svg?palette=github-dark&color_snake="
    "#FF4FD8&color_dots=#0D0A20,#173A46,#1A766F,#39F6D2,#4FFFE1",
]


def load(name: str):
    return yaml.load((WORKFLOWS / name).read_text(), Loader=yaml.BaseLoader)


def text(name: str) -> str:
    return (WORKFLOWS / name).read_text()


def named_step(job: dict, name: str) -> dict:
    matching = [step for step in job["steps"] if step.get("name") == name]
    assert len(matching) == 1, f"expected one {name!r} step"
    return matching[0]


def action_step(job: dict, expected: str) -> dict:
    matching = [step for step in job["steps"] if step.get("uses") == expected]
    assert len(matching) == 1, f"expected one {expected!r} step"
    return matching[0]


def command_lines(script: str) -> list[str]:
    return [line.strip() for line in script.splitlines() if line.strip()]


def push_commands(workflow_text: str) -> list[str]:
    return [
        line
        for line in command_lines(workflow_text)
        if line.startswith("git push ")
    ]


def assert_split_permissions(workflows: dict[str, dict]) -> None:
    writers = {
        (workflow_name, job_name)
        for workflow_name, workflow in workflows.items()
        for job_name, job in workflow["jobs"].items()
        if job.get("permissions", {}).get("contents") == "write"
    }
    assert writers == {
        ("daily-profile.yml", "publish"),
        ("snake.yml", "publish"),
    }, "only publish jobs may have contents write"
    for workflow in workflows.values():
        for job_name, job in workflow["jobs"].items():
            if job_name != "publish":
                assert job.get("permissions") == {"contents": "read"}


def assert_main_only_dynamic_jobs(workflow: dict) -> None:
    for name in ("generate", "publish"):
        assert workflow["jobs"][name]["if"] == MAIN_GUARD


def assert_daily_contract(workflow: dict, workflow_text: str) -> None:
    assert set(workflow["on"]) == {
        "push", "pull_request", "schedule", "workflow_dispatch"
    }
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert workflow["on"]["pull_request"]["branches"] == ["main"]
    assert workflow["on"]["schedule"] == [{"cron": "17 2 * * *"}]
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]) == {"quality", "generate", "publish"}
    assert_main_only_dynamic_jobs(workflow)

    quality = workflow["jobs"]["quality"]
    action_step(quality, CHECKOUT)
    setup = action_step(quality, SETUP_PYTHON)
    assert setup["with"] == {"python-version": "3.13", "cache": "pip"}

    generate = workflow["jobs"]["generate"]
    assert generate["needs"] == "quality"
    checkout = action_step(generate, CHECKOUT)
    assert checkout["with"] == {"ref": "main"}
    action_step(generate, SETUP_PYTHON)
    generator = named_step(generate, "Generate validated SVG cards")
    assert generator["run"] == (
        "python scripts/generate_profile.py --output-dir dist/profile-cards"
    )
    assert generator["env"] == {"GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}"}
    upload = action_step(generate, UPLOAD_ARTIFACT)
    assert upload["with"] == {
        "name": "profile-cards",
        "path": "dist/profile-cards",
        "if-no-files-found": "error",
    }

    publish = workflow["jobs"]["publish"]
    assert publish["needs"] == "generate"
    checkout = action_step(publish, CHECKOUT)
    assert checkout["with"] == {"ref": "main", "fetch-depth": "0"}
    download = action_step(publish, DOWNLOAD_ARTIFACT)
    assert download["with"] == {
        "name": "profile-cards",
        "path": ".profile-cards-staged",
    }
    publish_step = named_step(publish, "Publish changed cards")
    commands = command_lines(publish_step["run"])
    assert "mv .profile-cards-staged assets/generated" in commands
    assert [line for line in commands if line.startswith("git add ")] == [
        "git add assets/generated"
    ]
    assert push_commands(workflow_text) == ["git push origin HEAD:main"]
    assert "--force" not in push_commands(workflow_text)[0]


def assert_snake_contract(workflow: dict, workflow_text: str) -> None:
    assert set(workflow["on"]) == {"schedule", "workflow_dispatch"}
    assert workflow["on"]["schedule"] == [{"cron": "43 2 * * *"}]
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]) == {"generate", "publish"}
    assert_main_only_dynamic_jobs(workflow)

    generate = workflow["jobs"]["generate"]
    snake = action_step(generate, SNAKE_ACTION)
    assert snake["with"]["github_user_name"] == "${{ github.repository_owner }}"
    assert snake["with"]["outputs"].splitlines() == SNAKE_OUTPUTS
    assert snake["env"] == {"GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}"}
    validation = named_step(generate, "Validate generated files")["run"]
    assert "xml.etree.ElementTree" in validation
    assert "{http://www.w3.org/2000/svg}svg" in validation
    assert "set(path.name for path in output.iterdir())" in validation
    upload = action_step(generate, UPLOAD_ARTIFACT)
    assert upload["with"] == {
        "name": "contribution-snake",
        "path": "dist/contribution-snake.svg\ndist/contribution-snake-dark.svg",
        "if-no-files-found": "error",
    }

    publish = workflow["jobs"]["publish"]
    assert publish["needs"] == "generate"
    checkout = action_step(publish, CHECKOUT)
    assert checkout["with"] == {"ref": "main", "fetch-depth": "0"}
    download = action_step(publish, DOWNLOAD_ARTIFACT)
    assert download["with"] == {
        "name": "contribution-snake",
        "path": "dist",
    }
    publish_step = named_step(publish, "Publish output branch")
    commands = command_lines(publish_step["run"])
    assert "git switch --orphan output" in commands
    assert [line for line in commands if line.startswith("git rm ")] == [
        "git rm -rf --ignore-unmatch ."
    ]
    assert [line for line in commands if line.startswith("git add ")] == [
        "git add contribution-snake.svg contribution-snake-dark.svg"
    ]
    assert push_commands(workflow_text) == ["git push --force origin output"]


def test_repository_has_exactly_two_workflows():
    assert {path.name for path in WORKFLOWS.iterdir() if path.is_file()} == WORKFLOW_NAMES


def test_workflows_split_read_only_generation_from_write_only_publication():
    workflows = {name: load(name) for name in WORKFLOW_NAMES}
    assert_split_permissions(workflows)


def test_daily_uses_main_guard_artifact_boundary_and_atomic_ref_publish():
    assert_daily_contract(load("daily-profile.yml"), text("daily-profile.yml"))


def test_snake_uses_main_guard_exact_xml_artifact_and_output_publish():
    assert_snake_contract(load("snake.yml"), text("snake.yml"))


def test_every_external_action_is_pinned_to_an_approved_full_sha():
    approved = {
        CHECKOUT, SETUP_PYTHON, UPLOAD_ARTIFACT, DOWNLOAD_ARTIFACT, SNAKE_ACTION
    }
    used = {
        step["uses"]
        for name in WORKFLOW_NAMES
        for job in load(name)["jobs"].values()
        for step in job["steps"]
        if "uses" in step
    }
    assert used <= approved
    assert all(re.search(r"@[0-9a-f]{40}$", action) for action in used)


def test_non_main_manual_dispatch_cannot_generate_or_publish():
    for name in WORKFLOW_NAMES:
        workflow = load(name)
        assert_main_only_dynamic_jobs(workflow)
        mutated = deepcopy(workflow)
        mutated["jobs"]["publish"]["if"] = "github.event_name == 'workflow_dispatch'"
        with pytest.raises(AssertionError):
            assert_main_only_dynamic_jobs(mutated)


def test_workflows_have_exact_concurrency_and_only_repository_token():
    workflows = [load(name) for name in sorted(WORKFLOW_NAMES)]
    assert [workflow["concurrency"]["group"] for workflow in workflows] == [
        "daily-profile-main", "contribution-snake-output"
    ]
    assert all(
        workflow["concurrency"]["cancel-in-progress"] == "false"
        for workflow in workflows
    )
    all_text = "\n".join(text(name) for name in sorted(WORKFLOW_NAMES))
    secret_references = re.findall(r"\bsecrets\.([A-Za-z_][A-Za-z0-9_]*)\b", all_text)
    assert secret_references and set(secret_references) == {"GITHUB_TOKEN"}
    assert [
        command
        for name in sorted(WORKFLOW_NAMES)
        for command in push_commands(text(name))
    ] == ["git push origin HEAD:main", "git push --force origin output"]


def test_permission_contract_rejects_write_on_generation_job():
    workflows = {name: deepcopy(load(name)) for name in WORKFLOW_NAMES}
    workflows["snake.yml"]["jobs"]["generate"]["permissions"] = {
        "contents": "write"
    }
    with pytest.raises(AssertionError, match="only publish jobs"):
        assert_split_permissions(workflows)


def test_snake_contract_rejects_another_force_push_target():
    workflow_text = text("snake.yml").replace(
        "git push --force origin output",
        "git push --force origin output\n          git push --force origin backup",
    )
    with pytest.raises(AssertionError):
        assert_snake_contract(load("snake.yml"), workflow_text)
