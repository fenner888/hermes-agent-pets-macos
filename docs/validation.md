# Validation

Use the project virtual environment for skill validation:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" skills/pet-project
```

Expected output:

```text
Skill is valid!
```
