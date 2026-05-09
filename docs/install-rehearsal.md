# Install Rehearsal

Use a temporary Hermes plugin directory to test the release package without touching your live install.

```bash
scripts/validate-hermes-companions.py
scripts/hermes-pet-overlay/build.sh
HERMES_PLUGIN_DIR=/tmp/hermes-plugin-test scripts/install-hermes-agent-pet.sh
scripts/test-hermes-agent-pet.py --plugin /tmp/hermes-plugin-test/hermes-pet-agent
```

Expected files:

```text
/tmp/hermes-plugin-test/hermes-pet-agent/plugin.yaml
/tmp/hermes-plugin-test/hermes-pet-agent/__init__.py
/tmp/hermes-plugin-test/hermes-pet-agent/bin/hermes-pet-overlay
/tmp/hermes-plugin-test/hermes-pet-agent/assets/koda/spritesheet.webp
```

The installed runtime package should not contain source-only folders such as
`reference-art`, or local metadata such as `.DS_Store`, `__pycache__`, and
`.pyc` files.

Then restart Hermes and try:

```text
/pet wake
/pet companions
/pet companion koda
/pet stop-sign
/pet sleep
```

The pet should appear as a native macOS overlay, use the selected companion assets, show the front-facing stop-sign run-up, and keep audio-reactive dancing off unless `/pet dance on` is used.
