# Profile contributions

The **Update Profile Contributions** workflow checks GitHub every hour at minute 17 (UTC), and can also be run from the Actions tab. GitHub may delay scheduled runs.

The list includes public repositories owned by other accounts where the profile owner has an authored, merged pull request. Open, closed-but-unmerged, private, and self-owned work is excluded. It displays project links, star badges, and concise contribution overviews. Projects without an overview use the three latest distinct merged PR titles as a fallback. It does not display PR links or an open-PR list.

The script follows every GraphQL page, ranks projects by merged contribution count, and only edits the region between `CONTRIBUTIONS:START` and `CONTRIBUTIONS:END` in the README. Keep these markers when editing the surrounding profile. Project display names can be adjusted in `DISPLAY_NAMES` and contribution overviews in `PROJECT_SUMMARIES` in the script; new projects are discovered without adding configuration. Overviews must describe verified merged contributions. Automatic refreshes preserve these overviews while updating project membership and ordering; maintain the overview when new contributions expand its scope.

The workflow uses the repository's built-in `GITHUB_TOKEN`; no personal access token or paid service is required. API failures or invalid markers fail the run before writing the README. Unchanged results do not create commits. The write job runs only on `main`, never on pull requests.

Run the checks locally:

```sh
python3 -m unittest discover -s tests -v
```

To refresh locally, set `GH_TOKEN` to an authenticated GitHub token and run:

```sh
python3 scripts/update_contributions.py --user xu91102
```
