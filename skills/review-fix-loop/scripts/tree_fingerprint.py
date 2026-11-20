#!/usr/bin/env python3
"""Read-only uncommitted scope estimates and review fingerprints (Python 3.9+)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys


def git(repo, *args, check=True, data=None):
    result = subprocess.run(
        ["git", "-C", str(repo), *args], input=data, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    if check and result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    return result


def paths(output):
    return {p for p in output.split(b"\0") if p}


def context(repo):
    root = Path(os.fsdecode(git(repo, "rev-parse", "--show-toplevel").stdout[:-1]))
    head = git(root, "rev-parse", "--verify", "HEAD", check=False)
    base = head.stdout.strip() if head.returncode == 0 else git(
        root, "hash-object", "-t", "tree", "--stdin", data=b"").stdout.strip()
    common = ("--no-ext-diff", "--no-textconv", "--no-renames", "--ignore-submodules=none")
    staged = ("diff", *common, "--cached", os.fsdecode(base))
    unstaged = ("diff", *common)
    changed = paths(git(root, *staged, "--name-only", "-z").stdout)
    changed |= paths(git(root, *unstaged, "--name-only", "-z").stdout)
    untracked = paths(git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout)
    return root, head.stdout.strip() if head.returncode == 0 else b"no commits", staged, unstaged, changed, untracked


def file_data(root, raw):
    path = root / os.fsdecode(raw)
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return b"missing", b""
    if stat.S_ISLNK(mode):
        return str(mode).encode(), os.fsencode(os.readlink(path))
    if not stat.S_ISREG(mode):
        raise RuntimeError("Cannot capture directory or special file: " + repr(os.fsdecode(raw)))
    return str(mode).encode(), path.read_bytes()


def fingerprint(repo):
    root, head, _, _, changed, untracked = context(repo)
    digest = hashlib.sha256()

    def add(value):
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)

    add(os.fsencode(root.resolve()))
    add(head)
    # Reading the index bytes also covers staging-only changes and index flags.
    # No Git command here refreshes the index or writes objects, refs or files.
    index = Path(os.fsdecode(git(root, "rev-parse", "--git-path", "index").stdout.rstrip(b"\n")))
    if not index.is_absolute():
        index = root / index
    add(index.read_bytes() if index.exists() else b"no index")
    shared = git(root, "rev-parse", "--shared-index-path").stdout.rstrip(b"\n")
    if shared:
        shared_path = Path(os.fsdecode(shared))
        add((shared_path if shared_path.is_absolute() else root / shared_path).read_bytes())
    for raw in sorted(changed | untracked):
        add(raw)
        for value in file_data(root, raw):
            add(value)
    return digest.hexdigest()


def estimate(repo):
    root, _, staged, unstaged, changed, untracked = context(repo)
    added = removed = 0
    binary = set()
    for command in (staged, unstaged):
        for entry in git(root, *command, "--numstat", "-z").stdout.split(b"\0"):
            if not entry:
                continue
            plus, minus, raw = entry.split(b"\t", 2)
            if plus == b"-":
                binary.add(raw)
            else:
                added += int(plus)
                removed += int(minus)
    for raw in untracked:
        _, data = file_data(root, raw)
        if b"\0" in data:
            binary.add(raw)
        else:
            added += data.count(b"\n") + int(bool(data) and not data.endswith(b"\n"))
    return {"changed_files": len(changed | untracked), "added_lines": added,
            "removed_lines": removed, "binary_files": len(binary),
            "paths": [os.fsdecode(p) for p in sorted(changed | untracked)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository path (default: cwd)")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("estimate", "capture", "verify"):
        sub = commands.add_parser(name)
        sub.add_argument("--repo", default=argparse.SUPPRESS)
        if name == "verify":
            sub.add_argument("fingerprint")
    args = parser.parse_args()
    try:
        if args.command == "estimate":
            print(json.dumps(estimate(args.repo), sort_keys=True))
        elif args.command == "capture":
            print(fingerprint(args.repo))
        elif fingerprint(args.repo) != args.fingerprint:
            print("Review tree changed; discard this round.", file=sys.stderr)
            return 1
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print("Cannot inspect review tree: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
