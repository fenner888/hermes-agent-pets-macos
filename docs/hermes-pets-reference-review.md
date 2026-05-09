# Hermes Pets Reference Review

This note captures the release lessons applied from reviewing the Windows Hermes Pets setup and adapting the project for macOS.

## Replicated Ideas

- Keep installable plugin code separate from generated art work files.
- Ship final runtime assets only: `pet.json`, `spritesheet.webp`, and overlay-specific confirmation assets.
- Provide a simple install script that can target either `~/.hermes/plugins` or a temporary rehearsal directory.
- Keep companion metadata centralized so future characters can be added without editing the overlay logic.
- Validate from a clean-install mindset before publishing.

## macOS-Specific Shape

```text
hermes-agent-pets/
  hermes-pet-agent/
    plugin.yaml
    __init__.py
    assets/<pet-id>/
scripts/
  hermes-pet-overlay/
    HermesPetOverlay.m
    build.sh
```

The macOS overlay is native AppKit. The Hermes plugin launches it from the installed plugin package when available, or from the repo build during development.

## Public Starter Set

- Koda
- Miko
- Bramble
- Nyx
- Pip
- Atlas

Personal/private characters should stay out of this public repo. Users can create and package their own companions with the documented character format.
