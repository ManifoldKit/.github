# Reusable companion workflows

This repo (`ManifoldKit/.github`) hosts reusable `workflow_call` workflows and a
shared composite action for the ManifoldKit companion repos
(`manifold-llama`, `manifold-mlx`, `manifold-eval`, and any future backend
family or assurance repo). They were extracted because manifold-llama and
manifold-mlx each carried near-identical ~135-line `core-bump.yml` and
~51-line `canary.yml` copies that had already drifted once (mlx's pin-rewrite
regex targeted a stale `roryford/ManifoldKit` path instead of
`ManifoldKit/ManifoldKit`).

**Important:** because this repo is itself named `.github`, callers reference
these workflows with the org-repo path doubled up:

```
uses: ManifoldKit/.github/.github/workflows/<file>.yml@main
```

(`ManifoldKit/.github` is the repo; `.github/workflows/<file>.yml` is the path
inside it — GitHub does not collapse the repeated `.github` segment.)

Reusable workflows (`on: workflow_call`) replace **jobs**, not steps. Callers
keep their own top-level triggers (`repository_dispatch`, `workflow_dispatch`,
`schedule`, `push`) and invoke a workflow via `jobs.<id>.uses`; all step-level
logic lives in this repo.

## `companion-core-bump.yml`

Bumps a companion's ManifoldKit pin to a released version, gated on a real
green build, then opens and admin-squash-merges a `fix:` PR. The merge is
PAT-authored so it trips the caller's own push-triggered `release-please.yml`.

| Input | Default | Notes |
|---|---|---|
| `version` (required) | — | X.Y.Z, no leading `v`. Caller resolves this from its trigger payload before calling. |
| `pin-mode` | `upToNextMinor` | `upToNextMinor` rewrites `.upToNextMinor(from: "X.Y.Z")` (manifold-llama, manifold-mlx). `exact` rewrites `exact: "X.Y.Z"` (manifold-eval). |
| `gate-command` | `swift build && swift test` | Runs after `swift package resolve` against the new pin. |
| `trip-release-please` | `true` | Set `false` for repos with no release-please workflow (e.g. manifold-eval) — only skips the informational trigger step, not the PR merge. |

| Secret | Required | Notes |
|---|---|---|
| `RELEASE_AUTOMERGE_TOKEN` | yes | Fine-grained PAT, Contents: read+write + Pull requests: read+write, on the caller repo. |

### Caller shim — `upToNextMinor` companion (manifold-llama / manifold-mlx style)

```yaml
name: Bump core pin (on ManifoldKit release)

on:
  repository_dispatch:
    types: [core-release]
  workflow_dispatch:
    inputs:
      tag:
        description: "ManifoldKit tag to pin to (e.g. v0.63.0)"
        required: true
        type: string

jobs:
  resolve:
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.tag.outputs.version }}
    steps:
      - id: tag
        env:
          DISPATCH_TAG: ${{ github.event.client_payload.tag }}
          INPUT_TAG: ${{ github.event.inputs.tag }}
        run: |
          set -euo pipefail
          TAG="${DISPATCH_TAG:-$INPUT_TAG}"
          echo "version=${TAG#v}" >> "$GITHUB_OUTPUT"

  bump:
    needs: resolve
    uses: ManifoldKit/.github/.github/workflows/companion-core-bump.yml@main
    with:
      version: ${{ needs.resolve.outputs.version }}
      pin-mode: upToNextMinor
    secrets: inherit
```

### Caller shim — exact-pin repo (manifold-eval style)

```yaml
name: Bump core pin (on ManifoldKit release)

on:
  repository_dispatch:
    types: [core-release]
  workflow_dispatch:
    inputs:
      tag:
        description: "ManifoldKit tag to pin to (e.g. v0.63.0)"
        required: true
        type: string

jobs:
  resolve:
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.tag.outputs.version }}
    steps:
      - id: tag
        env:
          DISPATCH_TAG: ${{ github.event.client_payload.tag }}
          INPUT_TAG: ${{ github.event.inputs.tag }}
        run: |
          set -euo pipefail
          TAG="${DISPATCH_TAG:-$INPUT_TAG}"
          echo "version=${TAG#v}" >> "$GITHUB_OUTPUT"

  bump:
    needs: resolve
    uses: ManifoldKit/.github/.github/workflows/companion-core-bump.yml@main
    with:
      version: ${{ needs.resolve.outputs.version }}
      pin-mode: exact
      trip-release-please: false
    secrets:
      RELEASE_AUTOMERGE_TOKEN: ${{ secrets.RELEASE_AUTOMERGE_TOKEN }}
```

Both `secrets: inherit` and an explicit `secrets:` mapping work — use
`inherit` when the caller repo's org/repo secret is already named
`RELEASE_AUTOMERGE_TOKEN`; use the explicit form to rename or to pass a
differently-scoped token.

## `companion-canary.yml`

Builds + tests the caller against `ManifoldKit/ManifoldKit`'s `core-ref` HEAD
(default `main`) via `swift package edit`, catching a core seam move before
it ships as a release. A failure here means core moved, not that the caller
regressed.

| Input | Default | Notes |
|---|---|---|
| `core-ref` | `main` | Any branch/ref in `ManifoldKit/ManifoldKit`. |

No secrets required (checks out core over the public repo; needs only
`contents: read`).

### Caller shim

```yaml
name: Canary (core main)

on:
  schedule:
    - cron: "17 4 * * *"   # nightly, 04:17 UTC (quiet hour)
  workflow_dispatch:
  repository_dispatch:
    types: [core-release]

jobs:
  canary:
    uses: ManifoldKit/.github/.github/workflows/companion-canary.yml@main
```

(No secrets needed — omit `secrets:` entirely, or pass `secrets: inherit` if
your org policy requires it explicitly.)

## `companion-release-please.yml`

Thin wrapper around `googleapis/release-please-action`. Kept as a reusable
workflow (rather than folded into `companion-core-bump.yml`) because it runs
on its own `push: [main]` trigger, independent of the bump flow.

| Input | Default | Notes |
|---|---|---|
| `config-file` | `release-please-config.json` | Path relative to caller repo root. |
| `manifest-file` | `.release-please-manifest.json` | Path relative to caller repo root. |

No secrets input needed — the reusable workflow declares
`permissions: contents: write, pull-requests: write` itself and uses the
caller's default `GITHUB_TOKEN` (release-please does not need the
PAT — it only opens/updates the release PR, it doesn't need to trip another
workflow with its own commits).

### Caller shim

```yaml
name: Release Please

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  release-please:
    uses: ManifoldKit/.github/.github/workflows/companion-release-please.yml@main
```

## `actions/setup-swift-ci`

Composite action (not a reusable workflow — invoked from a `steps:` list,
not `jobs.<id>.uses`) that selects the pinned Xcode 26 toolchain and restores
the SwiftPM dependency cache (`.build/artifacts` + `.build/checkouts` +
`.build/repositories`; deliberately NOT `.build/debug` — see
ManifoldKit/ManifoldKit's `ci.yml` for why path-fingerprinted own-module
objects go stale on cache restore).

| Input | Default | Notes |
|---|---|---|
| `xcode-version` | `26.3` | Passed to `maxim-lobanov/setup-xcode`. |
| `cache-key-suffix` | `""` | Append to disambiguate a job's cache key, e.g. `-foundation-only`. |
| `verify-toolchain` | `false` | Set `true` in jobs that build `Package.swift` directly, to fail fast with a clear message on a tools-version/runner-Swift mismatch. |

### Usage

```yaml
jobs:
  test:
    runs-on: macos-15
    steps:
      - uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd # v5
      - uses: ManifoldKit/.github/.github/actions/setup-swift-ci@main
        with:
          verify-toolchain: "true"
      - run: swift build
      - run: swift test
```

## Regex dry-run proof (pin-rewrite, both modes)

Both `pin-mode` regexes in `companion-core-bump.yml` were dry-run against
copies of the real companion manifests with `VERSION=9.9.9`:

```
=== upToNextMinor regex against manifold-llama/Package.swift ===
before: .package(url: "https://github.com/ManifoldKit/ManifoldKit", .upToNextMinor(from: "0.63.0")),
after:  .package(url: "https://github.com/ManifoldKit/ManifoldKit", .upToNextMinor(from: "9.9.9")),

=== exact regex against manifold-eval/Package.swift ===
before: .package(url: "https://github.com/ManifoldKit/ManifoldKit.git", exact: "0.63.0"),
after:  .package(url: "https://github.com/ManifoldKit/ManifoldKit.git", exact: "9.9.9"),

=== cross-check: upToNextMinor regex against manifold-eval/Package.swift ===
no change (eval has no .upToNextMinor(from:) pin to match)

=== cross-check: exact regex against manifold-llama/Package.swift ===
no change (llama has no exact: pin to match)
```

Both regexes anchor on `ManifoldKit/ManifoldKit(?:\.git)?"` so they work
whether or not the caller's URL has a `.git` suffix (llama/mlx omit it, eval
includes it) — unlike mlx's current local copy, which still matches a stale
`roryford/ManifoldKit` path and was NOT ported here.
