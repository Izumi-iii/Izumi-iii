from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from typing import Callable, Iterable
from urllib.request import Request, urlopen


GRAPHQL_URL = "https://api.github.com/graphql"
GRAPHQL_QUERY = """
query Profile($login: String!, $cursor: String) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      contributionCalendar { totalContributions }
    }
    repositories(first: 100, after: $cursor, privacy: PUBLIC, ownerAffiliations: OWNER) {
      nodes {
        name
        url
        stargazerCount
        updatedAt
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
""".strip()


@dataclass(frozen=True)
class ProjectData:
    name: str
    url: str
    stars: int
    updated_at: str


@dataclass(frozen=True)
class ProfileData:
    login: str
    commits: int
    pull_requests: int
    contributions: int
    total_stars: int
    languages: tuple[tuple[str, int], ...]
    projects: tuple[ProjectData, ...]


def _schema_error(context: str, detail: str) -> ValueError:
    return ValueError(f"GitHub GraphQL response schema error at {context}: {detail}")


def _mapping(value, context: str) -> dict:
    if not isinstance(value, dict):
        raise _schema_error(context, "expected an object")
    return value


def _list(value, context: str) -> list:
    if not isinstance(value, list):
        raise _schema_error(context, "expected a list")
    return value


def _field(mapping: dict, name: str, context: str):
    if name not in mapping:
        raise _schema_error(f"{context}.{name}", "missing field")
    return mapping[name]


def _text(value, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise _schema_error(context, "expected a non-empty string")
    return value


def _integer(value, context: str) -> int:
    if isinstance(value, bool):
        raise _schema_error(context, "expected an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise _schema_error(context, "expected an integer") from exc


def _raise_graphql_errors(payload: dict) -> None:
    if not payload.get("errors"):
        return
    errors = _list(payload["errors"], "errors")
    messages = []
    for index, error in enumerate(errors):
        error = _mapping(error, f"errors[{index}]")
        message = error.get("message", "unknown")
        messages.append(str(message))
    raise ValueError(f"GitHub GraphQL error: {'; '.join(messages)}")


def _profile_nodes(payload: dict) -> tuple[dict, dict, list]:
    payload = _mapping(payload, "response")
    _raise_graphql_errors(payload)
    data = _mapping(_field(payload, "data", "response"), "data")
    user = _mapping(_field(data, "user", "data"), "data.user")
    repositories = _mapping(
        _field(user, "repositories", "data.user"), "repositories"
    )
    nodes = _list(
        _field(repositories, "nodes", "repositories"), "repositories.nodes"
    )
    return user, repositories, nodes


def parse_profile_payload(
    payload: dict, featured_names: Iterable[str], login: str = "Izumi-iii"
) -> ProfileData:
    user, _, repository_nodes = _profile_nodes(payload)
    contributions = _mapping(
        _field(user, "contributionsCollection", "data.user"),
        "contributionsCollection",
    )
    commits = _integer(
        _field(
            contributions,
            "totalCommitContributions",
            "contributionsCollection",
        ),
        "contributionsCollection.totalCommitContributions",
    )
    pull_requests = _integer(
        _field(
            contributions,
            "totalPullRequestContributions",
            "contributionsCollection",
        ),
        "contributionsCollection.totalPullRequestContributions",
    )
    calendar = _mapping(
        _field(contributions, "contributionCalendar", "contributionsCollection"),
        "contributionsCollection.contributionCalendar",
    )
    contribution_total = _integer(
        _field(
            calendar,
            "totalContributions",
            "contributionsCollection.contributionCalendar",
        ),
        "contributionsCollection.contributionCalendar.totalContributions",
    )

    repositories: list[dict] = []
    language_sizes: Counter[str] = Counter()
    for repo_index, value in enumerate(repository_nodes):
        context = f"repositories.nodes[{repo_index}]"
        repo = _mapping(value, context)
        normalized = {
            "name": _text(_field(repo, "name", context), f"{context}.name"),
            "url": _text(_field(repo, "url", context), f"{context}.url"),
            "stargazerCount": _integer(
                _field(repo, "stargazerCount", context),
                f"{context}.stargazerCount",
            ),
            "updatedAt": _text(
                _field(repo, "updatedAt", context), f"{context}.updatedAt"
            ),
        }
        languages = _mapping(
            _field(repo, "languages", context), f"{context}.languages"
        )
        edges = _list(
            _field(languages, "edges", f"{context}.languages"),
            f"{context}.languages.edges",
        )
        # GitHub returns the top ten languages by byte size for each repository.
        for edge_index, value in enumerate(edges):
            edge_context = f"{context}.languages.edges[{edge_index}]"
            edge = _mapping(value, edge_context)
            size = _integer(
                _field(edge, "size", edge_context), f"{edge_context}.size"
            )
            node = _mapping(
                _field(edge, "node", edge_context), f"{edge_context}.node"
            )
            language = _text(
                _field(node, "name", f"{edge_context}.node"),
                f"{edge_context}.node.name",
            )
            language_sizes[language] += size
        repositories.append(normalized)

    by_name = {repo["name"]: repo for repo in repositories}
    featured_names = tuple(featured_names)
    missing = [name for name in featured_names if name not in by_name]
    if missing:
        raise ValueError(f"missing featured repositories: {', '.join(missing)}")

    projects = tuple(
        ProjectData(
            name=name,
            url=by_name[name]["url"],
            stars=by_name[name]["stargazerCount"],
            updated_at=by_name[name]["updatedAt"],
        )
        for name in featured_names
    )
    return ProfileData(
        login=login,
        commits=commits,
        pull_requests=pull_requests,
        contributions=contribution_total,
        total_stars=sum(repo["stargazerCount"] for repo in repositories),
        languages=tuple(language_sizes.most_common(6)),
        projects=projects,
    )


def fetch_profile(
    token: str,
    login: str,
    featured_names: Iterable[str],
    opener: Callable = urlopen,
) -> ProfileData:
    if not token:
        raise ValueError("GITHUB_TOKEN is required")
    cursor = None
    seen_cursors: set[str] = set()
    first_payload = None
    all_nodes: list[dict] = []
    while True:
        body = json.dumps(
            {
                "query": GRAPHQL_QUERY,
                "variables": {"login": login, "cursor": cursor},
            }
        ).encode()
        request = Request(
            GRAPHQL_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "Izumi-iii-profile-generator",
            },
        )
        with opener(request, timeout=30) as response:
            payload = json.load(response)
        _, connection, nodes = _profile_nodes(payload)
        if first_payload is None:
            first_payload = payload
        all_nodes.extend(nodes)

        page_info_value = connection.get("pageInfo")
        if page_info_value is None:
            break
        page_info = _mapping(page_info_value, "repositories.pageInfo")
        has_next_page = _field(
            page_info, "hasNextPage", "repositories.pageInfo"
        )
        if not isinstance(has_next_page, bool):
            raise _schema_error(
                "repositories.pageInfo.hasNextPage", "expected a boolean"
            )
        if not has_next_page:
            break
        next_cursor = _text(
            _field(page_info, "endCursor", "repositories.pageInfo"),
            "repositories.pageInfo.endCursor",
        )
        if next_cursor in seen_cursors:
            raise _schema_error(
                "repositories.pageInfo.endCursor", "cursor did not advance"
            )
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    assert first_payload is not None
    first_payload["data"]["user"]["repositories"]["nodes"] = all_nodes
    return parse_profile_payload(first_payload, featured_names, login=login)
