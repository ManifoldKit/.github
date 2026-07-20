#!/usr/bin/env python3
"""Tripwire tests for lint-composite-actions.py.

Why this exists: the linter is itself a gate, and a gate that cannot be shown to
fail is not coverage. Both real bugs found in review — a `run:` step with no
`shell:`, and an action with no `using:` — were cases where the linter exited 0
and printed a success line, and both would have been caught by a fixture here.
So every check gets a fixture that must FAIL, plus a happy path that must PASS.

Run: python3 .github/scripts/test_lint_composite_actions.py
(no pytest dependency — this runs on a bare runner)
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

LINTER = Path(__file__).parent / "lint-composite-actions.py"

VALID_STEP = """
    - name: ok
      shell: bash
      run: echo hi
"""

# (name, action.yml body, expect_failure[, required stderr substring])
# The optional 4th element matters for malformed-input cases: a non-zero exit
# alone cannot distinguish "reported the problem" from "crashed", so those
# assert on the diagnostic text too.
CASES: list[tuple] = [
    (
        "happy path",
        f"""
name: t
description: d
runs:
  using: composite
  steps:{VALID_STEP}
""",
        False,
    ),
    (
        "run: with no shell: (round-1 bug)",
        """
name: t
description: d
runs:
  using: composite
  steps:
    - name: no shell
      run: echo hi
""",
        True,
    ),
    (
        "run: key present but empty (round-2 bug B)",
        """
name: t
description: d
runs:
  using: composite
  steps:
    - name: empty run
      run:
""",
        True,
    ),
    (
        "runs: with no using: (round-2 bug A)",
        """
name: t
description: d
runs:
  steps:
    - name: ok
      shell: bash
      run: echo hi
""",
        True,
    ),
    (
        "runs: {} — no using, no steps (round-2 bug A)",
        """
name: t
description: d
runs: {}
""",
        True,
    ),
    (
        "unknown using:",
        """
name: t
description: d
runs:
  using: nodeXX
  steps: []
""",
        True,
    ),
    (
        "using: node20 with no steps is legitimate",
        """
name: t
description: d
runs:
  using: node20
  main: index.js
""",
        False,
    ),
    (
        "using: composite with no steps",
        """
name: t
description: d
runs:
  using: composite
""",
        True,
    ),
    (
        "uses: pinned to a tag",
        """
name: t
description: d
runs:
  using: composite
  steps:
    - uses: some-org/some-action@v1
""",
        True,
    ),
    (
        "uses: pinned to a 40-hex SHA",
        """
name: t
description: d
runs:
  using: composite
  steps:
    - uses: some-org/some-action@ed7a3b1fda3918c0306d1b724322adc0b8cc0a90
""",
        False,
    ),
    (
        "docker:// with a mutable tag",
        """
name: t
description: d
runs:
  using: composite
  steps:
    - uses: docker://alpine:latest
""",
        True,
    ),
    (
        "docker:// pinned by digest",
        """
name: t
description: d
runs:
  using: composite
  steps:
    - uses: docker://alpine@sha256:0000000000000000000000000000000000000000000000000000000000000000
""",
        False,
    ),
    (
        "bashism under shell: sh",
        """
name: t
description: d
runs:
  using: composite
  steps:
    - name: sh step
      shell: sh
      run: 'if [[ -n "$FOO" ]]; then echo x; fi'
""",
        True,
    ),
    (
        "unused variable (SC2034 must not be excluded)",
        """
name: t
description: d
runs:
  using: composite
  steps:
    - name: unused
      shell: bash
      run: |
        tools_version=$(head -n 1 Package.swift)
        echo finished
""",
        True,
    ),
    (
        "runs: is a string, not a mapping",
        """
name: t
description: d
runs: nonsense
""",
        True,
        "`runs:` must be a mapping",
    ),
    (
        "steps: is not a list",
        """
name: t
description: d
runs:
  using: composite
  steps:
    not: a-list
""",
        True,
        "must be a list",
    ),
    (
        "uses: is not a string",
        """
name: t
description: d
runs:
  using: composite
  steps:
    - uses:
        not: a-string
""",
        True,
        "`uses:` must be a string",
    ),
    (
        "step is a list, not a mapping",
        """
name: t
description: d
runs:
  using: composite
  steps:
    - [not, a, mapping]
""",
        True,
        "is not a mapping",
    ),
    (
        "shell: python is skipped, not mis-linted",
        """
name: t
description: d
runs:
  using: composite
  steps:
    - name: py
      shell: python
      run: print('hi')
""",
        False,
    ),
]


def run_case(body: str) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        action_dir = root / ".github" / "actions" / "fixture"
        action_dir.mkdir(parents=True)
        (action_dir / "action.yml").write_text(body)
        result = subprocess.run(
            [sys.executable, str(LINTER), str(root)],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode, result.stderr


def main() -> int:
    failures = 0
    for case in CASES:
        # Optional 4th element: a substring the diagnostic must contain. Exit
        # code alone cannot tell "reported the problem" from "crashed with a
        # traceback" — both are non-zero — so the malformed-input cases assert
        # on the message. Without this the isinstance guards had no tripwire.
        name, body, expect_failure = case[0], case[1], case[2]
        expect_stderr = case[3] if len(case) > 3 else None

        rc, stderr = run_case(body)
        actually_failed = rc != 0
        ok = actually_failed == expect_failure
        detail = ""
        if ok and expect_stderr is not None:
            if expect_stderr not in stderr:
                ok = False
                detail = f" — expected stderr to contain {expect_stderr!r}"
            elif "Traceback" in stderr:
                ok = False
                detail = " — crashed with a traceback instead of reporting"
        want = "FAIL" if expect_failure else "PASS"
        got = "FAIL" if actually_failed else "PASS"
        print(f"  [{'ok' if ok else 'XX'}] {name}: want {want}, got {got} (rc={rc}){detail}")
        if not ok:
            failures += 1

    # A linter that finds no actions must not silently succeed as if it had
    # checked something — but "nothing to lint" is a legitimate 0. Assert the
    # message so a future refactor can't turn a real sweep into a no-op quietly.
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [sys.executable, str(LINTER), tmp], capture_output=True, text=True, check=False
        )
        if result.returncode != 0 or "No composite actions found" not in result.stdout:
            print(f"  [XX] empty tree: expected rc=0 and a 'nothing to lint' notice, "
                  f"got rc={result.returncode} / {result.stdout!r}")
            failures += 1
        else:
            print("  [ok] empty tree: reports nothing to lint, rc=0")

    # A nonexistent root globs to nothing, which looks identical to a real empty
    # tree — so a path typo would pass the gate silently. The empty-tree case
    # above uses a REAL directory and therefore cannot catch this.
    result = subprocess.run(
        [sys.executable, str(LINTER), "/nonexistent/typo/path"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode == 0 or "not a directory" not in result.stderr:
        print(f"  [XX] nonexistent root: expected a non-zero 'not a directory' error, "
              f"got rc={result.returncode} / {result.stderr!r}")
        failures += 1
    else:
        print("  [ok] nonexistent root: refuses to report success, rc=1")

    print()
    if failures:
        print(f"{failures} case(s) behaved unexpectedly.", file=sys.stderr)
        return 1
    print(f"All {len(CASES) + 2} cases behaved as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
