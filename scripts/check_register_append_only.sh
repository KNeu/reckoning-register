#!/usr/bin/env bash
# Fail if any line already committed in register/register.jsonl has been altered or
# removed in the working copy. The register is append-only: history is the product.
#
# Runs as a pre-commit hook alongside validate_register.py. Exit 0 = clean, 1 = violation.

set -uo pipefail

REGISTER="${1:-register/register.jsonl}"
STAGED_TMP="$(mktemp)"
HEAD_TMP="$(mktemp)"
trap 'rm -f "$STAGED_TMP" "$HEAD_TMP"' EXIT

fail() { echo "APPEND-ONLY VIOLATION: $*" >&2; exit 1; }

# No prior commit of the register (first commit, or file not yet tracked): nothing to protect.
if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
  echo "append-only: no HEAD yet, skipping"
  exit 0
fi
if ! git cat-file -e "HEAD:$REGISTER" 2>/dev/null; then
  echo "append-only: $REGISTER not in HEAD, skipping"
  exit 0
fi

git show "HEAD:$REGISTER" > "$HEAD_TMP" || fail "could not read HEAD:$REGISTER"

# Compare against the staged content if the file is staged, otherwise the working copy.
if git diff --cached --name-only | grep -qx "$REGISTER"; then
  git show ":$REGISTER" > "$STAGED_TMP" 2>/dev/null || fail "could not read staged $REGISTER"
else
  if [ ! -f "$REGISTER" ]; then
    fail "$REGISTER exists in HEAD but is missing from the working copy"
  fi
  cp "$REGISTER" "$STAGED_TMP"
fi

head_lines=$(wc -l < "$HEAD_TMP" | tr -d ' ')
new_lines=$(wc -l < "$STAGED_TMP" | tr -d ' ')

if [ "$new_lines" -lt "$head_lines" ]; then
  fail "$REGISTER shrank from $head_lines to $new_lines lines. Entries are never deleted."
fi

# Every committed line must still be present, byte-identical, at the same position.
if [ "$head_lines" -gt 0 ]; then
  if ! head -n "$head_lines" "$STAGED_TMP" | cmp -s - "$HEAD_TMP"; then
    first_bad=$(head -n "$head_lines" "$STAGED_TMP" | cmp - "$HEAD_TMP" 2>/dev/null \
                | sed -n 's/.*line \([0-9]*\).*/\1/p' | head -1)
    fail "$REGISTER: an existing entry was modified or reordered${first_bad:+ (first difference around line $first_bad)}.
       Corrections are new lines with a \"supersedes\" field. Restore the original with:
         git checkout HEAD -- $REGISTER"
  fi
fi

added=$(( new_lines - head_lines ))
echo "append-only: OK ($head_lines existing line(s) intact, $added added)"
exit 0
