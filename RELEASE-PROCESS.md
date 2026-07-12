# The ManifoldKit release train

ManifoldKit (core) and its companion repos (`manifold-mlx`, `manifold-llama`,
`manifold-eval`) release on a chain: a core release should end with every
companion pinned to the new version and, where the companion has its own
release-please setup, a fresh companion release cut too. Most of the chain is
automated. This doc describes what runs on its own, and the handful of steps
a human still needs to do in the right order.

## The automated flow

1. **Core release-please** watches pushes to `main` on
   `ManifoldKit/ManifoldKit`. Once enough `feat:`/`fix:` commits have landed,
   it opens (or updates) a release PR with an auto-generated CHANGELOG entry.
2. When that release PR is merged, release-please tags the release and sets
   `release_created` on the run. Two jobs then fire:
   - **`sync-release-notes`** rewrites the GitHub release notes from the
     merged CHANGELOG entry, so the tag's release page matches
     `CHANGELOG.md` instead of GitHub's default commit-list rendering.
   - **`notify-companions`** sends a `repository_dispatch` of type
     `core-release` (payload: the new tag) to `manifold-llama`,
     `manifold-mlx`, and `manifold-eval`. This step needs a
     `COMPANION_DISPATCH_TOKEN` secret on the core repo — a fine-grained PAT
     with `contents: read+write` on all three companion repos, since the
     default `GITHUB_TOKEN` can't reach across repos. If that secret is
     missing or wrong, this job fails loudly rather than silently skipping
     the dispatch.
3. Each companion listens for that `core-release` dispatch in its own
   `core-bump.yml`. On receipt, it rewrites its ManifoldKit pin in
   `Package.swift` to the new version, re-resolves, builds and tests against
   the new core, and — if that gate is green — opens and merges a `fix: bump
   ManifoldKit pin to vX.Y.Z` PR. That merge is authored by a
   `RELEASE_AUTOMERGE_TOKEN` PAT (not the default token) specifically so it
   trips the companion's own push-triggered `release-please.yml`.
4. The companion's release-please then opens its own release PR off that
   pin-bump commit (plus anything else that landed since its last release).
   `manifold-eval` pins with `exact:` rather than `.upToNextMinor(from:)` and
   currently has no release-please of its own, so step 4 doesn't apply there
   yet — the pin-bump PR from step 3 is the end state for that repo.

All of the reusable workflows behind this (`companion-core-bump.yml`,
`companion-release-please.yml`, `companion-canary.yml`, `swift-ci.yml`) live
in this repo and are documented in [WORKFLOWS.md](WORKFLOWS.md).

## What still needs a human, and in what order

The automated flow above only starts once a *core* release PR is merged. But
by the time you're ready to cut that core release, some companions usually
have their own pending feature work sitting in open PRs. Merging things in
the wrong order means a companion either ships a release without its own
pending work, or ends up bumped to the new core pin *before* its own feature
PRs have landed — forcing a second, avoidable pin-bump cycle. The sequencing
that avoids both:

1. **Merge pending companion feature PRs first.** Before merging core's
   release PR, look at each companion's open PRs and merge the ones you want
   in the next companion release. They should land before the companion's
   own release-please PR is finalized, so they're included in that release's
   changelog rather than trailing behind it.
2. **Rewrite the companion release-PR changelogs.** Once a companion's
   release-please PR exists (either from its own accumulated commits, or
   from the pin-bump PR in step 3 above), rewrite the auto-generated bullets
   before merging — same rule as core's own release PRs. Use the Prisma
   Highlights format for anything notable (a short headline, a couple of
   sentences of context, a runnable snippet for new/changed public API);
   small fixes can stay as one-line bullets.
3. **Merge the companion release PRs.** Do this before merging core's
   release PR, not after — a companion release cut against an *old* core pin
   is fine (that's the common case for a companion's own feature work), but
   you don't want core's tag to go out while known-good companion work is
   still sitting unmerged.
4. **Merge core's release PR last.** This is what triggers
   `notify-companions`, which in turn drives each companion's
   `core-bump.yml`. Merging it last means the dispatch lands on companions
   that are already in a settled state, so the automated pin-bump PR is a
   clean, single-purpose diff.
5. **Run `companion-compat.yml` as a pre-tag safety net for risky core
   releases.** This is a manual, on-demand workflow in the core repo
   (`workflow_dispatch`, not a required gate) that builds `manifold-mlx` and
   `manifold-llama` against an arbitrary core ref — normally `main` — before
   you tag. It exists because a breaking change (for example, a new
   non-`@frozen` enum case in a Contract type) lands on core's `main` well
   before the release PR exists, so there's nothing on the release PR's diff
   to gate on automatically. Press this button before merging a `feat!:` or
   otherwise risky minor release PR, so a companion-breaking seam is caught
   while core's `main` is still unreleased, instead of surfacing only after
   the tag ships (the post-release `core-bump` gate in step 3 above already
   stops a broken companion *release* from going out, but by then the tag is
   already public). Note this check only covers `manifold-mlx` and
   `manifold-llama` today — `manifold-eval` isn't in its matrix.

## Checklist

Before merging a core release PR:

- [ ] Merge any companion feature PRs you want in the next companion release
- [ ] For a `feat!:` or otherwise risky core release, run `companion-compat.yml`
      against core's `main` and confirm both companions still build
- [ ] Rewrite each companion's pending release-please PR changelog (Prisma
      Highlights for notable entries) and merge it
- [ ] Rewrite core's own release PR changelog and merge it last

After merging core's release PR:

- [ ] Confirm `notify-companions` succeeded for all three companion repos
      (it fails loudly, not silently, if `COMPANION_DISPATCH_TOKEN` is
      missing or a dispatch 4xx/5xxs)
- [ ] Confirm each companion's `core-bump.yml` run went green and its pin-bump
      PR merged
- [ ] For companions with their own release-please, rewrite and merge the
      resulting release PR once it appears
