#!/usr/bin/env python3
"""Commit-reveal for register entries whose number is sealed while readers forecast.

A sealed entry is logged with `"probability": null` and
`"probability_commitment": "sha256:<hex>"`, where the hash is

    sha256("<entry id>|<probability to four decimals>|<salt>")

The probability and the salt are published later, as one line in register/reveals.jsonl (append
only). Anyone can recompute the hash and see that the number was fixed on the day the entry was
logged. The salt is what makes the hash unguessable: a probability has only so many values.

`apply(claims)` is the one place the rest of the code learns a sealed entry's number. It returns
the claims with `probability` filled in where a reveal exists, and it stops everything if a
reveal does not match its commitment. Until then the number is None and the entry cannot be
graded or scored. A commitment that can never be revealed (the salt is lost) is closed with a
public `void_commitment` annotation and scored as a Brier of 1.0: `voided(...)` lists those.
"""
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
REVEALS = ROOT / "register" / "reveals.jsonl"
ANNOTATIONS = ROOT / "register" / "annotations.jsonl"
COMMITMENT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
VOID_TYPE = "void_commitment"
VOID_TEXT = "void: commitment unverifiable"
VOID_BRIER = 1.0


def _jsonl(path):
    path = pathlib.Path(path)
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip() and not l.lstrip().startswith("#")]


def digest(entry_id, probability, salt):
    return "sha256:" + hashlib.sha256(("%s|%.4f|%s" % (entry_id, float(probability), salt)).encode()).hexdigest()


def is_sealed(claim):
    return claim.get("probability") is None and bool(claim.get("probability_commitment"))


def reveals(path=None):
    return {r["entry_id"]: r for r in _jsonl(path or REVEALS)}


def voided(claims, annotations_path=None):
    """Ids of sealed entries closed as unverifiable. Each is scored VOID_BRIER."""
    sealed = {c["id"] for c in claims if c.get("probability_commitment")}
    return sorted({a.get("entry_id") for a in _jsonl(annotations_path or ANNOTATIONS)
                   if a.get("type") == VOID_TYPE and a.get("entry_id") in sealed})


def check(claims, reveals_path=None, annotations_path=None):
    """Every problem with the reveals file, as a list of strings. Empty means it is sound."""
    errors, by_id, seen = [], {c["id"]: c for c in claims}, set()
    void = set(voided(claims, annotations_path))
    for i, r in enumerate(_jsonl(reveals_path or REVEALS), 1):
        eid = r.get("entry_id")
        where = "reveals line %d (%s)" % (i, eid)
        c = by_id.get(eid)
        if c is None:
            errors.append(where + ": no such register entry"); continue
        if eid in seen:
            errors.append(where + ": a second reveal for the same entry"); continue
        seen.add(eid)
        if not c.get("probability_commitment"):
            errors.append(where + ": the entry carries no commitment to reveal"); continue
        if eid in void:
            errors.append(where + ": the entry was already closed as unverifiable"); continue
        p, salt = r.get("probability"), r.get("salt")
        if isinstance(p, bool) or not isinstance(p, (int, float)) or not (0.0 < float(p) < 1.0):
            errors.append(where + ": probability must be a number strictly between 0 and 1"); continue
        if not isinstance(salt, str) or len(salt) < 32:
            errors.append(where + ": salt is missing or too short"); continue
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(r.get("date", ""))):
            errors.append(where + ": date is not an ISO date"); continue
        if digest(eid, p, salt) != c["probability_commitment"]:
            errors.append(where + ": probability and salt do not hash to the entry's commitment")
    return errors


def apply(claims, reveals_path=None, annotations_path=None):
    """The claims with revealed numbers filled in. Exits if any reveal fails its commitment."""
    errors = check(claims, reveals_path, annotations_path)
    if errors:
        sys.exit("commitments: the reveals file does not match the register:\n  " + "\n  ".join(errors))
    rv, out = reveals(reveals_path), []
    for c in claims:
        if is_sealed(c) and c["id"] in rv:
            c = dict(c, probability=float(rv[c["id"]]["probability"]), _revealed=rv[c["id"]])
        out.append(c)
    return out


if __name__ == "__main__":
    rows = _jsonl(ROOT / "register" / "register.jsonl")
    problems = check(rows)
    sealed = [c["id"] for c in rows if c.get("probability_commitment")]
    print("commitments: %d sealed entr%s, %d revealed, %d void%s" % (
        len(sealed), "y" if len(sealed) == 1 else "ies", len([i for i in sealed if i in reveals()]), len(voided(rows)),
        "" if not problems else "\n  " + "\n  ".join(problems)))
    sys.exit(1 if problems else 0)
