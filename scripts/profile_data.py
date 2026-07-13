from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from typing import Callable, Iterable
from urllib.request import Request, urlopen


GRAPHQL_URL = "https://api.github.com/graphql"
GRAPHQL_QUERY = """
query Profile($login: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      contributionCalendar { totalContributions }
    }
    repositories(first: 100, privacy: PUBLIC, ownerAffiliations: OWNER) {
      nodes {
        name
        url
        stargazerCount
        updatedAt
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
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


def parse_profile_payload(
    payload: dict, featured_names: Iterable[str], login: str = "Izumi-iii"
) -> ProfileData:
    if payload.get("errors"):
        messages = "; ".join(error.get("message", "unknown") for error in payload["errors"])
        raise ValueError(f"GitHub GraphQL error: {messages}")

    try:
        user = payload["data"]["user"]
        contributions = user["contributionsCollection"]
        repositories = user["repositories"]["nodes"]
    except (KeyError, TypeError) as exc:
        raise ValueError("GitHub GraphQL response is missing profile data") from exc

    by_name = {repo["name"]: repo for repo in repositories}
    featured_names = tuple(featured_names)
    missing = [name for name in featured_names if name not in by_name]
    if missing:
        raise ValueError(f"missing featured repositories: {', '.join(missing)}")

    language_sizes: Counter[str] = Counter()
    for repo in repositories:
        for edge in repo.get("languages", {}).get("edges", []):
            language_sizes[edge["node"]["name"]] += int(edge["size"])

    projects = tuple(
        ProjectData(
            name=name,
            url=by_name[name]["url"],
            stars=int(by_name[name]["stargazerCount"]),
            updated_at=by_name[name]["updatedAt"],
        )
        for name in featured_names
    )
    return ProfileData(
        login=login,
        commits=int(contributions["totalCommitContributions"]),
        pull_requests=int(contributions["totalPullRequestContributions"]),
        contributions=int(contributions["contributionCalendar"]["totalContributions"]),
        total_stars=sum(int(repo["stargazerCount"]) for repo in repositories),
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
    body = json.dumps({"query": GRAPHQL_QUERY, "variables": {"login": login}}).encode()
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
    return parse_profile_payload(payload, featured_names, login=login)
