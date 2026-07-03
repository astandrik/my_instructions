# Instruction Evals

This directory contains the repo-local eval contract for the instruction files.

## Static gate

Run this before every instruction change. It does not call a model.

```bash
python3 scripts/run_instruction_evals.py validate
git diff --check
```

## Real agent run

Prerequisites:

- Codex CLI is installed and authenticated.
- The command passed through `--agent-command` can run `--version`.
- Network/model access is available for the chosen model.

Every agent eval case runs against the same candidate instruction bundle:
`CRITICAL_INSTRUCTIONS.md` plus `ADVANCED_PATTERNS_REFERENCE.md`. The advanced
file is always available to the eval agent, but the expected behavior remains
selective: use it only when the task shape triggers the optional appendix.
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

The `gpt-5.5-*` and `gpt-5.4-*` presets set `service_tier="fast"` because
the local Codex catalog advertises Fast tier for those models. Spark presets
do not set a service tier unless the target account catalog starts advertising
one.

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

## External Reference Baselines

Reference bundles live in `evals/reference-instructions.json`. They let the
same cases compare local instructions against a public instruction source
without copying the full external text into this repository.

The first checked-in reference is `openhands-agents`: OpenHands' public
`AGENTS.md`, selected because OpenHands is a major open-source coding-agent
project and the file is a real agent instruction file. The bundle pins the raw
URL with a SHA256 hash and maps it to `CRITICAL_INSTRUCTIONS.md`; the advanced
appendix file is intentionally empty because that reference is single-file.

`validate` checks the reference config shape but does not fetch external URLs.
Actual `compare --baseline-reference ...` runs fetch and hash-check the pinned
content before invoking the eval agent.

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
```

Preview the reference comparison command shape without fetching or running the
agent:

```bash
python3 scripts/run_instruction_evals.py compare --baseline-reference openhands-agents --quality-judge --agent-command "codex exec" --dry-run
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

The public reference comparison snapshot lives in the root `README.md`.

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
