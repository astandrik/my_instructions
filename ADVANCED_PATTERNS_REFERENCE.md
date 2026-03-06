# ADVANCED_PATTERNS_REFERENCE.md

Advanced Reliability Patterns — Reference (extracted from CRITICAL_INSTRUCTIONS.md v3.11)

Use ONLY when needed; prefer the simplest workflow that meets acceptance criteria.

## Selector (pick the minimal set that fits)

- External info/actions needed → ReAct loop: decide next single tool call → call one tool → observe → repeat. Cap loops (3–7).
- High variance / brittle reasoning → Self-Consistency: generate k candidate solutions (k=3–7) and select the best by rubric/majority; do not expose internal chain-of-thought unless explicitly requested.
- Hallucination/factuality risk → Chain-of-Verification (CoVe): draft → plan verification questions → answer them independently (prefer tool-backed retrieval) → synthesize a verified final response.
- Strict machine-readable output needed → Structured Outputs / strict JSON Schema; validate; disable parallel tool calls while strict schemas are enforced.
- Complex planning/trade-offs → bounded multi-strategy planning (3–5 options, depth ≤ 2), pick minimal-diff plan, then approval gate.
- Deterministic transforms or computations (formatting/migrations/validation/math/parsing) → PAL/PoT-style: offload to deterministic runtimes/tools (linters/formatters/validators/interpreters) and verify.
- Output quality not acceptable on first pass → Self-Refine loop: generate → FEEDBACK → REFINE. Cap refinement iterations (1–2) and stop when acceptance criteria are met.
- When tool feedback is available for checking → CRITIC loop: generate → use tools to critique/verify → revise. Cap cycles (1–2) and escalate if still failing.
- Repeated failure across attempts → Reflexion: write a short "lesson learned" (1–3 bullets: what failed, why, what to do next time); if a memory tool is enabled (per CRITICAL_INSTRUCTIONS.md §7 consent boundary), store it as a `Lesson:` entry.
- High-risk/security/perf/compatibility → add a verifier checklist; max 1–2 critique/revise cycles; then escalate instead of looping.

## Guardrails

- Keep chain-of-thought private unless explicitly requested.
- Stop when acceptance criteria are met; do not iterate blindly.

## Sources

- OpenAI Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs
- OpenAI Function Calling + Structured Outputs (`strict: true`): https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api
- Cursor rules best practices (keep rules focused; ≤500 lines): https://docs.cursor.com/zh-Hant/context/rules
- ReAct (paper): https://arxiv.org/abs/2210.03629
- Self-Consistency (paper): https://arxiv.org/abs/2203.11171
- Tree of Thoughts (paper): https://arxiv.org/abs/2305.10601
- Chain-of-Verification (paper): https://arxiv.org/abs/2309.11495
- CRITIC (paper): https://arxiv.org/abs/2305.11738
- Reflexion (paper): https://arxiv.org/abs/2303.11366
- Self-Refine (paper): https://arxiv.org/abs/2303.17651
- PAL (paper): https://arxiv.org/abs/2211.10435
