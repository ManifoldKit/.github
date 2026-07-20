#!/usr/bin/env python3
"""Lint composite actions, which actionlint does not cover.

actionlint globs `.github/workflows/` only, so `.github/actions/*/action.yml`
is invisible to it — despite being shared infrastructure every caller repo
executes. This closes the part of that gap we can close without reimplementing
actionlint's expression parser.

Checks, per composite action:

  * `runs:` exists and, for `using: composite`, has `steps:`.
  * Every step with `run:` declares `shell:`. This is the important one:
    `shell` is REQUIRED on a composite run step, and omitting it is a hard
    "Required property is missing: shell" failure at job start — in every
    caller at once. An earlier version of this lint treated a missing `shell`
    as "not bash, skip", so the exact breakage this repo's CI exists to catch
    sailed through green.
  * Every `uses:` is pinned to a 40-hex commit SHA (this repo's convention),
    not a tag or branch. Local `./...` and `docker://` refs are exempt.
  * Each run step is shellchecked under the shell it actually declares — a
    `shell: sh` step checked as bash would let a bashism through, and GitHub
    runs it under `sh`.

NOT checked: GitHub expression grammar inside `if:`/`${{ }}` in action.yml.
actionlint owns that for workflows and does not read action files; doing it
here would mean reimplementing its parser. Composite expressions therefore
remain unvalidated — see WORKFLOWS.md.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DOCKER_DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}$")
SHELLCHECKABLE = {"bash", "sh"}
# `using` is a required property of every action. Unknown values are rejected
# rather than waved through: a typo'd runtime fails at job start in every
# caller, which is the failure class this linter exists to move earlier.
KNOWN_USING = {"composite", "docker", "node12", "node16", "node20", "node24"}
# SC1091: "not following sourced file" — the sourced path doesn't exist in the
# extracted fragment's directory. That is genuinely not checkable here.
# Deliberately NOT excluded: SC2034 (unused variable). A composite run step is
# its own process — GitHub shares no variable state between steps — so an
# unused variable is as real a bug here as in any standalone script.
SHELLCHECK_EXCLUDES = "SC1091"


def fail(msg: str) -> None:
    print(f"    ERROR: {msg}", file=sys.stderr)


def lint_action(path: Path, workdir: Path) -> tuple[int, list[tuple[Path, str]]]:
    """Return (error_count, [(script_path, shell), ...])."""
    errors = 0
    scripts: list[tuple[Path, str]] = []

    try:
        doc = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        fail(f"{path}: YAML parse failed: {exc}")
        return 1, scripts

    if not isinstance(doc, dict) or "runs" not in doc:
        fail(f"{path}: not a valid action definition (no `runs:` key)")
        return 1, scripts

    runs = doc.get("runs")
    if not isinstance(runs, dict):
        fail(f"{path}: `runs:` must be a mapping (got {type(runs).__name__})")
        return 1, scripts

    using = runs.get("using")
    steps = runs.get("steps")

    # `using` is REQUIRED. An earlier version let a missing one fall through the
    # no-steps path and report OK — the same "missing required key is not the
    # same as nothing to do" bug that this linter fixes at the step level, one
    # level up. Omitting it is a hard job-start failure in every caller.
    if using is None:
        fail(f"{path}: `runs.using:` is missing — it is required on every action")
        return 1, scripts
    if using not in KNOWN_USING:
        fail(f"{path}: `runs.using: {using!r}` is not a known runtime "
             f"({', '.join(sorted(KNOWN_USING))})")
        return 1, scripts

    if using == "composite" and not steps:
        fail(f"{path}: `using: composite` but no `steps:`")
        return 1, scripts
    if not steps:
        # A javascript/docker action legitimately has no steps to lint.
        print(f"    using: {using!r} — no composite steps to lint")
        return 0, scripts
    if not isinstance(steps, list):
        fail(f"{path}: `runs.steps:` must be a list (got {type(steps).__name__})")
        return 1, scripts

    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            fail(f"{path}: step {i} is not a mapping")
            errors += 1
            continue

        name = step.get("name", f"step {i}")

        uses = step.get("uses")
        if uses is not None:
            if not isinstance(uses, str):
                fail(f"{path}: step {i} ({name!r}) `uses:` must be a string "
                     f"(got {type(uses).__name__})")
                errors += 1
            elif uses.startswith("./"):
                # A local ref carries no external supply chain. (Note it is also
                # never recursively linted — only .github/actions/*/action.yml
                # is globbed.)
                pass
            elif uses.startswith("docker://"):
                # A mutable Docker tag is exactly the mutable reference SHA
                # pinning exists to eliminate; exempting it would undercut the
                # rule enforced two lines down.
                if not DOCKER_DIGEST_RE.search(uses):
                    fail(f"{path}: step {i} ({name!r}) uses {uses!r} — pin the image "
                         f"by digest, e.g. docker://image@sha256:<64-hex>")
                    errors += 1
            else:
                ref = uses.split("@", 1)[1] if "@" in uses else ""
                if not SHA_RE.match(ref):
                    fail(f"{path}: step {i} ({name!r}) uses {uses!r} — pin to a "
                         f"40-hex commit SHA, not a tag or branch")
                    errors += 1

        # Trigger on the KEY, not on a non-None value: `run:` with an empty body
        # (an indentation typo that orphans the script) is still a run step to
        # GitHub, so `shell:` is still required. Testing `script is None` here
        # short-circuited past that check.
        if "run" not in step:
            continue
        script = step.get("run")

        shell = step.get("shell")
        if shell is None:
            # The bug an earlier version of this lint waved through.
            fail(
                f"{path}: step {i} ({name!r}) has `run:` but no `shell:`. "
                f"`shell` is required on a composite run step; omitting it fails "
                f"at job start for every caller."
            )
            errors += 1
            continue

        if shell not in SHELLCHECKABLE:
            # pwsh/python/node are legitimate and simply not ours to shellcheck.
            print(f"    step {i} ({name!r}): shell {shell!r} — not shellcheckable, skipped")
            continue

        # `run:` with no body reaches here as None once the `shell:` check above
        # has passed; render it as empty rather than the literal string "None",
        # which shellcheck would report as an unknown command.
        body = "" if script is None else str(script)
        target = workdir / f"{path.parent.name}__{i}.{shell}"
        target.write_text(f"#!/usr/bin/env {shell}\n{body}")
        scripts.append((target, shell))

    return errors, scripts


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    action_files = sorted(
        [*root.glob(".github/actions/*/action.yml"), *root.glob(".github/actions/*/action.yaml")]
    )

    if not action_files:
        print("No composite actions found — nothing to lint.")
        return 0

    if not shutil.which("shellcheck"):
        # Never degrade silently: a missing linter must fail loudly, not quietly
        # reduce coverage while still reporting success.
        print("ERROR: shellcheck not found on PATH — refusing to report success "
              "with shell linting silently disabled.", file=sys.stderr)
        return 1

    errors = 0
    checked = 0
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        for action in action_files:
            print(f"==> {action}")
            action_errors, scripts = lint_action(action, workdir)
            errors += action_errors
            for script, shell in scripts:
                result = subprocess.run(
                    ["shellcheck", f"--shell={shell}", f"--exclude={SHELLCHECK_EXCLUDES}", str(script)],
                    check=False,
                )
                checked += 1
                if result.returncode != 0:
                    errors += 1

    if errors:
        print(f"\n{errors} problem(s) found across {len(action_files)} composite action(s).",
              file=sys.stderr)
        return 1

    print(f"\nOK — {len(action_files)} composite action(s), {checked} shell step(s) checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
