import json
from io import BytesIO
from pathlib import Path

import pytest

from scripts.profile_data import fetch_profile, parse_profile_payload


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


@pytest.mark.parametrize(
    ("mutate", "context"),
    (
        (
            lambda payload: payload["data"]["user"]["contributionsCollection"].pop(
                "totalCommitContributions"
            ),
            "contributionsCollection.totalCommitContributions",
        ),
        (
            lambda payload: payload["data"]["user"]["repositories"]["nodes"][0].pop(
                "stargazerCount"
            ),
            "repositories.nodes[0].stargazerCount",
        ),
        (
            lambda payload: payload["data"]["user"]["repositories"]["nodes"][0][
                "languages"
            ]["edges"][0]["node"].pop("name"),
            "repositories.nodes[0].languages.edges[0].node.name",
        ),
    ),
)
def test_parse_profile_payload_wraps_nested_schema_errors_with_context(
    mutate, context
):
    payload = json.loads(FIXTURE.read_text())
    mutate(payload)

    with pytest.raises(ValueError, match=context.replace("[", r"\[").replace("]", r"\]")):
        parse_profile_payload(payload, FEATURED)


class FakeResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def test_fetch_profile_paginates_all_public_repositories():
    base = json.loads(FIXTURE.read_text())
    nodes = base["data"]["user"]["repositories"]["nodes"]
    first = json.loads(json.dumps(base))
    first["data"]["user"]["repositories"] = {
        "nodes": nodes[:2],
        "pageInfo": {"hasNextPage": True, "endCursor": "cursor-100"},
    }
    second = json.loads(json.dumps(base))
    second["data"]["user"]["repositories"] = {
        "nodes": nodes[2:],
        "pageInfo": {"hasNextPage": False, "endCursor": None},
    }
    requests = []
    pages = iter((first, second))

    def opener(request, timeout):
        assert timeout == 30
        requests.append(json.loads(request.data))
        return FakeResponse(json.dumps(next(pages)).encode())

    profile = fetch_profile("token", "Izumi-iii", FEATURED, opener=opener)

    assert tuple(project.name for project in profile.projects) == FEATURED
    assert [request["variables"] for request in requests] == [
        {"login": "Izumi-iii", "cursor": None},
        {"login": "Izumi-iii", "cursor": "cursor-100"},
    ]


def test_fetch_profile_treats_fixture_without_page_info_as_last_page():
    requests = []

    def opener(request, timeout):
        requests.append(request)
        return FakeResponse(FIXTURE.read_bytes())

    fetch_profile("token", "Izumi-iii", FEATURED, opener=opener)

    assert len(requests) == 1


def test_fetch_profile_rejects_next_page_without_cursor():
    payload = json.loads(FIXTURE.read_text())
    payload["data"]["user"]["repositories"]["pageInfo"] = {
        "hasNextPage": True,
        "endCursor": None,
    }

    def opener(request, timeout):
        return FakeResponse(json.dumps(payload).encode())

    with pytest.raises(ValueError, match="repositories.pageInfo.endCursor"):
        fetch_profile("token", "Izumi-iii", FEATURED, opener=opener)
