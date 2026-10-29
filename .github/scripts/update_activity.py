
import json
import os
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

USERNAME = "manish-pandey413"
README = "README.md"

START = "<!-- GITHUB_ACTIVITY_START -->"
END = "<!-- GITHUB_ACTIVITY_END -->"

API = "https://api.github.com"
API_VERSION = "2026-03-10"
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")

# Set to True to include forked repositories in language percentages.
INCLUDE_FORKS_IN_LANGUAGES = False

# Number of language percentages displayed on each line.
LANGUAGES_PER_LINE = 4


def request_json(url, payload=None):
    """Make an authenticated GitHub API request and return JSON."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "github-profile-readme-updater",
    }

    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub API returned HTTP {exc.code}: {details}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not connect to the GitHub API: {exc.reason}"
        ) from exc


def get_json(url):
    return request_json(url)


def post_graphql(query):
    """Execute a GitHub GraphQL query."""
    if not TOKEN:
        raise RuntimeError(
            "GH_TOKEN is required for GraphQL requests. "
            "Set GH_TOKEN in your environment or GitHub Actions."
        )

    result = request_json(
        f"{API}/graphql",
        payload={"query": query},
    )

    if result.get("errors"):
        messages = "; ".join(
            error.get("message", "Unknown GraphQL error")
            for error in result["errors"]
        )
        raise RuntimeError(f"GitHub GraphQL error: {messages}")

    if "data" not in result:
        raise RuntimeError("GitHub GraphQL returned no data.")

    return result["data"]


def get_user():
    return get_json(f"{API}/users/{USERNAME}")


def get_all_repositories():
    """Fetch all public repositories owned by the profile."""
    repositories = []
    page = 1

    while True:
        params = urlencode({
            "type": "owner",
            "sort": "updated",
            "per_page": 100,
            "page": page,
        })

        batch = get_json(
            f"{API}/users/{USERNAME}/repos?{params}"
        )

        if not batch:
            break

        repositories.extend(batch)

        if len(batch) < 100:
            break

        page += 1

    return repositories


def get_language_bytes(repositories):
    """
    Aggregate GitHub's language byte counts across repositories.
    Forks are excluded by default.
    """
    totals = defaultdict(int)

    if INCLUDE_FORKS_IN_LANGUAGES:
        selected_repositories = repositories
    else:
        selected_repositories = [
            repo for repo in repositories
            if not repo.get("fork", False)
        ]

    for repo in selected_repositories:
        languages_url = repo.get("languages_url")

        if not languages_url:
            continue

        language_data = get_json(languages_url)

        for language, byte_count in language_data.items():
            totals[language] += int(byte_count)

    return dict(totals)


def get_all_time_contributions(created_at, now):
    """
    Sum GitHub contribution-graph commit and PR totals year by year.

    Each contributionsCollection query uses a maximum one-year window.
    The current year is counted only up to 'now'.
    """
    created = datetime.fromisoformat(
        created_at.replace("Z", "+00:00")
    ).astimezone(timezone.utc)

    year_aliases = []
    years = list(range(created.year, now.year + 1))

    for year in years:
        if year == created.year:
            start = created
        else:
            start = datetime(year, 1, 1, tzinfo=timezone.utc)

        next_year = datetime(
            year + 1, 1, 1, tzinfo=timezone.utc
        )

        end = min(
            now,
            next_year - timedelta(seconds=1),
        )

        start_text = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_text = end.strftime("%Y-%m-%dT%H:%M:%SZ")

        year_aliases.append(
            f"""
            y{year}: contributionsCollection(
                from: "{start_text}"
                to: "{end_text}"
            ) {{
                totalCommitContributions
                totalPullRequestContributions
            }}
            """
        )

    login = json.dumps(USERNAME)

    query = f"""
    query {{
        user(login: {login}) {{
            {"".join(year_aliases)}
        }}
    }}
    """

    data = post_graphql(query)
    contribution_data = data.get("user")

    if not contribution_data:
        raise RuntimeError(
            f"Could not retrieve contribution data for {USERNAME}."
        )

    total_commits = 0
    total_pull_requests = 0

    for year in years:
        year_data = contribution_data.get(f"y{year}")

        if year_data is None:
            raise RuntimeError(
                f"Contribution data missing for year {year}."
            )

        total_commits += year_data["totalCommitContributions"]
        total_pull_requests += (
            year_data["totalPullRequestContributions"]
        )

    return total_commits, total_pull_requests


def format_language_percentages(language_bytes):
    """Convert byte counts into language percentages."""
    total_bytes = sum(language_bytes.values())

    if total_bytes == 0:
        return []

    ordered = sorted(
        language_bytes.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    return [
        (language, byte_count / total_bytes * 100)
        for language, byte_count in ordered
    ]


def build_activity_section(
    user,
    repositories,
    language_bytes,
    total_commits,
    total_pull_requests,
    now,
):
    original_repositories = [
        repo for repo in repositories
        if not repo.get("fork", False)
    ]

    stars = sum(
        repo.get("stargazers_count", 0)
        for repo in repositories
    )

    public_repositories = user.get(
        "public_repos", len(repositories)
    )
    followers = user.get("followers", 0)

    lines = [
        (
            f"> **{public_repositories:,}** public repositories"
            f" &nbsp;·&nbsp; **{followers:,}** followers"
            f" &nbsp;·&nbsp; **{stars:,}** stars<br/>"
        ),
        (
            f"> **{len(original_repositories):,}** original repositories"
            f" &nbsp;·&nbsp; **{total_commits:,}** commits"
            f" &nbsp;·&nbsp; **{total_pull_requests:,}** "
            f"pull requests opened<br/>"
        ),
        (
            "> **language mix** "
            "<sub>(code-byte share across original public repositories)</sub>"
            "<br/>"
        ),
    ]

    percentages = format_language_percentages(language_bytes)

    if percentages:
        for index in range(0, len(percentages), LANGUAGES_PER_LINE):
            chunk = percentages[
                index:index + LANGUAGES_PER_LINE
            ]

            language_line = " &nbsp;·&nbsp; ".join(
                f"`{language}` {percentage:.1f}%"
                for language, percentage in chunk
            )

            lines.append(f"> {language_line}<br/>")
    else:
        lines.append("> No language data available.<br/>")

    # Latest push among original public repositories.
    latest = max(
        original_repositories,
        key=lambda repo: repo.get("pushed_at") or "",
        default=None,
    )

    if latest and latest.get("pushed_at"):
        pushed = datetime.fromisoformat(
            latest["pushed_at"].replace("Z", "+00:00")
        ).strftime("%d %b %Y")

        lines.append(
            f"> latest push · "
            f"[{latest['name']}]({latest['html_url']})"
            f" · {pushed}<br/>"
        )

    refreshed = now.strftime("%d %b %Y, %H:%M UTC")

    lines.append(
        f"> <sub>last refreshed {refreshed} · "
        "GitHub REST + GraphQL APIs</sub>"
    )

    return "\n".join(lines)


def update_readme(section):
    with open(README, "r", encoding="utf-8") as file:
        content = file.read()

    if START not in content or END not in content:
        raise ValueError(
            "README activity markers are missing. "
            "Keep both GITHUB_ACTIVITY markers in README.md."
        )

    before, remainder = content.split(START, 1)
    _, after = remainder.split(END, 1)

    new_section = f"{START}\n{section}\n{END}"

    with open(README, "w", encoding="utf-8", newline="\n") as file:
        file.write(before + new_section + after)


def main():
    now = datetime.now(timezone.utc)

    user = get_user()
    repositories = get_all_repositories()

    language_bytes = get_language_bytes(repositories)

    total_commits, total_pull_requests = (
        get_all_time_contributions(
            user["created_at"],
            now,
        )
    )

    section = build_activity_section(
        user=user,
        repositories=repositories,
        language_bytes=language_bytes,
        total_commits=total_commits,
        total_pull_requests=total_pull_requests,
        now=now,
    )

    update_readme(section)
    print("GitHub activity section updated successfully.")


if __name__ == "__main__":
    main()
