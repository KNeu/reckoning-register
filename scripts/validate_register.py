#!/usr/bin/env python3
"""Validate a claim register JSONL file against the schema in register/README.md.

Usage:
    python3 scripts/validate_register.py [path ...]

Defaults to register/register.jsonl. Draft files (issues/NN/register-drafts.jsonl) are
valid inputs too: they are expected to carry probability "TBD_KEVIN", which is legal in a
draft and illegal in the live register. Pass --live to enforce the stricter rule.

Exit 0 if every line validates, 1 otherwise. Errors are reported with line numbers.
"""

import argparse
import json
import re
import sys
from datetime import date

REQUIRED = [
    "id", "issue", "date_logged", "claim", "probability",
    "resolution_date", "falsifier", "resolution_source",
    "status", "resolved_on", "brier", "notes", "sector", "method",
]
METHODS = {"MC": "inputs", "RC": "reference_class"}
# The publication covers three sectors (13 Sep 2026). Every claim names one, or "cross" where
# the claim genuinely spans them; the calibration page reports Brier by sector.
SECTORS = {"space", "defense", "energy", "cross"}
# claim_es / falsifier_es carry the Spanish edition's wording for the same claim. They are
# optional because an entry may be logged before the translation exists — but once present they
# are part of the record and locked by the same append-only rule as the English.
# resolution_urls: the concrete pages scripts/snapshot_resolution_sources.py archives and renders
# as evidence; resolution_source stays the reader-facing prose.
OPTIONAL = ["supersedes", "claim_es", "falsifier_es", "resolution_urls", "inputs", "reference_class"]
STATUSES = {"open", "resolved_true", "resolved_false", "void"}
RESOLVED = {"resolved_true", "resolved_false"}

ID_RE = re.compile(r"^\d{4}-\d{2}-\d{3}$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TBD = "TBD_KEVIN"

# Adjectives that do quantitative work without a number. See the claim wording test.
WEASEL = [
    "significant", "significantly", "meaningful", "meaningfully", "widespread",
    "successful", "successfully", "substantial", "substantially", "major",
    "considerable", "robust", "strong", "several", "many", "few",
]


def iso_ok(v):
    if not isinstance(v, str) or not ISO_RE.match(v):
        return False
    try:
        date.fromisoformat(v)
        return True
    except ValueError:
        return False


def check(obj, lineno, live, seen_ids, errors):
    def err(msg):
        errors.append(f"  line {lineno}: {msg}")

    if not isinstance(obj, dict):
        err("not a JSON object")
        return

    for f in REQUIRED:
        if f not in obj:
            err(f"missing required field '{f}'")
    unknown = set(obj) - set(REQUIRED) - set(OPTIONAL)
    if unknown:
        err(f"unknown field(s): {', '.join(sorted(unknown))}")
    if any(f not in obj for f in REQUIRED):
        return

    if not ID_RE.match(str(obj["id"])):
        err(f"id {obj['id']!r} is not YYYY-MM-NNN")
    if obj["id"] in seen_ids:
        err(f"duplicate id {obj['id']!r} (first seen line {seen_ids[obj['id']]})")
    else:
        seen_ids[obj["id"]] = lineno

    if not isinstance(obj["issue"], str) or not obj["issue"].isdigit():
        err(f"issue {obj['issue']!r} must be a zero-padded numeric string, e.g. \"01\"")

    for f in ("date_logged", "resolution_date"):
        if not iso_ok(obj[f]):
            err(f"{f} {obj[f]!r} is not an ISO 8601 date")

    if iso_ok(obj["date_logged"]) and iso_ok(obj["resolution_date"]):
        if date.fromisoformat(obj["resolution_date"]) <= date.fromisoformat(obj["date_logged"]):
            err("resolution_date must be after date_logged")

    p = obj["probability"]
    if p == TBD:
        if live:
            err(f"probability is {TBD}: Kevin must set a number before this enters the live register")
    elif isinstance(p, bool) or not isinstance(p, (int, float)):
        err(f"probability {p!r} must be a number in [0,1] or the string {TBD!r}")
    elif not (0.0 <= float(p) <= 1.0):
        err(f"probability {p} out of range [0,1]")
    elif float(p) in (0.0, 1.0):
        err(f"probability {p} is a certainty; a calibrated forecast is never exactly 0 or 1")

    for f in ("claim", "falsifier", "resolution_source"):
        v = obj[f]
        if not isinstance(v, str) or not v.strip():
            err(f"{f} must be a non-empty string")
    if isinstance(obj["claim"], str):
        if obj["claim"].strip() and obj["claim"].strip()[-1] not in ".?":
            err("claim should be one complete sentence ending in a period")
        found = [w for w in WEASEL if re.search(rf"\b{w}\b", obj["claim"], re.I)]
        if found:
            err(f"claim contains unquantified adjective(s): {', '.join(found)} — see claim wording test")
    if isinstance(obj["falsifier"], str) and len(obj["falsifier"].split()) < 6:
        err("falsifier looks too short to be observable, dated and sourced")

    ru = obj.get("resolution_urls")
    if ru is not None and (not isinstance(ru, list) or not ru or
                           any(not isinstance(u, str) or not u.startswith("https://") for u in ru)):
        err("resolution_urls must be a non-empty list of https:// URLs")

    m = obj["method"]
    if m not in METHODS:
        err(f"method {m!r} not in {sorted(METHODS)}")
    else:
        need = METHODS[m]; other = "reference_class" if need == "inputs" else "inputs"
        if not isinstance(obj.get(need), str) or not obj.get(need, "").strip():
            err(f"method {m} requires a non-empty '{need}' line")
        if obj.get(other):
            err(f"method {m} must not carry '{other}' — exactly one method, one sub-field")

    if obj["sector"] not in SECTORS:
        err(f"sector {obj['sector']!r} not in {sorted(SECTORS)}")

    st = obj["status"]
    if st not in STATUSES:
        err(f"status {st!r} not in {sorted(STATUSES)}")
        return

    if st in RESOLVED:
        if not iso_ok(obj["resolved_on"]):
            err(f"status {st} requires an ISO resolved_on date")
        if not isinstance(obj["brier"], (int, float)) or isinstance(obj["brier"], bool):
            err(f"status {st} requires a numeric brier score")
        elif not (0.0 <= float(obj["brier"]) <= 1.0):
            err(f"brier {obj['brier']} out of range [0,1]")
        elif isinstance(p, (int, float)) and not isinstance(p, bool):
            outcome = 1.0 if st == "resolved_true" else 0.0
            expect = round((float(p) - outcome) ** 2, 6)
            if abs(float(obj["brier"]) - expect) > 1e-6:
                err(f"brier {obj['brier']} != (p - outcome)^2 = {expect}")
    else:
        if obj["resolved_on"] is not None:
            err(f"status {st} requires resolved_on to be null")
        if obj["brier"] is not None:
            err(f"status {st} requires brier to be null")
        if st == "void" and not str(obj["notes"]).strip():
            err("void requires a note explaining why the claim became ungradeable")

    if "supersedes" in obj and not ID_RE.match(str(obj["supersedes"])):
        err(f"supersedes {obj['supersedes']!r} is not a valid id")

    if not isinstance(obj["notes"], str):
        err("notes must be a string (may be empty)")


def check_supersession(entries, errors):
    """Supersession is a correction window, not an escape hatch. See register/README.md rule 7."""
    superseded_by = {}
    for eid, (lineno, obj) in entries.items():
        target = obj.get("supersedes")
        if not target:
            continue
        target = str(target)

        if target == eid:
            errors.append(f"  line {lineno}: entry {eid} supersedes itself")
            continue
        if target not in entries:
            errors.append(f"  line {lineno}: supersedes {target!r}, which is not in this file")
            continue
        if target in superseded_by:
            errors.append(
                f"  line {lineno}: {target} is already superseded by {superseded_by[target]}. "
                f"One correction only — an unsalvageable claim is 'void', not superseded twice")
            continue
        superseded_by[target] = eid

        _, orig = entries[target]
        if orig.get("status") in RESOLVED:
            errors.append(
                f"  line {lineno}: cannot supersede {target}, which is already {orig['status']}. "
                f"A revised view after resolution is a new independent entry, not a correction")

        # the correction window: same issue, or the one immediately after
        try:
            oi, ni = int(str(orig["issue"])), int(str(obj["issue"]))
        except (KeyError, ValueError):
            continue
        if ni not in (oi, oi + 1):
            errors.append(
                f"  line {lineno}: {eid} (issue {ni:02d}) supersedes {target} (issue {oi:02d}). "
                f"The correction window is the same issue or the next one. "
                f"A changed probability outside it is a NEW entry with no 'supersedes' field, "
                f"and both entries score — see register/README.md rule 7")


# ---------------------------------------------------------------- grades

GRADE_REQUIRED = ["entry_id", "graded_on", "outcome", "brier", "observation", "evidence"]
# archived_evidence: Wayback copy of the evidence. note: Kevin's <= 120 words. graded_by: who.
# (Added 13 Sep 2026, prompt 15-C; scripts/grade.py writes all three.)
GRADE_OPTIONAL = ["evidence_sha256", "archived_evidence", "note", "graded_by"]
OUTCOMES = {"resolved_true", "resolved_false", "void"}


def validate_grades(grades_path, register_path):
    """Grades live in their own append-only file; claims are byte-immutable once committed."""
    errors = []
    claims = {}
    try:
        for raw in open(register_path):
            if raw.strip():
                try:
                    o = json.loads(raw)
                    claims[str(o.get("id"))] = o
                except json.JSONDecodeError:
                    pass
    except FileNotFoundError:
        pass

    try:
        lines = open(grades_path).readlines()
    except FileNotFoundError:
        print(f"{grades_path}: not found", file=sys.stderr)
        return 1

    seen = {}
    count = 0
    for i, raw in enumerate(lines, 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        count += 1
        def err(m): errors.append(f"  line {i}: {m}")
        try:
            g = json.loads(raw)
        except json.JSONDecodeError as e:
            err(f"invalid JSON: {e}"); continue

        for f in GRADE_REQUIRED:
            if f not in g:
                err(f"missing required field '{f}'")
        unknown = set(g) - set(GRADE_REQUIRED) - set(GRADE_OPTIONAL)
        if unknown:
            err(f"unknown field(s): {', '.join(sorted(unknown))}")
        if any(f not in g for f in GRADE_REQUIRED):
            continue

        eid = str(g["entry_id"])
        if eid in seen:
            err(f"{eid} already graded on line {seen[eid]}. One grade per claim, permanently — "
                f"a regrade would be the score managing itself")
            continue
        seen[eid] = i

        claim = claims.get(eid)
        if claim is None:
            err(f"entry_id {eid!r} is not in {register_path}"); continue

        if not iso_ok(g["graded_on"]):
            err(f"graded_on {g['graded_on']!r} is not an ISO date")
        elif iso_ok(claim.get("resolution_date", "")):
            if date.fromisoformat(g["graded_on"]) < date.fromisoformat(claim["resolution_date"]):
                err(f"graded_on {g['graded_on']} precedes the claim's resolution_date "
                    f"{claim['resolution_date']}. Grade on the date, not before it")

        if g["outcome"] not in OUTCOMES:
            err(f"outcome {g['outcome']!r} not in {sorted(OUTCOMES)}"); continue

        for f in ("observation", "evidence"):
            if not isinstance(g[f], str) or not g[f].strip():
                err(f"{f} must be a non-empty string")

        p = claim.get("probability")
        if g["outcome"] == "void":
            if g["brier"] is not None:
                err("void grades carry brier null and are excluded from the running mean")
            if len(str(g["observation"]).split()) < 6:
                err("void requires an observation explaining what made the claim ungradeable")
        else:
            if isinstance(p, (int, float)) and not isinstance(p, bool):
                outcome = 1.0 if g["outcome"] == "resolved_true" else 0.0
                expect = round((float(p) - outcome) ** 2, 6)
                if not isinstance(g["brier"], (int, float)) or isinstance(g["brier"], bool):
                    err("brier must be numeric for a resolved grade")
                elif abs(float(g["brier"]) - expect) > 1e-6:
                    err(f"brier {g['brier']} != (p - outcome)^2 = {expect}, "
                        f"recomputed from the claim's own probability {p}")
            else:
                err(f"claim {eid} has no numeric probability, so it cannot be graded")

        if g.get("note") is not None:
            if not isinstance(g["note"], str) or not g["note"].strip():
                err("note, when present, must be a non-empty string")
            elif len(g["note"].split()) > 120:
                err(f"note is {len(g['note'].split())} words; the limit is 120")
        if g.get("archived_evidence") is not None and not str(g["archived_evidence"]).startswith("https://web.archive.org/"):
            err("archived_evidence must be a web.archive.org URL")
        if g.get("graded_by") is not None and (not isinstance(g["graded_by"], str) or not g["graded_by"].strip()):
            err("graded_by, when present, must be a non-empty string")

        if "evidence_sha256" in g and g["evidence_sha256"] is not None:
            h = str(g["evidence_sha256"])
            if len(h) != 64 or any(c not in "0123456789abcdef" for c in h.lower()):
                err("evidence_sha256 must be 64 hex characters")

    ungraded = [k for k in claims if k not in seen]
    if errors:
        print(f"{grades_path}: FAIL ({count} grade(s))")
        print("\n".join(errors))
        return 1
    print(f"{grades_path}: OK ({count} grade(s), {len(ungraded)} claim(s) still open)")
    return 0


def validate(path, live):
    errors = []
    seen_ids = {}
    entries = {}
    try:
        with open(path) as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        print(f"{path}: not found", file=sys.stderr)
        return 1

    count = 0
    for i, raw in enumerate(lines, 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        count += 1
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as e:
            errors.append(f"  line {i}: invalid JSON: {e}")
            continue
        check(obj, i, live, seen_ids, errors)
        if isinstance(obj, dict) and "id" in obj:
            entries[str(obj["id"])] = (i, obj)

    check_supersession(entries, errors)

    label = "live" if live else "draft"
    if errors:
        print(f"{path}: FAIL ({count} entr{'y' if count == 1 else 'ies'}, {label} rules)")
        print("\n".join(errors))
        return 1
    print(f"{path}: OK ({count} entr{'y' if count == 1 else 'ies'}, {label} rules)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", default=None)
    ap.add_argument("--live", action="store_true",
                    help="enforce live-register rules (probability must be a number)")
    ap.add_argument("--grades", action="store_true",
                    help="validate register/grades.jsonl against register/register.jsonl")
    args = ap.parse_args()

    if args.grades:
        if len(args.paths) == 2:
            return validate_grades(args.paths[0], args.paths[1])
        return validate_grades("register/grades.jsonl", "register/register.jsonl")

    paths = args.paths or ["register/register.jsonl"]
    live = args.live or paths == ["register/register.jsonl"]
    return max(validate(p, live) for p in paths)


if __name__ == "__main__":
    sys.exit(main())
