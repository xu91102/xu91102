"""Refresh the profile's contribution list from merged public pull requests."""

import argparse
import html
import json
import os
from pathlib import Path
import re
import urllib.request


START = "<!-- CONTRIBUTIONS:START -->"
END = "<!-- CONTRIBUTIONS:END -->"
DISPLAY_NAMES = {
    "morluto/rea": "REA",
    "larksuite/cli": "Lark CLI",
    "docsifyjs/docsify": "Docsify",
    "nicolargo/glances": "Glances",
    "cheeriojs/cheerio": "Cheerio",
    "markedjs/marked": "Marked",
    "nexu-io/open-design": "Open Design",
}
QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    pullRequests(first: 100, after: $cursor, states: MERGED) {
      nodes {
        title merged mergedAt
        repository { name nameWithOwner isPrivate owner { login } }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""


def fetch_merged_prs(user, token):
    prs = []
    cursor = None
    seen_cursors = set()
    while True:
        request = urllib.request.Request(
            "https://api.github.com/graphql",
            data=json.dumps({"query": QUERY, "variables": {"login": user, "cursor": cursor}}).encode(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "profile-contributions",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        if payload.get("errors"):
            messages = "; ".join(error["message"] for error in payload["errors"])
            raise RuntimeError(f"GitHub query failed: {messages}")
        if not (payload.get("data") or {}).get("user"):
            raise RuntimeError(f"GitHub user not found: {user}")
        connection = payload["data"]["user"]["pullRequests"]
        prs.extend(connection["nodes"])
        page_info = connection["pageInfo"]
        if not page_info["hasNextPage"]:
            return prs
        cursor = page_info["endCursor"]
        if not cursor or cursor in seen_cursors:
            raise RuntimeError("GitHub pagination did not advance; keeping the previous profile")
        seen_cursors.add(cursor)


def plain_markdown(text):
    text = html.escape(" ".join(text.split()), quote=False)
    return re.sub(r"([\\`*_\[\]])", r"\\\1", text)


def contribution_summary(prs):
    titles = []
    for pr in sorted(prs, key=lambda pr: pr["mergedAt"], reverse=True):
        title = re.sub(
            r"^(?:feat|fix|docs|test|chore|refactor|perf|style|build|ci|revert)(?:\([^)]*\))?!?:\s*",
            "", pr["title"], flags=re.IGNORECASE,
        ).strip().rstrip(".")
        if not title:
            continue
        title = title[0].upper() + title[1:]
        title = title if len(title) <= 140 else title[:137].rstrip() + "…"
        if title not in titles:
            titles.append(title)
        if len(titles) == 3:
            break
    return plain_markdown("; ".join(titles) + ".")


def render_contributions(prs, user):
    projects = {}
    for pr in prs:
        repo = pr["repository"]
        if not pr["merged"] or not pr["mergedAt"] or repo["isPrivate"]:
            continue
        if repo["owner"]["login"].casefold() == user.casefold():
            continue
        projects.setdefault(repo["nameWithOwner"], []).append(pr)
    lines = []
    for full_name, merged_prs in sorted(projects.items(), key=lambda item: (-len(item[1]), item[0].casefold())):
        name = DISPLAY_NAMES.get(full_name, merged_prs[0]["repository"]["name"])
        url = f"https://github.com/{full_name}"
        badge = f"https://img.shields.io/github/stars/{full_name}?style=flat&color=gold"
        lines.append(
            f"- **[{plain_markdown(name)}]({url})** "
            f"[![GitHub stars]({badge})]({url}) - {contribution_summary(merged_prs)}"
        )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", required=True)
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    args = parser.parse_args(argv)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("GH_TOKEN or GITHUB_TOKEN is required")
    original = args.readme.read_text(encoding="utf-8")
    if original.count(START) != 1 or original.count(END) != 1 or original.index(START) > original.index(END):
        raise ValueError("README must contain one correctly ordered contribution marker pair")
    before, remaining = original.split(START, 1)
    _, after = remaining.split(END, 1)
    content = render_contributions(fetch_merged_prs(args.user, token), args.user)
    updated = before + START + "\n" + content + "\n" + END + after
    if updated != original:
        args.readme.write_text(updated, encoding="utf-8")
        print("Updated the contribution list.")
    else:
        print("The contribution list is unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
