---
name: pet-project
description: Lightweight local workflow for the macOS Hermes Agent Pets project. Use when Codex is asked to inspect this pet project, organize generated pet assets, add or document project structure, create small repeatable workflows, or make the next incremental improvement from an otherwise minimal project state.
---

# Pet Project

## Workflow

1. Inspect the current tree with `rg --files` before deciding where new files belong.
2. Treat `hatch-runs/` as generated output unless the user explicitly asks to modify a run artifact.
3. Keep project scaffolding in top-level, human-authored folders such as `skills/`, `docs/`, or `scripts/`.
4. Prefer the smallest useful artifact: a short workflow, focused reference, or tiny script only after the same operation repeats.
5. Validate new skill files with the skill-creator validator when changing a skill.

## Project Shape

Use this starting convention:

- `skills/`: local Codex skills for this project.
- `docs/`: durable project notes and decisions, when needed.
- `scripts/`: deterministic utilities, only once a workflow needs automation.
- `hatch-runs/`: generated pet hatch outputs and QA artifacts.

## Example Workflow

For a starter task or next-step planning request, read `references/example-workflow.md` and adapt the checklist to the user's concrete goal.
