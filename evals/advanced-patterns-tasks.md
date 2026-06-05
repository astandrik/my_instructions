# Advanced Patterns Eval Tasks

Version: 1.0 — 2026-06-05

Use these scenarios for side-by-side checks when changing `ADVANCED_PATTERNS_REFERENCE.md`. Compare old and new appendix behavior; keep changes that improve selector accuracy, evidence quality, safety, or deterministic execution without making the optional appendix broad enough to become always-on guidance.

| Scenario | Appendix trigger | Expected advanced behavior | Required evidence |
|---|---|---|---|
| External factual risk | Platform behavior, security/privacy, compatibility, legal/current facts, or pricing could affect the answer | Define verification questions first, answer them with authoritative sources, then synthesize with citations | Source list and concise source-backed conclusion |
| Complex plan or migration | Architecture change, migration, multi-step refactor, rollback need, or high trade-off uncertainty | Compare 2-4 viable approaches, choose the smallest reversible path, and define rollback and verification before editing | Chosen approach, rejected alternatives, rollback path, verification plan |
| Strict machine-readable output | JSON Schema, generated config, parser contract, or machine-readable artifact is required | Define the minimal schema, generate only valid output, and validate or round-trip when tooling allows | Schema/parser validation result or bounded explanation if unavailable |
| Deterministic transform | Calculation, migration, formatting, schema change, or structured rewrite must be exact | Use a deterministic runtime, parser, formatter, validator, or dry-run instead of reasoning by inspection | Tool output, validator result, or parser round-trip evidence |
| Repeated failure loop | Tests/checks fail more than once for different reasons or the agent keeps revising blindly | Use failures as evidence, revise once or twice, write a brief private lesson for the current task, then escalate with a blocker instead of looping | Failure summary, revised attempt evidence, blocker or final verification |
| Instruction surface decision | A rule might belong in prompt, global defaults, AGENTS.md, nested instructions, skill/command, hook/rule/config, MCP, or connector | Choose the narrowest durable surface that matches scope and enforcement needs | Surface recommendation with why broader/narrower surfaces were rejected |
| Agent context/tool trust | Third-party AGENTS.md, skills, plugins, MCP servers, hooks, connectors, or remote instruction sources are introduced or relied on | Verify provenance, scopes, side effects, hidden instructions, remote fetches, secrets handling, and trust boundaries before enabling or relying on it | Provenance/scope review and bounded tool/config inspection |
| No-op possible | A bug report, fix request, or task may already be resolved, invalid, or unnecessary | Reproduce or inspect first; if evidence shows no mutation is needed, report the evidence and stop | Reproduction evidence or targeted search/inspection evidence |
