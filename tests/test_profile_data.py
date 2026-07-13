import json
from pathlib import Path

import pytest

from scripts.profile_data import parse_profile_payload


FIXTURE = Path("tests/fixtures/github-profile.json")
FEATURED = ("magicState", "downing_detect", "Algorithm")


def test_parse_profile_payload_aggregates_public_data():
    payload = json.loads(FIXTURE.read_text())
    profile = parse_profile_payload(payload, FEATURED)

    assert profile.login == "Izumi-iii"
    assert profile.commits == 42
    assert profile.pull_requests == 7
    assert profile.contributions == 81
    assert profile.total_stars == 10
    assert profile.languages == (("Python", 1200), ("C++", 800), ("Swift", 700))
    assert tuple(project.name for project in profile.projects) == FEATURED


def test_parse_profile_payload_rejects_missing_featured_repo():
    payload = json.loads(FIXTURE.read_text())
    payload["data"]["user"]["repositories"]["nodes"] = []

    with pytest.raises(ValueError, match="missing featured repositories"):
        parse_profile_payload(payload, FEATURED)


def test_parse_profile_payload_surfaces_graphql_errors():
    with pytest.raises(ValueError, match="GitHub GraphQL error"):
        parse_profile_payload({"errors": [{"message": "bad token"}]}, FEATURED)
