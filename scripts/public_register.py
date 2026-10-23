#!/usr/bin/env python3
"""Build the public mirror's register.jsonl from the source register.

    python3 scripts/public_register.py <source register.jsonl> <mirror register.jsonl> <out>

Rule of 22 Oct 2026 (Kevin, option a): lines already published in the mirror are never
changed — the mirror is append-only like the source, so each one is copied back byte for byte.
Lines published from now on carry the public fields only: the internal `notes` field is
replaced by a fixed marker, so the line still passes the mirror's validator (notes is a
required field) and says plainly that something was withheld. Grades and annotations are
public and are copied whole by publish_register.sh, not by this script.

Refuses: a mirror line whose id is not in the source; a mirror line that is neither the
source line nor its public projection (the mirror would no longer describe the source); a
mirror whose lines are not the source's in the same order.
"""
import json
import pathlib
import sys

WITHHELD = "(Withheld from the public mirror from 2026-10-22: internal notes. See README, 'Public mirror'.)"
INTERNAL = ["notes"]


def project(obj):
    out = dict(obj)
    for k in INTERNAL:
        if k in out:
            out[k] = WITHHELD
    return json.dumps(out, ensure_ascii=False)


def main(src, mirror, dest):
    src_lines = [l for l in pathlib.Path(src).read_text().splitlines() if l.strip()]
    mp = pathlib.Path(mirror)
    old = [l for l in mp.read_text().splitlines() if l.strip()] if mp.exists() else []
    src_by_id = {json.loads(l)["id"]: l for l in src_lines}
    order = [json.loads(l)["id"] for l in src_lines]
    old_ids = [json.loads(l)["id"] for l in old]
    if old_ids != order[:len(old_ids)]:
        sys.exit("public_register: the mirror's lines are not the source's, in the same order — refusing")
    for l, i in zip(old, old_ids):
        if i not in src_by_id:
            sys.exit("public_register: mirror has %s, which the source does not — refusing" % i)
        if l != src_by_id[i] and l != project(json.loads(src_by_id[i])):
            sys.exit("public_register: mirror line %s no longer matches the source — refusing" % i)
    out = old + [project(json.loads(l)) for l in src_lines[len(old):]]
    pathlib.Path(dest).write_text("\n".join(out) + "\n")
    print("public_register: %d line(s) kept as published, %d new line(s) with public fields only"
          % (len(old), len(out) - len(old)))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
