# The claim register

> **Status (13 September 2026): empty by design.** The register opens with W1 on 15 October 2026, when its first entry is logged with its probability; publication is the timestamp. Until then the drafts live in the working repository with their probability unset. This public mirror carries the claim file, the grade file, the schema below, and the validator, and is updated by `scripts/publish_register.sh` on every append. Site: https://reckoningbrief.com

Append-only. One JSON object per line. This file is the brief's core promise: every
forecast is dated, probability-weighted, falsifiable, and re-graded in public.

## Schema

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | `YYYY-MM-NNN`, e.g. `2026-09-001`. Unique. Never reused, not even for a voided entry. |
| `issue` | string | yes | Issue number as a zero-padded string, e.g. `01`. |
| `date_logged` | string | yes | ISO 8601 date, `YYYY-MM-DD`. The date the claim was published, not the date it was drafted. |
| `claim` | string | yes | One sentence. Unambiguous. Must pass the claim wording test below. |
| `probability` | number \| string | yes | Float in `[0,1]`, or the literal string `TBD_KEVIN`. Claude always writes `TBD_KEVIN`. |
| `resolution_date` | string | yes | ISO 8601. The date the claim gets graded, whether or not the outcome is obvious by then. |
| `falsifier` | string | yes | The observation that would resolve this false. Must be observable, dated, and sourced. |
| `resolution_source` | string | yes | Where the resolving fact will be checked. Name the specific source, not a category. |
| `status` | enum | yes | `open` \| `resolved_true` \| `resolved_false` \| `void` |
| `resolved_on` | string \| null | yes | ISO 8601 once resolved, else `null`. |
| `brier` | number \| null | yes | Brier score once resolved, else `null`. `(p - outcome)^2`, outcome ∈ {0,1}. |
| `notes` | string | yes | Reasoning, evidence summary, and any caveat. May be empty string. |
| `sector` | enum | yes | `space` \| `defense` \| `energy` \| `cross`. The publication's scope since 13 Sep 2026; Brier is reported by sector as well as overall. `cross` only where the claim genuinely spans sectors. |
| `supersedes` | string | no | The `id` of an entry this corrects. Present only on correcting entries. |
| `resolution_urls` | list of strings | no | The concrete pages the resolution will be checked against. `scripts/snapshot_resolution_sources.py` archives and renders each one into `evidence/<id>/` with hashes, monthly and on logging. `resolution_source` remains the prose a reader sees. |

## Rules

1. **Append only.** Existing lines are never edited or deleted. A pre-commit hook
   (`scripts/check_register_append_only.sh`) fails the commit if any line present in
   `HEAD:register/register.jsonl` is absent or altered in the working copy.

2. **Corrections are new entries.** If a claim was badly worded, ambiguous, or wrong on its
   facts, write a new entry with `supersedes` set to the original `id`. The original line is
   not touched. The reader sees both, and sees that the correction came second.

3. **`void` is for claims that became ungradeable through no fault of the forecast** — the
   resolving source stopped publishing, the company was acquired and stopped reporting, the
   question was rendered meaningless by an unrelated event. `void` is not an escape hatch
   for a claim that is heading toward `resolved_false`. Voiding requires a note explaining
   why, and voiding after the fact looks exactly like cowardice, so the bar is high.

4. **Probability is Kevin's.** Claude drafts entries with `probability: "TBD_KEVIN"` and a
   suggested range in `notes`. Kevin replaces the string with a number before the entry is
   appended here. An entry reaches this file only with a real probability.

5. **Grade on the date, into a second file.** A claim is graded on its `resolution_date` even
   when the outcome looks settled earlier, and especially when it looks bad.

   **The grade is never written onto the claim.** `register/register.jsonl` is byte-immutable
   once committed — the pre-commit hook refuses any change to a line already in `HEAD`, which
   includes setting `status`, `resolved_on` or `brier` on it. That is deliberate. A claim line
   is the artefact that proves what was forecast and when, and it is worth more if nothing can
   touch it, ever.

   Grades append to **`register/grades.jsonl`**, one JSON object per line, also append-only:

   | Field | Type | Notes |
   |---|---|---|
   | `entry_id` | string | The claim being graded. Must exist in `register.jsonl`. |
   | `graded_on` | string | ISO date. Not before the claim's `resolution_date`. |
   | `outcome` | enum | `resolved_true` \| `resolved_false` \| `void` |
   | `brier` | number \| null | `(p - outcome)^2` from the claim's own probability. `null` only for `void`. |
   | `observation` | string | What was actually observed, in one sentence. |
   | `evidence` | string | Where it was observed. The claim's `resolution_source`, resolved to a specific citation. |
   | `evidence_sha256` | string \| null | Optional hash of the retrieved source, so the evidence can be shown to be the same later. |
   | `archived_evidence` | string \| null | Wayback URL of the evidence (`scripts/archive_sources.py` / `snapshot_resolution_sources.py`). |
   | `note` | string | Kevin's note on the grade, ≤ 120 words. Written by Kevin; `scripts/grade.py` refuses to run without it. |
   | `graded_by` | string | Who graded. |

   `scripts/grade.py <id> <outcome> --evidence <url> --note-file <path>` is the only way a grade is
   written: it checks the entry is logged, open and past its date (or `--early` with a recorded
   reason), computes the Brier from the claim's own probability, appends, validates, and
   re-renders the site — the grade page at `/grades/<id>/`, the entry in green or red, and
   `/register/calibration/`. `register/resolutions.ics` (one event per resolution date) is
   regenerated on every append by `scripts/resolutions.py`.

   A claim's live status is therefore **derived**, not stored: it is `open` until a grade
   exists for it, and whatever that grade says afterwards. One grade per claim, permanently.
   `scripts/validate_register.py --grades` checks every rule above, including recomputing the
   Brier from the claim's probability rather than trusting the number written down.

6. **Drafts live elsewhere.** Per-issue drafts go in `issues/NN/register-drafts.jsonl`.
   Nothing enters this file until Kevin has set the probability.

7. **Supersession is a correction window, not an escape hatch.** `supersedes` exists so that
   a claim which was *never properly gradeable* — ambiguous wording, a falsifier that does
   not bite, a resolution source that turns out not to publish — can be restated. It does not
   exist to retire a forecast that is aging badly.

   The window is narrow and mechanical: a superseding entry must appear in the **same issue
   as the original, or the issue immediately after**. Inside that window the original is
   excluded from the running Brier average, retained in the file, and displayed struck
   through with a pointer to its replacement. Outside that window, `supersedes` is not
   available.

   **Changing your mind is not a correction.** A revised probability on a claim that was
   always gradeable is a *new, independent entry* with no `supersedes` field, and both
   entries score. You may update a forecast in public as often as the evidence warrants. You
   may not un-log the one you started with.

   A resolved entry can never be superseded. Neither can an entry already superseded by
   another — one correction, or the claim was not salvageable and should be `void`.

## Claim wording test

Would two reasonable people, reading only the `claim` and `falsifier`, agree on what
outcome resolves it true? If the claim contains "significant", "meaningful", "widespread",
"successful", or any adjective doing quantitative work, it fails. Rewrite with a number, a
date, and a named source.

## Falsifier test

The falsifier must be an observation, not an absence of belief. "Starship does not become
operational" fails. "Fewer than N Starship flights deliver payload to orbit by
2027-12-31, per the FAA launch log" passes: observable, dated, sourced.

## Brier scoring

`brier = (p - outcome)^2`, outcome 1 for true, 0 for false. Lower is better. The score lives
in `grades.jsonl`, never on the claim. A forecaster
who says 0.7 and is right scores 0.09; one who says 0.95 and is wrong scores 0.9025.
Voided entries are excluded from the running average and reported separately, with the
count shown so that exclusions are visible. **Superseded entries are excluded on the same
terms** — retained, displayed, and counted in the exclusions line. Two exclusion counts sit
beside every published Brier average, because a score with invisible exclusions is not a
score. If the exclusion count ever grows faster than the resolved count, the register is
being managed rather than kept.

## Revision discipline

A revised probability is a new independent entry, per rule 7 — not a supersession. Two limits
stop that freedom becoming a way to manage the score.

**The 60-day lock.** No revision may be logged within 60 days of a claim's `resolution_date`.
Late revisions are where a forecaster quietly converges on the answer they can already see, and
a Brier average built from them measures nerve, not calibration. Move the number early or
carry it.

**Range integrity on short-horizon claims.** A claim resolving within 90 days is only worth
logging if its drafted range sits between 0.20 and 0.80. Short-fuse near-certainties inflate a
running mean without testing anything. If the honest range is outside that band, the claim is
an observation, not a forecast, and belongs in the issue rather than the register.
