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
