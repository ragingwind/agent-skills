#!/usr/bin/env python3
"""The part of `status.py read` that runs on each project machine: for one
project, the last lines of every task's status file, in its build session's
task folder and in its testing session's tester folder, and the free space
of the home directory's disk. status.py sends this file over SSH to a remote
machine, so it uses the standard library only.

Usage: status_reader.py TASKS_ROOT TESTING_ROOT LINES

Prints one JSON object: {"tasks": {task: [lines]}, "testing": {task:
[lines]}, "free_gb": n}. A root that does not exist gives no tasks.
"""
import glob
import json
import os
import shutil
import sys


def last_lines(root, n):
    """Task -> the last n lines of `<root>/<task>/status.jsonl`."""
    out = {}
    for path in sorted(glob.glob(os.path.join(os.path.expanduser(root), "*", "status.jsonl"))):
        with open(path, encoding="utf-8", errors="replace") as f:
            out[os.path.basename(os.path.dirname(path))] = f.read().splitlines()[-n:]
    return out


def main(argv):
    if argv[:1] in (["-h"], ["--help"]):
        print(__doc__.strip())
        return 0
    if len(argv) != 3 or not argv[2].isdigit() or int(argv[2]) < 1:
        print("usage: status_reader.py TASKS_ROOT TESTING_ROOT LINES", file=sys.stderr)
        return 2
    n = int(argv[2])
    free = shutil.disk_usage(os.path.expanduser("~")).free
    print(json.dumps({"tasks": last_lines(argv[0], n), "testing": last_lines(argv[1], n),
                      "free_gb": round(free / 1024 ** 3, 1)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
