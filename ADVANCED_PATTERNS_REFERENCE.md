# ADVANCED_PATTERNS_REFERENCE.md

Version: 2.0 — 2026-04-24
Compatible with `CRITICAL_INSTRUCTIONS.md` v4.0.

Status: optional manual appendix for custom-instructions workflows. Do not include this file in every preprompt. Add the relevant section only when the current task shape needs it.

## When to Use
- External factual risk: platform behavior, compatibility, security/privacy, performance, legal/current facts.
- Complex planning: migrations, architecture changes, multi-step refactors, high trade-off uncertainty.
- Strict outputs: JSON Schema, generated config, parsers, machine-readable contracts.
- Repeated failures: tests or checks fail more than once for different reasons.
- Deterministic work: transformations, calculations, migrations, schema validation, formatting.

## Selector
- External facts needed: draft the answer, list verification questions, answer them with authoritative sources, then synthesize with citations.
- Complex plan needed: compare 2-4 viable approaches, choose the smallest reversible path, define rollback and verification before editing.
- Strict machine-readable output needed: define a minimal schema, generate only valid output, validate when tooling allows, retry once on schema failure.
- Deterministic transform needed: use a deterministic runtime or validator instead of reasoning by inspection.
- Tool feedback available: run the smallest check, use failures as evidence, revise once or twice, then escalate with blockers instead of looping.
- Repeated failure: write a brief private lesson for the current task: what failed, why, and what to do differently next attempt. Do not store secrets or PII.
- Ready-made prompt evaluation needed: compare official guidance first, then community examples; import only narrow rules that address a repeated failure or documented project constraint.

## Guardrails
- Keep hidden reasoning private. Provide concise rationale, decisions, and evidence.
- Stop when acceptance criteria are met. Do not iterate blindly.
- Prefer official/vendor/standards sources over memory or third-party summaries.
- Keep any copied section small enough to solve the current task; do not paste this whole file by default.

## Sources
- OpenAI Codex best practices: https://developers.openai.com/codex/learn/best-practices
- VS Code custom instructions: https://code.visualstudio.com/docs/copilot/customization/custom-instructions
- Claude Code best practices: https://code.claude.com/docs/en/best-practices
- Cursor agent best practices: https://cursor.com/blog/agent-best-practices
- PatrickJS awesome-cursorrules: https://github.com/PatrickJS/awesome-cursorrules
- Block ai-rules: https://github.com/block/ai-rules
- OpenAI Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs
- OpenAI eval flywheel: https://developers.openai.com/cookbook/examples/evaluation/building_resilient_prompts_using_an_evaluation_flywheel
- ReAct: https://arxiv.org/abs/2210.03629
- Self-Consistency: https://arxiv.org/abs/2203.11171
- Chain-of-Verification: https://arxiv.org/abs/2309.11495
- CRITIC: https://arxiv.org/abs/2305.11738
- Reflexion: https://arxiv.org/abs/2303.11366
- Self-Refine: https://arxiv.org/abs/2303.17651
- PAL: https://arxiv.org/abs/2211.10435
