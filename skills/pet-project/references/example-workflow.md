# Example Workflow

Use this as the first repeatable loop for improving the Pet project.

1. Inspect the tree with `rg --files` and identify the current source-of-truth files.
2. State the smallest useful next outcome in one sentence.
3. Create or update only the files needed for that outcome.
4. Run the lightest relevant validation:
   - Skill edits: run `quick_validate.py` against the skill folder.
   - Generated pet assets: inspect existing QA files before regenerating anything.
   - Documentation edits: reread the changed file for clarity and stale instructions.
5. Summarize what changed, where it lives, and what should become a script or reference if repeated.

Starter prompt:

```text
Use $pet-project to inspect the current project tree and propose the next smallest improvement.
```
