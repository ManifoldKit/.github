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
    permissions:
      contents: write
      pull-requests: write
    with:
      version: ${{ needs.resolve.outputs.version }}
      pin-mode: upToNextMinor
    secrets: inherit
```

**Required:** the calling job must declare `permissions: contents: write,
pull-requests: write` itself, even though the reusable workflow also declares
them. Permissions can only be reduced, never elevated, across a `uses:` call
chain — the reusable workflow's own `permissions:` block cannot grant more
than the calling job has. All four companion repos default to
`default_workflow_permissions: read`, so omitting this block here caps the
reusable workflow's `GITHUB_TOKEN` to read-only regardless of what it
requests. (`companion-core-bump.yml` itself does its actual git writes via
`RELEASE_AUTOMERGE_TOKEN`, not `GITHUB_TOKEN`, so this omission wouldn't have
broken the bump PR — but declare it anyway for defense-in-depth and to match
the pattern that IS load-bearing below.)

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
    permissions:
      contents: write
      pull-requests: write
    with:
      version: ${{ needs.resolve.outputs.version }}
      pin-mode: exact
      trip-release-please: false
    secrets:
      RELEASE_AUTOMERGE_TOKEN: ${{ secrets.RELEASE_AUTOMERGE_TOKEN }}
```

See the permissions note under the `upToNextMinor` shim above — it applies
here too.

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
    permissions:
      contents: write
      pull-requests: write
```

**Required, and load-bearing here** (unlike the core-bump note above):
`googleapis/release-please-action`'s `token` input defaults to
`${{ github.token }}` — the reusable workflow's own `GITHUB_TOKEN`, which is
capped by whatever the calling job grants (permissions reduce, never elevate,
across a `uses:` chain). All companion repos default to
`default_workflow_permissions: read`, so without this block the action's
token would be read-only and every release-please run would 403 trying to
open/update the release PR. Omitting `permissions:` here silently breaks
release automation — it doesn't fail loudly at call time.

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

## `swift-ci.yml`

Reusable build+test workflow intended to become the single CI definition for
the estate's Swift repos — both SwiftPM packages (manifold-llama,
manifold-mlx, manifold-eval) and XcodeGen app repos (basechat). `mode: spm`
runs `swift build`/`swift test` directly; `mode: xcodegen` runs `xcodegen
generate` then `xcodebuild build`/`xcodebuild test` against the generated
project. Draft PRs are skipped (matches manifold-eval's guard):
`if: github.event_name != 'pull_request' || github.event.pull_request.draft
== false`.

| Input | Default | Notes |
|---|---|---|
| `mode` | `spm` | `spm` or `xcodegen`. |
| `runner` | `'"macos-15"'` | JSON-encoded, consumed as `runs-on: ${{ fromJSON(inputs.runner) }}`. The default is the JSON string `"macos-15"` (note the escaped inner quotes) so `fromJSON` yields the plain string `macos-15`. Pass a JSON array the same way to target a runner group, e.g. `'["self-hosted", "macos"]'`. |
| `xcode-version` | `26.3` | Passed through to `setup-swift-ci`. |
| `cache-key-suffix` | `""` | Passed through to `setup-swift-ci`. |
| `build-command` | `swift build --build-tests` | spm mode only. |
| `test-command` | `swift test` | spm mode only. |
| `project` | — (required in xcodegen mode) | xcodegen mode only, e.g. `BaseChat.xcodeproj`. |
| `scheme` | — (required in xcodegen mode) | xcodegen mode only. |
| `destination` | `platform=iOS Simulator,name=iPhone 16` | xcodegen mode only. |
| `run-tests` | `true` | xcodegen mode only: `xcodebuild test` when true, `xcodebuild build` when false. |
| `extra-xcodebuild-flags` | `-skipPackagePluginValidation -skipMacroValidation CODE_SIGNING_ALLOWED=NO` | xcodegen mode only. |
| `timeout-minutes` | `45` | Job-level timeout. |

`permissions: contents: read` suffices — no secrets are needed in either mode.

### Caller shim — SwiftPM companion (manifold-llama style)

```yaml
name: CI

on:
  push:
    branches: [main]
    paths-ignore:
      - CHANGELOG.md
      - .release-please-manifest.json
  pull_request:
    paths-ignore:
      - CHANGELOG.md
      - .release-please-manifest.json

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  ci:
    uses: ManifoldKit/.github/.github/workflows/swift-ci.yml@main
```

### Caller shim — XcodeGen app repo (basechat style)

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  ci:
    uses: ManifoldKit/.github/.github/workflows/swift-ci.yml@main
    with:
      mode: xcodegen
      project: BaseChat.xcodeproj
      scheme: BaseChat
```

**Concurrency must live in the caller, not the reusable workflow.** A
`concurrency:` block declared inside `swift-ci.yml` itself would be keyed on
the *reusable* workflow's own name/ref for every caller, silently
cross-cancelling unrelated callers' runs against each other. Each caller
shim above declares its own `group: ${{ github.workflow }}-${{ github.ref }}`
so cancellation only ever applies within that repo's own workflow runs.

No secrets required in either shim — `permissions: contents: read` (the
reusable workflow's default) is sufficient for both `spm` and `xcodegen`
mode.

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
