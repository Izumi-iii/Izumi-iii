from copy import deepcopy
from pathlib import Path
import re

import pytest
import yaml


WORKFLOWS = Path(".github/workflows")
WORKFLOW_NAMES = {"daily-profile.yml", "snake.yml"}
DAILY_GUARD = (
    "(github.event_name == 'schedule' || "
    "github.event_name == 'workflow_dispatch') && "
    "github.ref == 'refs/heads/main'"
)
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


def action_step(job: dict, prefix: str, expected: str) -> dict:
    matching = [
        step for step in job["steps"] if step.get("uses", "").startswith(prefix)
    ]
    assert [step["uses"] for step in matching] == [expected]
    return matching[0]


def command_lines(script: str) -> list[str]:
    return [line.strip() for line in script.splitlines() if line.strip()]


def push_commands(workflow_text: str) -> list[str]:
    return [
        line
        for line in command_lines(workflow_text)
        if line.startswith("git push ")
    ]


def assert_only_publishing_jobs_write(workflows: dict[str, dict]) -> None:
    writers = {
        (workflow_name, job_name)
        for workflow_name, workflow in workflows.items()
        for job_name, job in workflow["jobs"].items()
        if job.get("permissions", {}).get("contents") == "write"
    }
    assert writers == {
        ("daily-profile.yml", "generate"),
        ("snake.yml", "generate"),
    }, "only publishing jobs may have contents write"


def assert_daily_trigger_and_permission_contract(workflow: dict) -> None:
    assert set(workflow["on"]) == {
        "push",
        "pull_request",
        "schedule",
        "workflow_dispatch",
    }
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert workflow["on"]["pull_request"]["branches"] == ["main"]
    assert workflow["on"]["schedule"] == [{"cron": "17 2 * * *"}]
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]) == {"quality", "generate"}

    quality = workflow["jobs"]["quality"]
    assert quality.get("permissions") == {"contents": "read"}, (
        "quality job must be explicitly read-only"
    )

    generate = workflow["jobs"]["generate"]
    assert generate["permissions"] == {"contents": "write"}
    assert generate["needs"] == "quality"
    assert generate["if"] == DAILY_GUARD, (
        "generate must require a scheduled/manual main-branch event"
    )


def assert_daily_toolchain_contract(workflow: dict) -> None:
    quality = workflow["jobs"]["quality"]
    action_step(quality, "actions/checkout@", "actions/checkout@v6")
    quality_setup = action_step(
        quality, "actions/setup-python@", "actions/setup-python@v6"
    )
    assert quality_setup["with"] == {"python-version": "3.13", "cache": "pip"}
    quality_runs = [step["run"] for step in quality["steps"] if "run" in step]
    assert quality_runs == [
        "python -m pip install -r requirements-dev.txt",
        "pytest",
        "python scripts/validate_readme.py README.md",
    ]

    generate = workflow["jobs"]["generate"]
    checkout = action_step(generate, "actions/checkout@", "actions/checkout@v6")
    assert checkout.get("with", {}).get("ref") == "main", (
        "generate checkout must pin ref main"
    )
    assert checkout["with"].get("fetch-depth") == "0"
    generate_setup = action_step(
        generate, "actions/setup-python@", "actions/setup-python@v6"
    )
    assert generate_setup["with"] == {"python-version": "3.13"}

    generator = named_step(generate, "Generate validated SVG cards")
    assert generator["run"] == "python scripts/generate_profile.py"
    assert generator["env"] == {
        "GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}"
    }


def assert_daily_publication_contract(workflow: dict, workflow_text: str) -> None:
    publish = named_step(workflow["jobs"]["generate"], "Publish changed cards")
    commands = command_lines(publish["run"])
    assert [line for line in commands if line.startswith("git add ")] == [
        "git add assets/generated"
    ]
    assert "if git diff --cached --quiet; then" in commands
    assert "echo \"Profile cards are already current\"" in commands
    assert push_commands(workflow_text) == ["git push origin HEAD:main"], (
        "daily workflow must have only the normal push to main"
    )
    assert "--force" not in push_commands(workflow_text)[0]


def assert_snake_contract(workflow: dict, workflow_text: str) -> None:
    assert set(workflow["on"]) == {"schedule", "workflow_dispatch"}
    assert workflow["on"]["schedule"] == [{"cron": "43 2 * * *"}]
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "contribution-snake-output",
        "cancel-in-progress": "false",
    }
    assert set(workflow["jobs"]) == {"generate"}

    generate = workflow["jobs"]["generate"]
    assert generate["permissions"] == {"contents": "write"}
    checkout = action_step(generate, "actions/checkout@", "actions/checkout@v6")
    assert checkout["with"] == {"fetch-depth": "0"}

    snake = action_step(
        generate, "Platane/snk/", "Platane/snk/svg-only@v3"
    )
    assert snake["with"]["github_user_name"] == "${{ github.repository_owner }}"
    assert snake["with"]["outputs"].splitlines() == SNAKE_OUTPUTS
    assert snake["env"] == {"GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}"}

    validate = named_step(generate, "Validate generated files")
    assert command_lines(validate["run"]) == [
        "test -s dist/contribution-snake.svg",
        "test -s dist/contribution-snake-dark.svg",
        "grep -q '<svg' dist/contribution-snake.svg",
        "grep -q '<svg' dist/contribution-snake-dark.svg",
    ]

    publish = named_step(generate, "Publish output branch")
    commands = command_lines(publish["run"])
    assert "git switch --orphan output" in commands
    assert "git rm -rf . 2>/dev/null || true" in commands, (
        "output cleanup must succeed when orphan checkout is already empty"
    )
    assert [line for line in commands if line.startswith("git add ")] == [
        "git add contribution-snake.svg contribution-snake-dark.svg"
    ]
    assert push_commands(workflow_text) == ["git push --force origin output"], (
        "snake workflow must force push only to output"
    )


def test_repository_has_exactly_two_workflows():
    assert {path.name for path in WORKFLOWS.iterdir() if path.is_file()} == (
        WORKFLOW_NAMES
    )


def test_daily_triggers_permissions_dependency_and_main_ref_guard():
    assert_daily_trigger_and_permission_contract(load("daily-profile.yml"))


def test_daily_uses_pinned_toolchain_and_full_quality_commands():
    assert_daily_toolchain_contract(load("daily-profile.yml"))


def test_daily_stages_stable_assets_and_only_normally_pushes_main():
    assert_daily_publication_contract(
        load("daily-profile.yml"), text("daily-profile.yml")
    )


def test_snake_generates_validates_and_only_force_pushes_output():
    assert_snake_contract(load("snake.yml"), text("snake.yml"))


def test_only_publishing_jobs_have_contents_write():
    workflows = {name: load(name) for name in WORKFLOW_NAMES}
    assert_only_publishing_jobs_write(workflows)


def test_workflows_have_exact_concurrency_and_only_repository_token():
    workflows = [load(name) for name in sorted(WORKFLOW_NAMES)]
    assert [workflow["concurrency"]["group"] for workflow in workflows] == [
        "daily-profile-main",
        "contribution-snake-output",
    ]
    assert all(
        workflow["concurrency"]["cancel-in-progress"] == "false"
        for workflow in workflows
    )

    all_text = "\n".join(text(name) for name in sorted(WORKFLOW_NAMES))
    secret_references = re.findall(r"\bsecrets\.([A-Za-z_][A-Za-z0-9_]*)\b", all_text)
    assert secret_references
    assert set(secret_references) == {"GITHUB_TOKEN"}
    token_expressions = {
        expression.strip()
        for expression in re.findall(r"\$\{\{\s*([^}]+?)\s*\}\}", all_text)
        if re.search(r"token|secret|pat", expression, flags=re.IGNORECASE)
    }
    assert token_expressions == {"secrets.GITHUB_TOKEN"}
    without_repository_token = all_text.replace("secrets.GITHUB_TOKEN", "")
    assert not re.search(
        r"\b(?:PAT|PERSONAL_ACCESS_TOKEN|CUSTOM_TOKEN|PRIVATE_TOKEN)\b",
        without_repository_token,
        flags=re.IGNORECASE,
    )

    all_pushes = [
        command
        for name in sorted(WORKFLOW_NAMES)
        for command in push_commands(text(name))
    ]
    assert all_pushes == [
        "git push origin HEAD:main",
        "git push --force origin output",
    ]


def test_daily_contract_rejects_missing_checkout_ref_pin():
    workflow = deepcopy(load("daily-profile.yml"))
    checkout = action_step(
        workflow["jobs"]["generate"],
        "actions/checkout@",
        "actions/checkout@v6",
    )
    checkout.setdefault("with", {}).pop("ref", None)
    with pytest.raises(AssertionError, match="pin ref main"):
        assert_daily_toolchain_contract(workflow)


def test_permission_contract_rejects_quality_contents_write():
    workflows = {name: deepcopy(load(name)) for name in WORKFLOW_NAMES}
    workflows["daily-profile.yml"]["jobs"]["quality"]["permissions"] = {
        "contents": "write"
    }
    with pytest.raises(AssertionError, match="only publishing jobs"):
        assert_only_publishing_jobs_write(workflows)


def test_daily_contract_rejects_another_push_target():
    workflow_text = text("daily-profile.yml").replace(
        "git push origin HEAD:main",
        "git push origin HEAD:main\n          git push origin HEAD:release",
    )
    with pytest.raises(AssertionError, match="only the normal push to main"):
        assert_daily_publication_contract(load("daily-profile.yml"), workflow_text)


def test_snake_contract_rejects_another_force_push_target():
    workflow_text = text("snake.yml").replace(
        "git push --force origin output",
        "git push --force origin output\n          git push --force origin backup",
    )
    with pytest.raises(AssertionError, match="force push only to output"):
        assert_snake_contract(load("snake.yml"), workflow_text)
