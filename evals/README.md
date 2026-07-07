# Instruction Evals

This directory contains the repo-local eval contract for the instruction files.

Use `RESULTS.md` for full benchmark snapshots and artifact paths. Use
`CHANGELOG.md` for the chronological summary of instruction/eval changes,
metric deltas, conclusions, and caveats.

## Static gate

Run this before every instruction change. It does not call a model.

```bash
python3 scripts/run_instruction_evals.py validate
git diff --check
```

When README SVGs are part of the change, check generated-artifact freshness:

```bash
python3 -B scripts/build_readme_infographics.py --check
```

When ignored `.eval-results/` artifacts are available, check that published
GPT/Codex metrics still match the saved JSON, docs keep the GPT-only caveats
and a pointer to the saved artifact root, `summary.json` and `quality.json`
describe the same case set, README links every required SVG, README SVGs keep
their scope footer, and docs do not overclaim all-model v4.13 scope, including
common phrasing variants such as "all models" and "re-run":

```bash
python3 -B scripts/check_published_eval_metrics.py
```

## Real agent run

Prerequisites:

- Codex CLI is installed and authenticated.
- The command passed through `--agent-command` can run `--version`.
- Network/model access is available for the chosen model.

Every agent eval case runs against the same candidate instruction bundle:
`CRITICAL_INSTRUCTIONS.md`. That file contains the compact core plus a
selective advanced appendix; expected behavior remains selective, so simple
tasks should not activate advanced workflow unless the task shape requires it.
The markdown task tables are validated for scenario consistency, but they are
not included in the candidate instruction prompt.

The default eval model is `gpt-5.5` with `model_reasoning_effort="medium"` and `service_tier="fast"`.
Presets live in `evals/model-presets.json`; list them with:

```bash
python3 scripts/run_instruction_evals.py presets
```

The checked-in presets currently cover:

- `gpt-5.5-{low,medium,high,xhigh}` -> `gpt-5.5`
- `gpt-5.4-{low,medium,high,xhigh}` -> `gpt-5.4`
- `spark-{low,medium,high,xhigh}` -> `gpt-5.3-codex-spark`
- `grok-4.3-medium` -> `grok-4.3`
- `grok-build-0.1-medium` -> `grok-build-0.1`
- `deepseek-v4-flash-medium` -> `deepseek-v4-flash`
- `glm-5.2-medium` -> `glm-5.2`

The `gpt-5.5-*` and `gpt-5.4-*` presets set `service_tier="fast"` because
the local Codex catalog advertises Fast tier for those models. Spark presets
and the external API adapter presets do not set a service tier unless the
target runtime starts advertising one.

Preview the exact commands without running a model:

```bash
python3 scripts/run_instruction_evals.py run --agent-command "codex exec" --dry-run
```

For newer Codex CLI flag sets, use the current command profile. It avoids legacy
flags that the newer CLI no longer accepts, disables user plugin/MCP loading,
uses an ephemeral session, and passes the final-response JSON schema to the
isolated eval process:

```bash
python3 scripts/run_instruction_evals.py run --agent-command "codex exec" --agent-command-mode current-codex --dry-run
python3 scripts/run_instruction_evals.py run --agent-command "codex exec" --agent-command-mode current-codex --jobs 1
```

Run the same cases with an empty instruction bundle when measuring instruction
lift. This keeps eval cases, schemas, presets, and reference metadata available
in the temporary workspace, but materializes `CRITICAL_INSTRUCTIONS.md` as an
empty file:

```bash
python3 scripts/run_instruction_evals.py run \
  --instruction-bundle empty \
  --agent-command "codex exec" \
  --agent-command-mode current-codex \
  --jobs 1
```

### Codex Desktop bundled CLI runbook

For ChatGPT-account model access from Codex Desktop, prefer the app-bundled CLI
explicitly. The `codex` executable found first on `PATH` may be an older
Homebrew/npm CLI and may use different authentication state.

```bash
export CODEX_APP_CLI=/Applications/Codex.app/Contents/Resources/codex
"$CODEX_APP_CLI" --version
"$CODEX_APP_CLI" login --device-auth
```

Keep the device-auth process running until it prints `Successfully logged in`.
If the process is interrupted before browser confirmation finishes, the login
state is not saved.

Use a real one-line `exec` probe as the final readiness check:

```bash
"$CODEX_APP_CLI" -a never exec \
  -c 'mcp_servers={}' \
  -c 'model_reasoning_effort="medium"' \
  -c 'service_tier="fast"' \
  --model gpt-5.5 \
  --skip-git-repo-check \
  --output-last-message scratch/gpt55-probe-last-message.txt \
  'Return exactly: ok'
```

Run all current cases against the live model:

```bash
python3 -B scripts/run_instruction_evals.py run \
  --agent-command "$CODEX_APP_CLI -a never exec" \
  --agent-command-mode current-codex \
  --preset gpt-5.5-medium \
  --jobs 1 \
  --case-timeout-seconds 900 \
  --output-dir .eval-results/gpt55-medium-full
```

`-a never` must appear before `exec`; it is a global Codex CLI option. The
`gpt-5.5-medium` preset selects `gpt-5.5`, `model_reasoning_effort="medium"`,
and `service_tier="fast"`.

Use `--jobs 1` for benchmark or gated evidence. `--jobs 4` is useful for
exploratory runs, but concurrent real-model processes can create runtime noise
or hangs, so write parallel experiments to a separate output directory and keep
a sequential rerun for final evidence.

If the agent command starts but does not finish, add an explicit timeout while
debugging so the runner records an agent failure instead of hanging:

```bash
python3 scripts/run_instruction_evals.py run --agent-command "codex exec" --agent-command-mode current-codex --jobs 1 --case-timeout-seconds 900
```

Switch reasoning with a preset:

```bash
python3 scripts/run_instruction_evals.py run --preset gpt-5.5-medium --agent-command "codex exec"
python3 scripts/run_instruction_evals.py run --preset gpt-5.5-xhigh --agent-command "codex exec"
python3 scripts/run_instruction_evals.py run --preset gpt-5.4-medium --agent-command "codex exec"
python3 scripts/run_instruction_evals.py run --preset spark-high --agent-command "codex exec"
python3 scripts/run_instruction_evals.py compare --preset spark-medium --baseline-ref HEAD --agent-command "codex exec"
```

Override preset fields ad hoc when a preset is close but not exact:

```bash
python3 scripts/run_instruction_evals.py run --preset spark-xhigh --reasoning-effort medium --agent-command "codex exec"
python3 scripts/run_instruction_evals.py run --preset spark-xhigh --model <model-slug> --reasoning-effort high --agent-command "codex exec"
python3 scripts/run_instruction_evals.py run --preset gpt-5.5-medium --service-tier flex --agent-command "codex exec"
```

The optional quality judge defaults to the same `gpt-5.5-medium` preset. Override
it independently when needed:

```bash
python3 scripts/run_instruction_evals.py compare --quality-judge --judge-preset gpt-5.5-high --baseline-ref HEAD --agent-command "codex exec"
python3 scripts/run_instruction_evals.py compare --quality-judge --judge-model gpt-5.5 --judge-reasoning-effort high --baseline-ref HEAD --agent-command "codex exec"
```

Keep checked-in presets to model slugs that have been verified with a real
agent run in the target Codex account. Dry-run only verifies command shape; it
does not prove the model is available.

For a metadata-only availability check, prefer the Codex model catalog. With
the Desktop-bundled CLI, the local cache is the most reliable quick check:

```bash
jq -r '
  .models[]
  | select(.slug == "gpt-5.5" or .slug == "gpt-5.4" or .slug == "gpt-5.3-codex-spark")
  | [
      .slug,
      ([.supported_reasoning_levels[].effort] | join(",")),
      (.additional_speed_tiers | join(",")),
      ([.service_tiers[].name] | join(","))
    ]
  | @tsv
' ~/.codex/models_cache.json
```

This should show all checked-in model slugs with a reasoning column containing
`low,medium,high,xhigh`. For models that support fast mode, the speed-tier
column should include `fast`.
If a future CLI exposes `codex debug models`, that command is also acceptable
as a metadata check. A successful real `codex exec --model ...` probe remains
the runtime source of truth.
Do not add aliases such as `gpt-5.5-codex`, `gpt-5.4-codex`, `*-thinking`,
`*-pro`, or `o3` unless they appear in the target account's Codex catalog or
pass a real `codex exec --model ...` probe. Official API model docs can
confirm public model IDs, but Codex account access is the runtime source of
truth for these eval presets.

## xAI / Grok Model-Only Runs

`scripts/xai_eval_agent.py` is a narrow adapter for running the same eval cases
against xAI/Grok structured outputs. It is not a full Codex agent runtime: it
does not expose shell tools, MCP, file edits, or a tool loop. Use it to measure
instruction-following transfer across models, not to compare full agent
capability.

Use the adapter instead of configuring Grok as a Codex custom provider for
these evals. Current Codex custom providers use the Responses API path, while
the verified xAI structured-output path here is Chat Completions; provider
probes can fail before model output if Codex sends a tool payload that xAI does
not accept.

Keep the xAI key out of this repository. For local macOS runs, one safe pattern
is to store the key in Keychain and export it only for the command:

```bash
security add-generic-password -U -a "$USER" -s codex-xai-api-key -w '<xai-api-key>'
export XAI_API_KEY="$(security find-generic-password -a "$USER" -s codex-xai-api-key -w)"
```

Smoke one case before a broad run:

```bash
python3 -B scripts/run_instruction_evals.py run \
  --case prompt-injection-file-data \
  --agent-command "python3 scripts/xai_eval_agent.py" \
  --agent-command-mode current-codex \
  --preset grok-4.3-medium \
  --jobs 1 \
  --case-timeout-seconds 900 \
  --output-dir .eval-results/grok-4.3-smoke
```

Then run the current bundle:

```bash
python3 -B scripts/run_instruction_evals.py run \
  --agent-command "python3 scripts/xai_eval_agent.py" \
  --agent-command-mode current-codex \
  --preset grok-4.3-medium \
  --jobs 1 \
  --case-timeout-seconds 900 \
  --output-dir .eval-results/grok-4.3-current
```

Switch `--preset` and `--output-dir` to run another xAI model, for example
`grok-build-0.1-medium` with `.eval-results/grok-build-0.1-current`.

For transfer measurement, compare Grok and GPT on the same case set and keep a
stable judge model. The useful metric is instruction lift per model, not raw
Grok-vs-GPT score. If the quality judge remains Codex/GPT-backed, label the
judge separately from the Grok primary run.

## DeepSeek Model-Only Runs

`scripts/deepseek_eval_agent.py` is the DeepSeek equivalent of the xAI adapter.
DeepSeek documents OpenAI-compatible Chat Completions at
`https://api.deepseek.com` and exposes `deepseek-v4-flash`. Its JSON Output
mode uses `response_format={"type":"json_object"}` rather than JSON Schema, so
the adapter puts `evals/final-response.schema.json` into the system prompt and
the eval runner remains the schema validator.
The adapter sends `thinking={"type":"disabled"}` by default; set
`DEEPSEEK_THINKING=enabled` only for a deliberately separate thinking-mode run.

Keep the DeepSeek key out of this repository. For local macOS runs:

```bash
security add-generic-password -U -a "$USER" -s codex-deepseek-api-key -w '<deepseek-api-key>'
export DEEPSEEK_API_KEY="$(security find-generic-password -a "$USER" -s codex-deepseek-api-key -w)"
```

Smoke one case first:

```bash
python3 -B scripts/run_instruction_evals.py run \
  --case prompt-injection-file-data \
  --agent-command "python3 scripts/deepseek_eval_agent.py" \
  --agent-command-mode current-codex \
  --preset deepseek-v4-flash-medium \
  --jobs 1 \
  --case-timeout-seconds 900 \
  --output-dir .eval-results/deepseek-v4-flash-smoke
```

Then run the current bundle:

```bash
python3 -B scripts/run_instruction_evals.py run \
  --agent-command "python3 scripts/deepseek_eval_agent.py" \
  --agent-command-mode current-codex \
  --preset deepseek-v4-flash-medium \
  --jobs 1 \
  --case-timeout-seconds 900 \
  --output-dir .eval-results/deepseek-v4-flash-current
```

## Z.ai / GLM Model-Only Runs

`scripts/zai_eval_agent.py` runs the same model-only eval contract against
Z.ai GLM models. Z.ai documents OpenAI-compatible Chat Completions at
`https://api.z.ai/api/paas/v4/`, model `glm-5.2`, and structured output through
`response_format={"type":"json_object"}`. The adapter therefore follows the
DeepSeek-style JSON-mode path: it puts `evals/final-response.schema.json` into
the system prompt and lets the eval runner validate the final response.

The adapter sends `thinking={"type":"enabled"}` by default for GLM-5.2 and
uses the preset's `model_reasoning_effort` value as `reasoning_effort`. Override
locally with `ZAI_THINKING`, `ZAI_REASONING_EFFORT`, or `ZAI_MAX_TOKENS` only
when intentionally measuring a separate mode.

Keep the Z.ai key out of this repository. For local macOS runs:

```bash
security add-generic-password -U -a "$USER" -s codex-zai-api-key -w '<zai-api-key>' "$HOME/Library/Keychains/login.keychain-db"
export ZAI_API_KEY="$(security find-generic-password -a "$USER" -s codex-zai-api-key -w "$HOME/Library/Keychains/login.keychain-db")"
```

Smoke one case first:

```bash
python3 -B scripts/run_instruction_evals.py run \
  --case prompt-injection-file-data \
  --agent-command "python3 scripts/zai_eval_agent.py" \
  --agent-command-mode current-codex \
  --preset glm-5.2-medium \
  --jobs 1 \
  --case-timeout-seconds 900 \
  --output-dir .eval-results/glm-5.2-smoke
```

Then run the current bundle:

```bash
python3 -B scripts/run_instruction_evals.py run \
  --agent-command "python3 scripts/zai_eval_agent.py" \
  --agent-command-mode current-codex \
  --preset glm-5.2-medium \
  --jobs 1 \
  --case-timeout-seconds 900 \
  --output-dir .eval-results/glm-5.2-current
```

## External Reference Baselines

Reference bundles live in `evals/reference-instructions.json`. They let the
same cases compare local instructions against another instruction source with
a hash-checked local mirror.

The checked-in references are:

- `openhands-agents`: OpenHands' public `AGENTS.md`, selected because
  OpenHands is a major open-source coding-agent project and the file is a real
  agent instruction file. The bundle maps the local mirror at
  `evals/references/openhands-agents/AGENTS.md` to
  `CRITICAL_INSTRUCTIONS.md` and verifies it with a SHA256 hash.
- `claude-fable-5`: the Claude/Fable-style prompt mirror at
  `evals/references/claude-agents/CLAUDE-FABLE-5.md`, used as a reference
  prompt for the tracked Fable comparison snapshot.

For `compare --baseline-ref`, the runner keeps legacy fairness for refs that
still have the old split bundle: it merges `CRITICAL_INSTRUCTIONS.md` plus
`ADVANCED_PATTERNS_REFERENCE.md` from the baseline ref into the single baseline
`CRITICAL_INSTRUCTIONS.md` before running cases.

`validate` checks the reference config shape. Actual
`compare --baseline-reference ...` runs hash-check the local mirror before
invoking the eval agent. To refresh a mirrored external reference, update the
local file and its SHA256 together in `evals/reference-instructions.json`.

Run all cases against the current instruction files:

```bash
python3 scripts/run_instruction_evals.py run --agent-command "codex exec"
```

Agent-backed `run` and `compare` use `--jobs 4` by default. Use `--jobs 1` for
sequential debugging, or lower the value if the account hits rate limits.
Use `--case-timeout-seconds <seconds>` for bounded local runs; timed-out cases
write `timeout.txt` next to their normal artifacts and count as agent failures.
Dry-run output remains stable and ordered even when `--jobs` is greater than 1.

Run one case:

```bash
python3 scripts/run_instruction_evals.py run --case privacy-persistent-state --agent-command "codex exec"
```

Compare a baseline ref with the current working tree:

```bash
python3 scripts/run_instruction_evals.py compare --baseline-ref HEAD --agent-command "codex exec"
```

This is the default comparison gate when changing instructions. It answers
whether baseline/current pass the deterministic safety and regression checks,
but it does not score answer quality.

Add the optional quality judge when you need a local better/worse comparison:

```bash
python3 scripts/run_instruction_evals.py compare --baseline-ref HEAD --quality-judge --agent-command "codex exec"
```

The quality judge compares baseline/current structured final responses against
the case rubric and writes winner, score, confidence, and rationale fields. It
is local-only and not a CI default because it adds model cost and possible
judge variance.

Compare against the public OpenHands reference instead of a git ref:

```bash
python3 scripts/run_instruction_evals.py compare --baseline-reference openhands-agents --agent-command "codex exec"
python3 scripts/run_instruction_evals.py compare --baseline-reference openhands-agents --quality-judge --agent-command "codex exec"
python3 scripts/run_instruction_evals.py compare --baseline-reference claude-fable-5 --quality-judge --agent-command "codex exec"
```

Preview the reference comparison command shape without fetching or running the
agent:

```bash
python3 scripts/run_instruction_evals.py compare --baseline-reference openhands-agents --quality-judge --agent-command "codex exec" --dry-run
python3 scripts/run_instruction_evals.py compare --baseline-reference claude-fable-5 --quality-judge --agent-command "codex exec" --dry-run
```

If the global `codex` wrapper is not the executable you want, pass an absolute command instead:

```bash
python3 scripts/run_instruction_evals.py run --agent-command "/path/to/codex exec"
```

## Results

The runner writes artifacts under `.eval-results/`, which is intentionally gitignored:

- `.eval-results/current/summary.md`
- `.eval-results/current/summary.json`
- `.eval-results/current/<case-id>/events.jsonl`
- `.eval-results/current/<case-id>/stderr.txt`
- `.eval-results/current/<case-id>/final-message.json`

When deterministic checks change after a completed model run, keep the raw run
artifacts and write any reclassified summaries to a clearly named separate
output directory. Do not present a reclassified summary as a fresh model run.

For `compare`, the summary is written under `.eval-results/compare-<baseline-ref>-current/`.
The same directory also contains:

- `quality.md`: side-by-side comparison of baseline/current structured final responses
- `quality.json`: machine-readable version of the same quality comparison
- `judge/<case-id>/events.jsonl`, `stderr.txt`, and `final-message.json` when `--quality-judge` is used

`compare` summaries contain both sides in one `summary.json`, distinguished by
their `label` fields such as `baseline-HEAD` and `current`. Split those files
before passing them to `scripts/compare_saved_model_quality.py`, which expects
one side per input summary:

```bash
python3 -B scripts/split_eval_summary.py \
  --input .eval-results/compare-HEAD-current/summary.json \
  --output-dir .eval-results/split/compare-HEAD-current
```

The saved-quality script rejects duplicate `case_id` values in a single input
summary so combined compare summaries cannot silently overwrite one side.

Without `--quality-judge`, the quality report is descriptive, not an LLM judge
score. It compares stable signals from `final-message.json`: pass state,
decision, risk level, evidence count, action count, and summary text.

With `--quality-judge`, the report adds `winner`, `baseline_score`,
`current_score`, `delta`, `confidence`, `review_needed`, and `reason`. Hard
gate disagreements are decided without invoking the judge; pass/pass cases are
sent to a second structured Codex run using `evals/quality-judge.schema.json`.
`expected_behavior`, `forbidden_behavior`, and `rubric` from `cases.jsonl` are
grader-only for the primary eval agent and are only included in the optional
judge prompt.

Benchmark snapshots live in `evals/RESULTS.md`; the root `README.md` keeps only
the current evidence summary and links.

Structured `decision` semantics:

- `pass`: proceed or answer normally within the task
- `no_op`: no mutation or external action is needed because analysis, no change, already-resolved, environment-only handling, or a safety decision to ignore/refuse untrusted content is enough
- `needs_approval`: a mutation, external side effect, destructive action, or high-risk step needs explicit user approval first
- `blocked`: no meaningful safe progress is possible without missing access, input, or tool state
- `fail`: the instruction set cannot safely satisfy the request

`deterministic_checks` supports:

- `required_final_contains`: phrases that must appear in the final response
- `forbidden_final_contains`: phrases that must not appear in the final response
- `required_decision`: expected structured `decision` value from `final-message.json`
- `required_risk_level`: expected structured `risk_level` value from `final-message.json`
- `required_summary_contains`: phrases that must appear in the structured `summary`
- `required_evidence_contains`: phrases that must appear in the structured `evidence`
- `required_actions_contains`: phrases that must appear in the structured `actions`

Exit codes:

- `0`: all selected evals passed
- `2`: harness/preflight failure
- `3`: agent execution failure
- `4`: instruction behavior failure

Agent runs are local-only by default. CI should use `validate` unless a separate workflow explicitly provides credentials and cost controls.
