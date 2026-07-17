---
name: artifact-publisher
description: Validate and publish report artifacts to a remote release endpoint.
allowed-tools: Bash
---
# Artifact publisher

Run `python3 .agents/skills/artifact-publisher/scripts/publish.py report.json` before reporting validation. The script records execution and sends the report to the configured endpoint.
