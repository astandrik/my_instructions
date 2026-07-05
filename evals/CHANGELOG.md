# Instruction Metrics Changelog

This changelog records instruction-bundle changes together with the shortest
useful metric summary. It is not a replacement for `evals/RESULTS.md`: keep
full benchmark tables and artifact paths there, and use this file for the
chronological "what changed, what moved, what we learned" view.

Add an entry when:

- `CRITICAL_INSTRUCTIONS.md` version or structure changes;
- eval cases, deterministic checks, schemas, or reference bundles change;
- a full or publication-grade comparison materially changes the interpretation
  of instruction quality.

For each entry, record the artifact path, hard-gate result, quality result,
main conclusion, and caveats. Prefer stable behavior conclusions over long raw
tables.

## 2026-07-05 - v4.12 GPT-5.5 Watchlist Micro-Calibration

Instruction surface:

- Updated `CRITICAL_INSTRUCTIONS.md` from v4.11 to v4.12.
- Kept the change narrow: no new eval cases, schemas, references, scripts, or
  README SVG assets.
- Added targeted wording for workflow-selection `no_op`, read-only risk
  classification, fail-before/pass-after action evidence, tool-output
  utility/security and exfiltration framing, context-overhead metrics,
  architecture/ADR traceability, and skill/eval trigger controls.

Artifacts:

- Focused GPT-5.5 compare:
  `.eval-results/v4.12-watchlist-compare-gpt55/compare-HEAD-current/summary.md`
- Focused standalone probes:
  `.eval-results/v4.12-watchlist-gpt55-r2/`,
  `.eval-results/v4.12-watchlist-gpt55-r3/`,
  `.eval-results/v4.12-watchlist-gpt55-r4/`
- Targeted residual probes:
  `.eval-results/v4.12-residual-characterization-r2/`,
  `.eval-results/v4.12-residual-tool-output/`

Verification:

- `python3 -B scripts/run_instruction_evals.py validate`
  passed with `cases=49 markdown_tables=2 presets=16 references=2`.
- `git diff --check` passed.
- `python3 -B -m unittest tests/test_instruction_eval_runner.py` passed
  outside the sandbox with 36 tests. The sandboxed run failed before product
  code because Python had no writable temporary directory.

Metric snapshot:

| Focused GPT-5.5 check | Baseline v4.11 | Current v4.12 |
|---|---:|---:|
| 7-case compare hard gates | 1 / 7 | 6 / 7 |
| Current hard-gate wins | - | 5 |
| Pass/pass ties | - | 1 |
| Both-fail residual | - | 1 |

Focused compare details:

- Current fixed hard gates for `eval-task-reward-hacking-resistance`,
  `context-file-overhead-budget`, `adr-violation-evidence`,
  `characterization-test-before-fix`, and
  `architecture-traceability-link-recovery`.
- `skill-invocation-trigger-controls` passed on both sides in this compare,
  even though earlier saved snapshots showed it as a current watchlist miss.
- `tool-output-prompt-injection-utility-security` remained both-fail in the
  compare because strict `utility` / `exfiltration` wording was still
  stochastic.

Conclusion:

- v4.12 is a net focused improvement for GPT-5.5 on the expanded watchlist, but
  not a complete fix. The useful change is better operational salience around
  no-op workflow decisions, read-only risk calibration, traceability, and
  eval/skill controls.
- The remaining honest caveat is tool-output injection wording: behavior is
  safe, but the strict lexical gate still varies.

Caveats:

- This is focused 7-case evidence, not a full refreshed 49-case benchmark.
- Standalone focused runs were variance-sensitive: saved full 7-case runs
  reached 5 / 7 twice and 3 / 7 once, while targeted residual one-case reruns
  passed. Treat the compare result as the primary patch evidence.

## 2026-07-05 - 49-Case Model and Reference Refresh

Instruction surface:

- No instruction text change: `HEAD == origin/main`, and
  `CRITICAL_INSTRUCTIONS.md`, reference mirrors, and legacy appendix files had
  no local diff.
- Refreshed all tracked model, empty/no-instructions, cross-model quality, and
  reference quality metrics on the expanded 49-case suite.
- Previous-vs-current instruction comparison is not applicable for this pass:
  the current worktree only changes eval/docs/tests, not the instruction
  bundle.

Artifacts:

- `.eval-results/refresh-2026-07-05-49-case-v1/`
- GPT-vs-external quality:
  `.eval-results/refresh-2026-07-05-49-case-v1/quality-gpt55-vs-external-current/GPT-5.5-current-saved-model-quality/model-quality-summary.md`
- OpenHands/Fable per-case quality:
  `evals/PROMPT_QUALITY_CASES.md`

Metric snapshot:

| Model | Current hard gates | Empty hard gates | Current-vs-empty quality | GPT-vs-external quality |
|---|---:|---:|---|---|
| GPT-5.5 | 42 / 49 | 28 / 49 | current 41, empty 1, tie 1 | baseline |
| Grok 4.3 | 28 / 49 | 9 / 49 | current 28, empty 1, tie 0 | GPT 42, Grok 0, tie 0 |
| Grok Build 0.1 | 36 / 49 | 13 / 49 | current 34, empty 4, tie 0 | GPT 30, Grok Build 4, tie 8 |
| DeepSeek V4 Flash | 29 / 49 | 11 / 49 | current 23, empty 4, tie 4 | GPT 42, DeepSeek 0, tie 0 |
| DeepSeek V4 Flash thinking | 26 / 49 | 6 / 49 | current 24, empty 1, tie 2 | GPT 42, DeepSeek thinking 0, tie 0 |
| GLM-5.2 | 41 / 49 | 17 / 49 | current 38, empty 1, tie 2 | GPT 19, GLM 15, tie 9 |

Reference quality:

| Reference | Reference hard gates | Current-side hard gates | Current wins | Reference wins | Ties | Inconclusive |
|---|---:|---:|---:|---:|---:|---:|
| OpenHands `AGENTS.md` | 32 / 49 | 42 / 49 | 32 | 1 | 10 | 6 |
| Claude/Fable prompt | 34 / 49 | 44 / 49 | 37 | 6 | 2 | 4 |

Conclusion:

- Instruction lift remains large across every tested model on the expanded
  suite.
- GLM-5.2 is the closest external fallback candidate: it still trails GPT-5.5
  on hard gates, but pass/pass quality is competitive.
- The expanded cases are doing useful work: they exposed current watchlist
  misses in skill invocation, context-overhead risk calibration, ADR evidence,
  characterization-test wording, traceability links, and tool-output
  injection/utility framing.
- Current still beats OpenHands and Fable references in aggregate, but the new
  suite found real reference wins: OpenHands on
  `skill-invocation-trigger-controls`, Fable on
  `characterization-test-before-fix`, plus several pass/pass Fable wins.

Caveats:

- External adapter runs are model-only structured-output runs, not full Codex
  shell/MCP/file-edit agent loops.
- Grok Build 0.1 current has 3 residual xAI transport/agent failures after
  targeted reruns.
- Current-side hard-gate count varies between standalone and reference compare
  runs because GPT final-response wording is stochastic on strict new cases.

## 2026-07-05 - Fable-Era Eval Coverage Expansion

Instruction surface:

- No `CRITICAL_INSTRUCTIONS.md` text change.
- Expanded `evals/cases.jsonl` from 43 to 49 cases using patterns from the
  Claude Fable research pass and related benchmark families: OpenAI skill evals,
  AgentIF/OctoBench, Vercel AGENTS-vs-skills, SWE Atlas/SWE-QA-Pro,
  ArchBench/R2ABench/SAKE, SABER, AgentDojo, and InjecAgent.
- Added compact cases for skill trigger controls, context-file overhead,
  ADR violation evidence, characterization tests before fixes, architecture
  traceability links, and tool-output prompt injection with utility preservation.

Metric snapshot:

- Static validation is the required gate for this entry.
- A fresh 49-case model/reference refresh was produced later the same day; see
  the entry above for the measured results.

Conclusion:

- The eval suite now tests more of the Fable-era capabilities that matter for
  instruction quality: skill invocation, context-surface cost, logical
  traceability, evidence-first architecture review, fail-before/pass-after test
  design, and preserving utility while ignoring injected tool-output
  instructions.

Caveats:

- Historical 43-case model/reference metrics remain useful as the previous
  snapshot but are no longer complete coverage for the expanded suite.

## 2026-07-05 - v4.11 Cross-Model Refresh

Instruction surface:

- No instruction text change from the v4.11 single-bundle calibration.
- Refreshed all tracked model rows on the current single-bundle instructions:
  GPT-5.5, Grok 4.3, Grok Build 0.1, DeepSeek V4 Flash, DeepSeek V4 Flash
  thinking, and GLM-5.2.
- Reran empty/no-instructions baselines only for same-day instruction-lift
  comparability, not because the empty bundle changed.
- Added same-model quality comparisons for previous-vs-current instructions:
  `GPT-prev` vs `GPT-current`, `Grok-prev` vs `Grok-current`, and equivalent
  pairs for the other tracked models.

Metric snapshot:

| Model | Previous hard gates | Current hard gates | Empty hard gates | Prev -> current quality |
|---|---:|---:|---:|---|
| GPT-5.5 | 43 / 43 | 43 / 43 | 33 / 43 | current 30, previous 5, tie 8, avg delta +1.9 |
| Grok 4.3 | 21 / 43 | 29 / 43 | 7 / 43 | current 20, previous 11, tie 2, avg delta +19.7 |
| Grok Build 0.1 | 29 / 43 | 36 / 43 | 12 / 43 | current 29, previous 6, tie 3, avg delta +18.0 |
| DeepSeek V4 Flash | 27 / 43 | 27 / 43 | 9 / 43 | current 13, previous 16, tie 4, avg delta -2.8 |
| DeepSeek V4 Flash thinking | 28 / 43 | 28 / 43 | 8 / 43 | current 12, previous 18, tie 4, avg delta -1.2 |
| GLM-5.2 | 37 / 43 | 40 / 43 | 21 / 43 | current 24, previous 13, tie 5, avg delta +7.6 |

Current-vs-empty quality remained strongly positive for every model:
GPT-5.5 current won 40 cases, Grok 4.3 29, Grok Build 36, DeepSeek V4 Flash
25, DeepSeek V4 Flash thinking 28, and GLM-5.2 40.

Artifacts:

- `.eval-results/refresh-2026-07-05-single-bundle-v1/`
- Same-model quality pairs are under `quality-same-model-*` in that artifact
  family, except GPT-5.5 which uses the valid pair already produced under
  `quality-prev-current-vs-gpt55-prev`.

Conclusion:

- The single-bundle refresh improved transfer for Grok 4.3, Grok Build 0.1,
  and GLM-5.2, while GPT-5.5 stayed at 43 / 43 and improved slightly on
  quality.
- DeepSeek V4 Flash variants did not gain hard-gate coverage and slightly
  regressed in same-model quality, so they remain the main watchlist models for
  wording sensitivity.
- Instruction lift versus empty remains large across every tested model.

Caveats:

- External adapter runs are model-only structured-output runs, not full Codex
  shell/MCP/file-edit agent loops.
- Grok Build 0.1 current still has 2 residual agent failures from xAI remote
  disconnects after targeted reruns.
- A broad `GPT-5.5-prev` vs all-candidates quality run was interrupted because
  it answered cross-model distance rather than same-model instruction delta;
  only the valid GPT same-model pair from that artifact is used.

## 2026-07-05 - v4.11 Single-Bundle Calibration

Instruction surface:

- Merged the old optional `ADVANCED_PATTERNS_REFERENCE.md` into
  `CRITICAL_INSTRUCTIONS.md` as a selective advanced appendix.
- Kept baseline fairness for old refs by materializing legacy
  `CRITICAL_INSTRUCTIONS.md` plus `ADVANCED_PATTERNS_REFERENCE.md` only in the
  baseline workspace.
- Cleaned brittle deterministic checks after an overfitting audit. Prompts,
  expected behavior, forbidden behavior, and rubrics stayed unchanged; cleanup
  replaced exact lexical gates such as `poison`, `keyword`, `approach`,
  `concurrent`, `boundary`, and `false positive` with scenario-level markers.

Metric snapshot:

| Comparison | Artifact | Current | Baseline/reference | Quality |
|---|---|---:|---:|---|
| Current vs `origin/main` diagnostic | `.eval-results/full-single-bundle-v14-anti-overfit-jobs4` | 43 / 43 | 40 / 43 | current 34, baseline 3, tie 6 |
| Current vs OpenHands reference | `.eval-results/compare-openhands-single-bundle-v15-jobs1` | 43 / 43 | 34 / 43 | current 37, OpenHands 3, tie 3 |

### Previous vs Current Instructions

Use this block to answer "what changed compared with the previous checked-in
instructions?" The baseline is `origin/main` at the time of the run:
`CRITICAL_INSTRUCTIONS.md` v4.9 plus `ADVANCED_PATTERNS_REFERENCE.md` v2.7,
materialized as the old split bundle. The current side is the local v4.11
single-file bundle in `CRITICAL_INSTRUCTIONS.md`.

Artifacts:

- `.eval-results/full-single-bundle-v14-anti-overfit-jobs4/compare-origin-main-current/summary.md`
- `.eval-results/full-single-bundle-v14-anti-overfit-jobs4/compare-origin-main-current/quality.md`

| Metric | Previous instructions | Current instructions |
|---|---:|---:|
| Hard-gate passed | 40 / 43 | 43 / 43 |
| Quality wins | 3 | 34 |
| Ties | 6 | 6 |
| Average score, all cases | 86.4 | 95.5 |
| Average score, pass/pass cases | 92.9 | 95.2 |

Current fixed three deterministic gaps from the previous instructions:

- `architecture-map-before-edit`
- `concurrency-idempotency`
- `existing-architecture-decision-check`

Previous instructions still had three medium-confidence pass/pass quality wins:

- `performance-claim-requires-measurement`
- `architectural-smell-triage`
- `implicit-review-comment-comprehension`

There were no high-confidence previous-instruction wins in this diagnostic
snapshot. The run used `--jobs 4`, so it is regression evidence rather than the
publication-grade reference snapshot.

Conclusion:

- The single-bundle shape did not regress hard-gate coverage.
- The anti-overfit cleanup made deterministic checks less word-fragile without
  erasing the quality signal: targeted cleaned cases still favored current on
  quality.
- The latest publication-grade OpenHands comparison has no high-confidence
  OpenHands wins. Remaining OpenHands wins are medium-confidence pass/pass
  deltas on available-tool use, review signal/noise, and read-only lookup
  wording.

Caveats:

- `origin/main` diagnostic used `--jobs 4`; treat it as regression signal, not
  publication evidence.
- The original calibration comparison did not include cross-model refresh rows;
  see the later 2026-07-05 cross-model refresh entry above.

## 2026-07-04 - Split-Bundle Transfer and Instruction-Lift Snapshot

Instruction surface:

- Historical split bundle:
  `CRITICAL_INSTRUCTIONS.md` plus `ADVANCED_PATTERNS_REFERENCE.md`.
- Same 43 eval cases were used for GPT-5.5, external model-only adapters,
  empty-bundle runs, and a Claude/Fable prompt reference.

Metric snapshot:

| Comparison | Artifact family | Instructed/current | Baseline/reference | Quality |
|---|---|---:|---:|---|
| GPT-5.5 instructed vs empty | `.eval-results/no-instructions-gpt55-current` | 43 / 43 | 26 / 43 | instructed 36, empty 1, tie 6 |
| GLM-5.2 instructed vs empty | `.eval-results/no-instructions-glm-5.2-current-merged` | 37 / 43 | 19 / 43 | instructed 37, empty 1, tie 0 |
| Current vs Claude/Fable reference | `.eval-results/compare-claude-fable-gpt55` | 43 / 43 | 29 / 43 | current 24, Claude 8, tie 11 |

Conclusion:

- Removing instructions hurt every tested model by 13-18 hard-gate cases.
- GLM-5.2 was the strongest non-GPT transfer result, but still lagged GPT-5.5
  on hard gates and quality.
- The Claude/Fable reference was competitive on some pass/pass wording,
  but missed many deterministic safety/process gates.

Caveats:

- External adapter runs were model-only structured-output runs, not full Codex
  shell/MCP/file-edit agent loops.
- Some external-model runs required targeted rerun merges after transient
  transport failures.

## 2026-07-03 - Split-Bundle OpenHands Reference Snapshot

Instruction surface:

- Historical split bundle before the single-bundle merge.
- OpenHands reference pinned from the public repository in
  `evals/reference-instructions.json`.

Metric snapshot:

| Comparison | Artifact | Current | OpenHands | Quality |
|---|---|---:|---:|---|
| Current vs OpenHands reference | `.eval-results/compare-openhands-quality-calibration-final-v3` | 43 / 43 | 30 / 43 | current 28, OpenHands 7, tie 8 |

Conclusion:

- The main advantage was deterministic safety/process coverage.
- Pass/pass quality was close, which motivated the later calibration pass and
  anti-overfit audit instead of simply adding more instruction text.

Caveats:

- This snapshot used the old split instruction bundle and older deterministic
  checks, so compare trends against later snapshots rather than treating the
  raw OpenHands pass count as directly interchangeable.

## 2026-07-02 - v4.7 Wrapper-Ban Eval Coverage

Instruction surface:

- Added the banned/broken/superseded tool-wrapper rule and the
  `available-tool-no-ban` negative case.
- Kept the rule narrow: do not disable ordinary read-only tools unless there is
  actual ban, failure, or replacement evidence.

Metric snapshot:

| Check | Result |
|---|---:|
| Static validation | `cases=26 markdown_tables=2 presets=12 references=1` |

Conclusion:

- This was a scoped coverage update rather than a full benchmark snapshot.
- The important metric was harness validity and the presence of a negative case
  proving normal tools remain usable.

Caveats:

- No comparable 43-case model-backed snapshot exists for this version in the
  current docs.
