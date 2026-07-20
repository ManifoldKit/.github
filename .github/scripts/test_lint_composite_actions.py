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

# (name, action.yml body, expect_failure)
CASES: list[tuple[str, str, bool]] = [
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
        echo done
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


def run_case(body: str) -> int:
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
        return result.returncode


def main() -> int:
    failures = 0
    for name, body, expect_failure in CASES:
        rc = run_case(body)
        actually_failed = rc != 0
        ok = actually_failed == expect_failure
        want = "FAIL" if expect_failure else "PASS"
        got = "FAIL" if actually_failed else "PASS"
        print(f"  [{'ok' if ok else 'XX'}] {name}: want {want}, got {got} (rc={rc})")
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

    print()
    if failures:
        print(f"{failures} case(s) behaved unexpectedly.", file=sys.stderr)
        return 1
    print(f"All {len(CASES) + 1} cases behaved as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
