
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

USERNAME = "manish-pandey413"
README = "README.md"

START = "<!-- GITHUB_ACTIVITY_START -->"
END = "<!-- GITHUB_ACTIVITY_END -->"

API = "https://api.github.com"
TOKEN = os.environ.get("GH_TOKEN", "")


def get_json(url):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "github-profile-readme-updater",
    }

    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    request = urllib.request.Request(url, headers=headers)

    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def main():
    user = get_json(f"{API}/users/{USERNAME}")

    repositories = []
    page = 1

    # Fetch all public repositories so the star total is accurate.
    while True:
        batch = get_json(
            f"{API}/users/{USERNAME}/repos"
            f"?type=owner&sort=updated&per_page=100&page={page}"
        )

        repositories.extend(batch)

        if len(batch) < 100:
            break

        page += 1

    original_repos = [repo for repo in repositories if not repo["fork"]]

    stars = sum(repo["stargazers_count"] for repo in repositories)

    latest = max(
        repositories,
        key=lambda repo: repo.get("pushed_at") or "",
        default=None,
    )

    updated = datetime.now(timezone.utc).strftime("%d %b %Y")

    lines = [
        f"> **{user['public_repos']}** public repositories"
        f" &nbsp;·&nbsp; **{user['followers']}** followers"
        f" &nbsp;·&nbsp; **{stars}** stars across public repositories",
        "",
        f"> **{len(original_repos)}** original public repositories"
        " &nbsp;·&nbsp; **GitHub REST API**",
        "",
    ]

    if latest and latest.get("pushed_at"):
        pushed = datetime.fromisoformat(
            latest["pushed_at"].replace("Z", "+00:00")
        ).strftime("%d %b %Y")

        name = latest["name"]
        url = latest["html_url"]

        lines.extend([
            f"> Latest repository activity: [{name}]({url})",
            f"> Last pushed on {pushed}.",
            "",
        ])
    else:
        lines.extend([
            "> No public repository activity is available yet.",
            "",
        ])

    lines.append(f"<sub>Last refreshed: {updated} (UTC)</sub>")

    with open(README, "r", encoding="utf-8") as file:
        content = file.read()

    if START not in content or END not in content:
        raise ValueError("README activity markers are missing.")

    before, remainder = content.split(START, 1)
    _, after = remainder.split(END, 1)

    new_section = (
        f"{START}\n"
        + "\n".join(lines)
        + f"\n{END}"
    )

    with open(README, "w", encoding="utf-8") as file:
        file.write(before + new_section + after)

    print("GitHub activity section updated.")


if __name__ == "__main__":
    main()
