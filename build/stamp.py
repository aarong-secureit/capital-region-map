"""Version shown in Settings: build time to the minute and the git commit (used by inject.py and make_site.py)."""


def build_stamp():
    """Build time to the minute (UTC, which is Iceland's time all year) and the git commit, if known."""
    import datetime, os, subprocess
    t = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    sha = (os.environ.get("WORKERS_CI_COMMIT_SHA") or "")[:7]
    if not sha:
        try:
            sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                                 cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
        except OSError:
            sha = ""
    return t + (f" · {sha}" if sha else "")
