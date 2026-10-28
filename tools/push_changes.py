#!/usr/bin/env python3
"""Commit every project file to GitHub via the Git Database API, using the
registered custom.github connector helper (the token never leaves the vault).

Usage: python3 tools/push_changes.py "commit message"

Requires the repo to exist and to have at least one commit (seed it once via
the contents API). Skips data/ (market-data cache), __pycache__, .git.
"""
import base64
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.expanduser("~/workspace/custom-connectors/custom.github/bin/gh_api.py")
OWNER, REPO = "dzianisv", "trading-harness2"
SKIP_DIRS = {"data", "__pycache__", ".git"}


def api(method, path, payload=None):
    args = ["python3", HELPER, method, path]
    tmp = None
    if payload is not None:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(payload, tmp)
        tmp.close()
        args += ["--data", "@" + tmp.name]
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=120)
    finally:
        if tmp:
            os.unlink(tmp.name)
    text = out.stdout
    status_line, _, body = text.partition("\n")
    status = int(status_line.replace("HTTP", "").strip())
    if status >= 300:
        raise RuntimeError(f"{method} {path} -> HTTP {status}: {body[:400]}")
    return json.loads(body) if body.strip() else {}


def collect_files():
    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".pyc"):
                continue
            full = os.path.join(dirpath, fn)
            files.append(os.path.relpath(full, ROOT))
    return sorted(files)


def main():
    message = sys.argv[1] if len(sys.argv) > 1 else "update"
    ref = api("GET", f"/repos/{OWNER}/{REPO}/git/ref/heads/main")
    head_sha = ref["object"]["sha"]
    head_commit = api("GET", f"/repos/{OWNER}/{REPO}/git/commits/{head_sha}")
    base_tree = head_commit["tree"]["sha"]

    tree_entries = []
    for rel in collect_files():
        with open(os.path.join(ROOT, rel), "rb") as f:
            content = base64.b64encode(f.read()).decode()
        blob = api("POST", f"/repos/{OWNER}/{REPO}/git/blobs",
                   {"content": content, "encoding": "base64"})
        tree_entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})

    tree = api("POST", f"/repos/{OWNER}/{REPO}/git/trees",
               {"base_tree": base_tree, "tree": tree_entries})
    commit = api("POST", f"/repos/{OWNER}/{REPO}/git/commits",
                 {"message": message, "tree": tree["sha"], "parents": [head_sha]})
    api("PATCH", f"/repos/{OWNER}/{REPO}/git/refs/heads/main", {"sha": commit["sha"]})
    print(json.dumps({"committed": commit["sha"], "files": len(tree_entries), "message": message}))


if __name__ == "__main__":
    main()
