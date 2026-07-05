# My Instructions

Compact, project-neutral custom instructions for coding agents, plus a local
eval harness for checking whether those instructions actually change behavior.

## Contents

- `CRITICAL_INSTRUCTIONS.md`: single instruction bundle with compact always-on
  rules plus a selective advanced appendix.
- `evals/`: deterministic and model-backed evals for the instruction bundle.
- `scripts/run_instruction_evals.py`: the main validation, run, and compare
  harness.

## Current Evidence

Latest tracked snapshot: 43 eval cases, `gpt-5.5-medium` as the primary Codex
runner and fixed quality judge.
Cross-model, no-instructions, and previous-vs-current rows were refreshed after
the single-bundle cleanup. OpenHands and Claude/Fable reference rows are the
latest tracked reference compares documented in `evals/RESULTS.md`.

| Question | Result | What it means |
|---|---:|---|
| Does the current bundle pass its deterministic gates? | 43 / 43 on GPT-5.5 | The current instruction set satisfies all hard checks on the primary runner after the documented targeted rerun. |
| Does the bundle transfer to non-GPT models? | GLM-5.2: 40 / 43, Grok Build: 36 / 43, Grok 4.3: 29 / 43, DeepSeek: 27-28 / 43 | Instructions help across models, but weaker models still miss safety/process gates. |
| Did the single-bundle refresh improve prior external-model runs? | Grok 4.3 +8 cases, Grok Build +7, GLM +3; DeepSeek unchanged | Quality improved for GPT/Grok/GLM, while DeepSeek quality moved slightly down despite unchanged hard-gate counts. |
| Does removing instructions hurt? | Current gains +10 to +24 passed cases over empty | The bundle is doing real work, especially on prompt injection, side-effecting tools, generated artifacts, branch context, dependency boundaries, and verification discovery. |
| Does it beat OpenHands `AGENTS.md` on these cases? | Current 43 / 43, OpenHands 34 / 43 | The current bundle keeps a hard-gate safety/process edge and has no high-confidence OpenHands quality wins in the latest run. |
| Does it beat a Claude-style prompt on these cases? | Current 43 / 43, Claude/Fable reference 29 / 43 | Similar pattern: large deterministic advantage, narrower pass/pass quality advantage. |

Representative quality results:

| Comparison | Current / instructed wins | Ties | Other wins | Read this as |
|---|---:|---:|---:|---|
| Current vs OpenHands reference | 37 | 3 | 3 | Strong hard-gate advantage; current also has a pass/pass quality edge. |
| Current vs Claude/Fable reference | 24 | 11 | 8 | Strong hard-gate advantage; pass/pass quality remains competitive, not one-sided. |
| GPT-5.5 instructed vs empty | 40 | 3 | 0 | Instructions clearly improve behavior under the same-day single-bundle run. |
| GLM-5.2 instructed vs empty | 40 | 0 | 0 | Strong instruction lift even on the strongest external model. |
| Grok Build 0.1 current vs previous instructions | 29 | 3 | 6 | The single-bundle refresh materially improved this model despite two residual transport failures. |
| DeepSeek V4 Flash current vs previous instructions | 13 | 4 | 16 | Hard gates were stable, but quality slightly favored the previous split-bundle run. |

See [evals/RESULTS.md](evals/RESULTS.md) for the full snapshot tables and
[evals/PROMPT_QUALITY_CASES.md](evals/PROMPT_QUALITY_CASES.md) for tracked
per-case prompt/reference quality outcomes. See
[evals/CHANGELOG.md](evals/CHANGELOG.md) for the chronological change and
metric-summary log.

## Quick Checks

Run the static contract before changing instructions or eval cases:

```bash
python3 -B scripts/run_instruction_evals.py validate
git diff --check
```

Run a local GPT-5.5 pass when model access and cost are acceptable:

```bash
export CODEX_APP_CLI=/Applications/Codex.app/Contents/Resources/codex
python3 -B scripts/run_instruction_evals.py run \
  --agent-command "$CODEX_APP_CLI -a never exec" \
  --agent-command-mode current-codex \
  --preset gpt-5.5-medium \
  --jobs 1 \
  --case-timeout-seconds 900
```

Compare the current worktree against a baseline ref with the same model and a
fixed quality judge:

```bash
python3 -B scripts/run_instruction_evals.py compare \
  --baseline-ref HEAD \
  --quality-judge \
  --agent-command "$CODEX_APP_CLI -a never exec" \
  --agent-command-mode current-codex \
  --preset gpt-5.5-medium \
  --judge-preset gpt-5.5-medium \
  --jobs 1 \
  --case-timeout-seconds 900
```

Use the Codex Desktop bundled CLI path above instead of an arbitrary `codex`
wrapper on `PATH`. Keep `-a never` before `exec` for noninteractive harness
runs. Agent-backed `run` and `compare` default to `--jobs 4`; use `--jobs 1`
for benchmark evidence.

## Documentation Map

| File | Purpose |
|---|---|
| [CRITICAL_INSTRUCTIONS.md](CRITICAL_INSTRUCTIONS.md) | Single instruction bundle: compact core plus selective advanced appendix. |
| [evals/README.md](evals/README.md) | Harness contract, command runbooks, provider adapter usage, reference-baseline setup, and artifact layout. |
| [evals/RESULTS.md](evals/RESULTS.md) | Latest benchmark snapshots and interpretation notes. |
| [evals/PROMPT_QUALITY_CASES.md](evals/PROMPT_QUALITY_CASES.md) | Per-case quality winners, deltas, confidence, and hard-gate shortcuts for tracked prompt/reference compares. |
| [evals/CHANGELOG.md](evals/CHANGELOG.md) | Chronological instruction/eval changes with compact metric deltas and conclusions. |
| [evals/cases.jsonl](evals/cases.jsonl) | Canonical eval cases and deterministic checks. |
| [evals/model-presets.json](evals/model-presets.json) | Model preset names used by the harness. |

## Maintenance Rules

- Keep root README concise: overview, current evidence, quick checks, and links.
- Put runbook details in `evals/README.md`.
- Put benchmark snapshots in `evals/RESULTS.md`.
- Put chronological instruction/eval deltas in `evals/CHANGELOG.md`.
- Keep `.eval-results/` ignored and out of commits.
- Do not commit private reference material unless redistribution is explicitly
  approved.
- For meaningful instruction changes, update eval cases and rerun the smallest
  evidence chain that proves the intended behavior.
