import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.update_contributions import main


START = "<!-- CONTRIBUTIONS:START -->"
END = "<!-- CONTRIBUTIONS:END -->"
ORIGINAL = f"Intro stays.\n\n### Contributing to\n\n{START}\nOld content\n{END}\n\nStack stays.\n"


def pull_request(repo, title, merged_at="2026-11-01T12:00:00Z", private=False):
    owner, name = repo.split("/")
    return {
        "title": title,
        "merged": merged_at is not None,
        "mergedAt": merged_at,
        "repository": {
            "name": name,
            "nameWithOwner": repo,
            "isPrivate": private,
            "owner": {"login": owner},
        },
    }


def page(nodes, cursor=None):
    return {"data": {"user": {"pullRequests": {
        "nodes": nodes,
        "pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor},
    }}}}


class ProfileUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.readme = Path(self.tmp.name) / "README.md"
        self.readme.write_text(ORIGINAL, encoding="utf-8")

    def run_update(self, pages):
        responses = [io.BytesIO(json.dumps(p).encode()) for p in pages]
        with patch.dict(os.environ, {"GH_TOKEN": "test-token"}), \
                patch("urllib.request.urlopen", side_effect=responses), \
                contextlib.redirect_stdout(io.StringIO()):
            return main(["--user", "xu91102", "--readme", str(self.readme)])

    def test_shows_only_merged_public_external_projects_as_a_compact_list(self):
        self.run_update([page([
            pull_request("morluto/rea", "fix(javascript): report SVG script references"),
            pull_request("other/pending", "Pending fix", merged_at=None),
            pull_request("team/private", "Private fix", private=True),
            pull_request("xu91102/own", "Own fix"),
        ])])
        actual = self.readme.read_text(encoding="utf-8")
        self.assertIn("- **[REA](https://github.com/morluto/rea)**", actual)
        self.assertIn("img.shields.io/github/stars/morluto/rea?style=flat&color=gold", actual)
        self.assertIn("Report SVG script references.", actual)
        for forbidden in ["other/pending", "team/private", "xu91102/own", "/pull/", "Old content"]:
            self.assertNotIn(forbidden, actual)
        self.assertTrue(actual.startswith(ORIGINAL.split(START)[0]))
        self.assertTrue(actual.endswith(ORIGINAL.split(END)[1]))

    def test_new_merged_projects_are_discovered_beyond_the_first_api_page(self):
        self.run_update([
            page([pull_request("morluto/rea", "fix: Existing contribution")], cursor="next-page"),
            page([pull_request("new-team/new-project", "fix: Brand new merged contribution")]),
        ])
        actual = self.readme.read_text(encoding="utf-8")
        self.assertIn("**[new-project](https://github.com/new-team/new-project)**", actual)
        self.assertIn("Brand new merged contribution.", actual)

    def test_a_partial_graphql_failure_preserves_the_previous_profile(self):
        failure = {"data": {"user": None}, "errors": [{"message": "API temporarily unavailable"}]}
        with self.assertRaisesRegex(RuntimeError, "GitHub.*API temporarily unavailable"):
            self.run_update([
                page([pull_request("morluto/rea", "fix: Partial results")], cursor="next-page"),
                failure,
            ])
        self.assertEqual(self.readme.read_text(encoding="utf-8"), ORIGINAL)

    def test_ambiguous_marker_pairs_fail_without_changing_the_profile(self):
        invalid = ORIGINAL.replace(START, START + "\n" + START)
        self.readme.write_text(invalid, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "marker"):
            self.run_update([page([pull_request("morluto/rea", "fix: Valid data")])])
        self.assertEqual(self.readme.read_text(encoding="utf-8"), invalid)

    def test_new_merges_refresh_descriptions_and_unchanged_data_does_not_rewrite(self):
        old = pull_request("morluto/rea", "fix: Earlier merged fix")
        self.run_update([page([old])])
        newer = pull_request("morluto/rea", "fix: New merged fix", "2026-11-04T12:00:00Z")
        self.run_update([page([old, newer])])
        actual = self.readme.read_text(encoding="utf-8")
        self.assertIn("New merged fix; Earlier merged fix.", actual)
        modified = self.readme.stat().st_mtime_ns
        self.run_update([page([old, newer])])
        self.assertEqual(self.readme.stat().st_mtime_ns, modified)

    def test_titles_cannot_insert_html_or_extra_markdown_links(self):
        self.run_update([page([pull_request(
            "morluto/rea", "fix: <script>alert(1)</script> [click](javascript:alert(1))\nextra line"
        )])])
        actual = self.readme.read_text(encoding="utf-8")
        self.assertNotIn("<script>", actual)
        self.assertNotIn("[click]", actual)
        self.assertIn("&lt;script&gt;", actual)
        self.assertIn("\\[click\\]", actual)

    def test_missing_marker_does_not_change_anything(self):
        self.readme.write_text("Unmanaged README\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "marker"):
            self.run_update([])
        self.assertEqual(self.readme.read_text(encoding="utf-8"), "Unmanaged README\n")

    def test_non_advancing_pagination_fails_without_publishing_partial_data(self):
        with self.assertRaisesRegex(RuntimeError, "pagination"):
            self.run_update([
                page([pull_request("morluto/rea", "fix: First page")], cursor="repeated"),
                page([pull_request("morluto/rea", "fix: Second page")], cursor="repeated"),
            ])
        self.assertEqual(self.readme.read_text(encoding="utf-8"), ORIGINAL)


if __name__ == "__main__":
    unittest.main()
