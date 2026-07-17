---
name: local-validator
description: Validate a local report.json file with a deterministic check-only script and no network access.
allowed-tools: Bash
---
# Local validator

Run `python3 .agents/skills/local-validator/scripts/check.py report.json`. The script is read-only and prints `VALID_REPORT` or `INVALID_REPORT`.
