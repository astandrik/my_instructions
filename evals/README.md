# Instruction Evals

Legacy pre-blinding snapshot: primary prompts exposed case id/scenario metadata
(prompt contamination). The unchanged numbers are historical and are not clean
blinded instruction-lift evidence.

This directory contains the repo-local eval contract for the instruction files.

Use `RESULTS.md` for full benchmark snapshots and artifact paths. Use
`CHANGELOG.md` for the chronological summary of instruction/eval changes,
metric deltas, conclusions, and caveats.

## Blinded Six-Model Publication

Pre-semantic-alternative scorer snapshot: the unchanged figures use the prior
exact-phrase and exact-risk grader; deterministic regrade results are
diagnostic and not published.

The current publication covers six clean blinded `With instructions v4.13`
versus `Empty instructions` model/runner pairs and dual-order consensus from
`.eval-results/blinded-50-case-v1/dual-order-quality-v2/`.

Fixed dual-order quality judge: `gpt-5.6-sol-medium`.

The GPT-5.6 Sol row uses the same model family as the fixed quality judge; this is instruction-lift evidence, not a cross-model leaderboard.

These are within-runner With instructions v4.13 versus Empty instructions comparisons, not a cross-model leaderboard.

No OpenHands, Claude/Fable, or other reference rows are included.

Grok Build is excluded because repeated transport failures prevented a clean primary pair.

## Absolute Cross-Model Quality

Current-only v4.14 behavior snapshot evaluated at commit `762db4f` before the
metadata-only version/date bump; no fresh empty baseline is used for this
absolute-quality publication.

The direct model-quality publication uses independent single-response scoring,
not pairwise judge prompts. Only the 163 saved responses that passed their
deterministic hard gates are judged. Hard-gate pass rate and quality among
passed responses are separate metrics.

Sol medium is the primary judge; Terra high is an audit judge. Their scores
are shown separately and are not averaged. Direct model comparisons use only
common hard-gate-passed cases and are derived from saved absolute scores. They
require no additional model calls. No global leaderboard or rank is computed.

Canonical artifacts live under
`.eval-results/blinded-50-case-v2-762db4f/absolute-quality/canonical/`:

- `.eval-results/blinded-50-case-v2-762db4f/absolute-quality/canonical/sol-absolute.json`
- `.eval-results/blinded-50-case-v2-762db4f/absolute-quality/canonical/terra-absolute.json`
- `.eval-results/blinded-50-case-v2-762db4f/absolute-quality/canonical/sol-terra-audit.json`

Reproduce or validate the ignored artifacts with:

```bash
python3 -B scripts/run_model_absolute_quality.py plan --judge sol
python3 -B scripts/run_model_absolute_quality.py plan --judge terra
python3 -B scripts/aggregate_model_absolute_quality.py --check
```

The frozen evaluated instruction SHA-256 is
`66d8d3c5ba5c33924f54ddc83be209741a69a65b6b832aa655c5d4a5cc7140ac`;
the cases SHA-256 is
`835b074ca94be96da328e6e6a9470a0259aaa1932a5786629a0776889375ec88`.

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

When ignored `.eval-results/` artifacts are available, check that the published
blinded six-model rows and retained legacy pre-blinding metrics still match the
saved JSON, README links exactly the required SVGs, docs retain the canonical
artifact roots, and generated assets carry the matching publication scope:

```bash
python3 -B scripts/check_published_eval_metrics.py
```

The SVG scope check also rejects forbidden all-model/provider overclaims inside
generated README SVG text, so standalone images cannot publish a broader claim
than the Markdown allows.

## Regrade Saved Structured Responses

Use `regrade` when grader-only checks change but primary prompts and instruction
contents do not. It reclassifies complete saved 50-case structured responses;
it does not call a model or modify the source summaries.

```bash
python3 -B scripts/run_instruction_evals.py regrade \
  --source-summary current=.eval-results/source/current/summary.json \
  --source-summary empty=.eval-results/source/empty/summary.json \
  --output-dir .eval-results/semantic-regrade-v1
```

The output includes normal per-label summaries and `regrade-manifest.json`
with source, response-set, instruction, old-case, and new-case fingerprints.
Missing or malformed responses reject the source before any output is written.
Source agent/transport failures keep the regrade diagnostic and set
`canonical_promotion_allowed=false`.

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

- `gpt-5.6-sol-medium` -> `gpt-5.6-sol`
- `gpt-5.5-{low,medium,high,xhigh}` -> `gpt-5.5`
- `gpt-5.4-{low,medium,high,xhigh}` -> `gpt-5.4`
- `spark-{low,medium,high,xhigh}` -> `gpt-5.3-codex-spark`
- `grok-4.3-medium` -> `grok-4.3`
- `grok-build-0.1-medium` -> `grok-build-0.1`
- `deepseek-v4-flash-medium` -> `deepseek-v4-flash`
- `glm-5.2-medium` -> `glm-5.2`

The `gpt-5.6-sol-medium`, `gpt-5.5-*`, and `gpt-5.4-*` presets set
`service_tier="fast"` because the local Codex catalog advertises Fast tier for
those models. Spark presets and the external API adapter presets do not set a
service tier unless the target runtime starts advertising one.

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
lift. The primary temporary workspace contains only the candidate instruction
bundle and final-response schema. Cases, rubrics, fixtures, presets, and
reference metadata stay grader-side. The empty-bundle run materializes
`CRITICAL_INSTRUCTIONS.md` as an empty file:

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

Inline `run_instruction_evals.py compare` uses one `--agent-command` for the
primary runs and optional judge, so its judge preset defaults to the same
`gpt-5.5-medium` primary preset. Override it with Sol only when that command is
the Codex CLI or another transport that supports `gpt-5.6-sol`:

```bash
python3 scripts/run_instruction_evals.py compare --quality-judge --judge-preset gpt-5.6-sol-medium --baseline-ref HEAD --agent-command "codex exec"
python3 scripts/run_instruction_evals.py compare --quality-judge --judge-model gpt-5.6-terra --judge-reasoning-effort medium --baseline-ref HEAD --agent-command "codex exec"
```

The publication-oriented `compare_saved_model_quality.py` entry point has a
separate judge transport and defaults to `gpt-5.6-sol-medium`, which selects
`gpt-5.6-sol`, `model_reasoning_effort="medium"`, and `service_tier="fast"`.
This keeps provider-specific primary adapters separate from the fixed judge.

Keep checked-in presets to model slugs that have been verified with a real
agent run in the target Codex account. Dry-run only verifies command shape; it
does not prove the model is available.

For a metadata-only availability check, prefer the Codex model catalog. With
the Desktop-bundled CLI, the local cache is the most reliable quick check:

```bash
jq -r '
  .models[]
  | select(.slug == "gpt-5.6-sol" or .slug == "gpt-5.5" or .slug == "gpt-5.4" or .slug == "gpt-5.3-codex-spark")
  | [
      .slug,
      ([.supported_reasoning_levels[].effort] | join(",")),
      (.additional_speed_tiers | join(",")),
      ([.service_tiers[].name] | join(","))
    ]
  | @tsv
' ~/.codex/models_cache.json
```

This should show each selected Codex model slug with a reasoning column
containing `low,medium,high,xhigh`. For models that support fast mode, the
speed-tier column should include `fast`.
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
Saved-quality reports also record the fixed judge preset/model/reasoning
metadata in JSON and Markdown. Do not combine quality rows judged by different
model families in one aggregate matrix unless the rows are explicitly split and
labeled by judge; for a single all-model matrix, rerun every pair with the same
judge.

Publication-grade saved-output comparisons use the fixed
`gpt-5.6-sol-medium` judge in both semantic orders: current as baseline with
empty as candidate, then empty as baseline with current as candidate. Normalize
each verdict back to the semantic instruction side. Count a current win, empty
win, or tie only when both orders agree; otherwise mark the case
`order_sensitive`. Do not publish a single-order win count or force an
order-sensitive pair into a winner. The harness records both orders separately.
Aggregate the saved wrapper summaries offline with
`scripts/aggregate_saved_model_quality.py`; this does not call a model:

```bash
python3 -B scripts/aggregate_saved_model_quality.py \
  --repo-root . \
  --model-id <path-safe-model-id> \
  --model-label <display-label> \
  --baseline-source-summary <empty-summary.json> \
  --current-source-summary <current-summary.json> \
  --order-summary <baseline-first-model-quality-summary.json> \
  --order-summary <current-first-model-quality-summary.json> \
  --output-root .eval-results/blinded-50-case-v1/dual-order-quality-v2
```

The canonical aggregate preserves five winner buckets: `baseline`, `current`,
`tie`, `inconclusive`, and `order_sensitive`. Publication validation binds the
canonical detail back to both raw orders with source/order path, hash, and
orientation validation, then recomputes normalized comparisons before accepting
the artifact.

Quality judging is required for every pass/pass case in each row that is
published as a quality comparison or README quality infographic. It is not
required for smoke runs, transport reruns, or targeted hard-gate diagnostics
unless those runs are promoted into a published quality matrix. A provider
snapshot without complete quality coverage must stay labeled as hard-gate-only
with quality pending.

Before sending saved outputs to a model-backed judge, use the saved-quality
dry-run to review the resolved judge identity, output path, candidate rows,
number of judge calls, hard-gate shortcuts, and pass/pass case ids:

```bash
python3 -B scripts/compare_saved_model_quality.py \
  --baseline "GLM-5.2 previous=.eval-results/split/glm-5.2/baseline-HEAD/summary.json" \
  --candidate "GLM-5.2 current=.eval-results/split/glm-5.2/current/summary.json" \
  --agent-command "python3 scripts/zai_eval_agent.py" \
  --judge-preset glm-5.2-medium \
  --output-dir .eval-results/quality-glm-judge \
  --dry-run
```

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
