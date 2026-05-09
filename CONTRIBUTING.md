# Contributing

Thanks for helping make macOS Hermes Agent Pets better.

This repo is for native macOS Hermes companion pets, public starter companions, and tooling that helps users create their own pets. Personal/private character assets should not be contributed here.

## Good First Contributions

- Improve install docs.
- Add validation coverage.
- Improve the native macOS overlay.
- Improve custom pet packaging docs.
- Add public starter companion metadata or assets that are clearly licensed for this repo.
- Report macOS/Hermes integration bugs with exact versions and reproduction steps.

## Before Opening a Pull Request

Run:

```bash
scripts/validate-hermes-companions.py
for pet in koda miko bramble nyx pip atlas; do scripts/validate-hermes-pet.py "character-sets/$pet"; done
scripts/hermes-pet-overlay/build.sh
scripts/test-hermes-agent-pet.py
scripts/hermes-pet-doctor --build
```

For install changes, also run:

```bash
scripts/smoke-install.sh
```

If you changed overlay behavior and can run GUI checks locally:

```bash
scripts/smoke-install.sh --overlay
```

## Character Asset Rules

- Do not submit private or personal character assets.
- Do not submit assets copied from another project unless the license clearly permits redistribution.
- Include source/provenance notes for new public companion art.
- Keep generated frame folders out of Git. Commit final runtime assets only.
- Prefer small, readable sprites that work at macOS overlay size.

## Pull Request Checklist

- The change is scoped and described clearly.
- No local machine paths are embedded.
- No generated folders such as `hatch-runs/`, `build/`, `.venv/`, or `sprites/` are tracked.
- New public assets have a clear right to be distributed under this repo's license or an explicitly documented compatible license.
- Validation commands pass or the PR explains why they could not be run.
