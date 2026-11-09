# zafo-injector

Python 3.12+ / PowerShell 7 CLI for Slovak and English prose slot parsing,
deterministic QA, and optional OpenRouter candidate generation. Phase 1 uses
explicit language selection: Slovak is the backward-compatible default.
Phase 2A adds an opt-in, report-only multi-model comparison arena.
Automated validation uses benign synthetic fixtures and mocked HTTP; it does
not establish live English quality or production readiness.

## Setup

From the project directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m zafo_injector --help
```

The package is `src\zafo_injector`, not `src\tools`. Both
`python -m zafo_injector` and the installed `zafo-inject` entry point are supported.

## Storage and privacy

- **The whole D: drive is forbidden** for the vault and generated files, including
  paths resolved through junctions/symlinks. The workspace is also forbidden.
- The default vault is `Join-Path $HOME 'zafo-local'`; override with
  `ZAFO_VAULT_DIR` or `--vault-dir`. CLI flags take precedence.
- Known Google Drive directory names, `GOOGLE_DRIVE_DIR`, and `.gdoc` /
  `.code-workspace` markers in existing ancestors are rejected. This is not
  exhaustive discovery of custom-named cloud mounts: set `GOOGLE_DRIVE_DIR` for
  those, and choose a genuinely unsynchronized vault.
- This is **storage isolation, not a network air gap**. A human live run sends
  style anchors, the local addon, slot instructions, and sliced frame context to
  OpenRouter over HTTPS. Proxy environment variables and redirects are disabled
  for the production HTTP client. Provider quantization fallback is restricted
  to the requested `bf16`, `fp16`, and `fp8` list.
- Agents must not inspect the real vault or run live generation. Tests use
  temporary synthetic vaults only. See [AGENTS.md](AGENTS.md).
- The vault is not encrypted. Protect it using OS permissions. Path checks assume
  a trusted local account; they are not a sandbox against concurrent hostile
  filesystem changes by another process with the same permissions.

### Bootstrap (human operation)

```powershell
.\scripts\init_local_vault.ps1
```

The script creates `.env`, `TIER4_ADDON.txt`, and `output`. It extracts the first
fenced block from lexicon section 6. Existing `.env` and filled addon files are
preserved; an empty addon is populated. `-Force` explicitly resets both files,
including the API key placeholder. `-VaultDir` and `-LexiconPath` override defaults.
Relative paths resolve from PowerShell's current filesystem location, including
after `Set-Location`; they do not depend on the process working directory.
Bootstrap returns exit code 0 on success and 2 on failure, including repeated
invocations in the same PowerShell session.
Invalid source formats fail before any vault files are created.
Section headings inside fenced Markdown examples are ignored when locating
the addon skeleton.

Set `OPENROUTER_API_KEY` manually in the vault `.env` or process environment.
Process environment takes precedence; loading `.env` does not mutate it.
The loader supports comments, `export KEY=value`, and single/double-quoted values,
without interpolation. Errors and configuration representations do not echo keys.

## Commands

```powershell
# Safe metadata/structure check: no API, no writes, no addon or .env reads.
.\.venv\Scripts\python.exe -m zafo_injector ..\zafo-shorts\blog\posts\post_002.md --dry-run

# Local lint only: no API, vault access, or output writes.
.\.venv\Scripts\python.exe -m zafo_injector ..\zafo-shorts\blog\posts\post_002.md --lint-only C:\drafts\candidate.txt --strict

# Synthetic English checks: explicit language, no Slovak lexicon.
# Choose an unsynchronized C: vault outside the workspace, never on D:.
$syntheticVault = Join-Path $env:LOCALAPPDATA 'zafo-english-synthetic-vault'
.\.venv\Scripts\python.exe -m zafo_injector .\tests\fixtures\frame_en.md --language en --style-sheet .\tests\fixtures\STYLE_SHEET_EN.md --vault-dir $syntheticVault --dry-run
.\.venv\Scripts\zafo-inject.exe .\tests\fixtures\frame_en.md --language en --lint-only .\tests\fixtures\candidate_en.txt --strict
```

Only a human should invoke generation without `--dry-run` or `--lint-only`.
Default generation requests 3 candidates with up to 3 concurrent requests,
45-second request timeouts, and at most 2 exponential-backoff retries for
HTTP 429/5xx. Total run time can exceed 45 seconds. Latency and cost depend on
the provider and are not guaranteed.

`--language sk|en` selects the output language; omission means `sk`. Language
is never auto-detected from prose, headers, filenames, or style sheets.
Both entrypoints support the same flags and behavior.

Other flags: `--candidates`, `--model`, `--models`, `--temp`, `--min-p`, `--vault-dir`,
`--style-sheet`, `--lexicon`, `--strict`, and `--print-output`.
Style paths default to the frame's neighboring `blog\docs\STYLE_SHEET.md`
(`post_path.parent.parent / "docs"`). Slovak mode also defaults to its neighboring
`SLOVAK_LEXICON.md`. English mode neither requires nor reads that lexicon.
An explicitly supplied `--lexicon` with `--language en` is rejected with exit 2
before file or vault access; it is not silently ignored or treated as an English
dictionary. Slovak `--lexicon` behavior is unchanged.

The existing bootstrapper remains Slovak-lexicon based. For an English-only
synthetic trial, a human can instead create `.env`, `output`, and optionally a
benign `TIER4_ADDON.txt` directly in an explicit, isolated synthetic vault.
Configure its credential privately; no Slovak lexicon is needed by the English
CLI. Do not use the private default vault for acceptance experiments.

Dry-run prints only redacted structure, POV, counts, and readiness; it does not
print frame excerpts or a local addon. Lint-only and generation diagnostics print
rule IDs and line numbers, not matched text or suggestions. Generation findings
identify the candidate, including before a strict failure exits without drafts.
Terminal messages are UTF-8, plain text, and never ANSI colored, including when
`NO_COLOR` is set.

### Output and failure policy

Without `--models`, the existing Phase 1 policy is unchanged:

- Writes only `<stem>.candidates.md` and `<stem>.merged.md` in the validated
  vault's `output` directory. Every candidate has a lint table and counts.
- Candidates sort by score descending, with original request index breaking ties.
  The highest score is merged. Sources, BOMs, and newlines outside the slot are
  preserved; candidate prose replaces exactly the slot comment.
- Existing drafts are **never overwritten**. Move them before running again.
  Files are staged and atomically published without replacement; a failed second
  publication rolls back the first. There is no crash-atomic two-file transaction.
  Conflict checks happen during rendering, so a repeated live request can still
  incur charges before an existing draft prevents publication.
- Any remote candidate failure fails the batch: no partial-success drafts.
  Errors show actionable, redacted messages without API response bodies.
- Lint failures are review findings, not fatal by default. `--strict` returns 5
  and writes nothing if **all** candidates fail hard rules. A failed top-ranked
  draft is explicitly warned about. Lint-only uses 5 for a strict hard-rule failure.
- Candidate summaries include score, word count, target bounds, and paragraph
  count. Findings use `[FAIL]` for errors and `[WARN]` for warnings; matched text
  and suggestions remain in the local candidate report.
- Generated prose is not printed unless `--print-output` is explicitly supplied.

| Exit | Meaning |
|---|---|
| 0 | Completed, or non-strict lint completed |
| 2 | Arguments, configuration, source format, or local file/output failure |
| 3 | Storage boundary violation |
| 4 | OpenRouter failure |
| 5 | Strict lint failure |

## Phase 2A: Multi-Model Comparison Arena

The following policies were approved on 2026-11-07 and implemented with offline,
synthetic validation. Matrix mode compares the same parsed frame, style, selected
language, assembled messages, and bounds. It never selects a winner or produces
a merged draft. Phase 2B tracks/path detection, `CLEAN_TAIL_CHECK`, translation
workflows, and Phase 3 UI are not implemented by this phase.

### Static model profiles and argument policy

Public catalog and per-model endpoint metadata were checked on 2026-11-07,
without credentials or inference. All three IDs below had listed fp8 endpoints
with status 0; that snapshot is not a guarantee of future availability or billing.

| Full registered model ID | Matrix sampling support | Catalog input/output USD per million tokens |
|---|---|---|
| `anthracite-org/magnum-v4-72b` | temperature, top_p, min_p, repetition_penalty | 2.50 / 5.00 |
| `deepseek/deepseek-chat-v3-0324` | temperature, top_p | 0.29 / 1.14 |
| `sao10k/l3.1-euryale-70b` | temperature, top_p, min_p, repetition_penalty | 0.85 / 0.85 |

The status-0 DeepSeek endpoint advertised 0.25 / 1.00, differing from the catalog
aggregate. Sources: [public catalog](https://openrouter.ai/api/v1/models),
[Magnum endpoints](https://openrouter.ai/api/v1/models/anthracite-org/magnum-v4-72b/endpoints),
[DeepSeek endpoints](https://openrouter.ai/api/v1/models/deepseek/deepseek-chat-v3-0324/endpoints),
and [Euryale endpoints](https://openrouter.ai/api/v1/models/sao10k/l3.1-euryale-70b/endpoints).
The old planning ID `sao10k/l3.3-euryale-70b` was absent from the catalog and had
zero endpoints. Its replacement with the listed **3.1** ID was explicitly approved;
the CLI never silently substitutes a model.

- `--models m1,m2,...` requires **2-3 exact, case-sensitive registered full IDs**.
  Surrounding whitespace is trimmed; empty, duplicate, unknown, short, and retired
  IDs are rejected. The registry is static: neither offline modes nor tests depend
  on catalog lookup. A human must recheck public metadata before a future live run.
- `--model` and `--models` are mutually exclusive, even if the explicit `--model`
  equals the legacy default. Without `--models`, single-model IDs and payload
  behavior remain unchanged; profiles are not applied to legacy `--model` runs.
- All profiles default to temperature 0.68 and top_p 0.90. Magnum/Euryale also send
  min_p 0.06 and repetition_penalty 1.05; DeepSeek omits these unsupported fields.
  Explicit `--temp` overrides every profile. Explicit `--min-p` overrides every
  profile only if **all** selected models support it; otherwise the command rejects
  before source/vault access, even for `--min-p 0.06`.
- Matrix requests retain allowed quantizations `bf16`, `fp16`, `fp8` and
  `allow_fallbacks=true`, with matrix-only `require_parameters=true`. Provider
  fallback must support the requested parameters and allowed quantizations; it
  does not substitute another model. Profiles/settings and omissions are reported,
  so differing sampling is not mislabeled a controlled model-only experiment.
- `--candidates N` is the common per-model count, default 3. Matrix mode permits
  **at most 9 initial requests** and **at most 27 HTTP attempts** per invocation.
  Two models allow N=1-4; three allow N=1-3. There is one shared executor with a
  maximum of three in-flight requests, 45-second request timeouts, and at most two
  retries for 429/5xx with existing 0.5/1.0-second backoff. Transport/shape failures
  are not retried. No new single-model candidate limit was introduced.
- `--models --dry-run` validates profiles/overrides/budgets and prints redacted
  readiness and effective settings without credentials/addon reads, requests, or
  writes. `--models --lint-only` is rejected: linting one file is not a model
  comparison. Language selection and English lexicon rejection remain unchanged.

Safe synthetic previews through both entrypoints:

```powershell
# Choose a genuinely unsynchronized C: location outside the workspace.
# Preview validates it and creates no vault or output files.
$syntheticVault = Join-Path $env:LOCALAPPDATA ("Temp\zafo-arena-preview-" + [guid]::NewGuid().ToString('N'))
$arenaModels = 'anthracite-org/magnum-v4-72b,deepseek/deepseek-chat-v3-0324,sao10k/l3.1-euryale-70b'
.\.venv\Scripts\python.exe -m zafo_injector .\tests\fixtures\frame_en.md --language en --style-sheet .\tests\fixtures\STYLE_SHEET_EN.md --vault-dir $syntheticVault --models $arenaModels --dry-run
.\.venv\Scripts\zafo-inject.exe .\tests\fixtures\frame.md --style-sheet .\tests\fixtures\STYLE_SHEET.md --lexicon .\tests\fixtures\SLOVAK_LEXICON.md --vault-dir $syntheticVault --models $arenaModels --dry-run
```

Only a separately authorized human may remove `--dry-run` for live generation.
Storage isolation is not a network air gap: assembled prompts are transmitted to
OpenRouter and requests/retries may incur charges.

### Arena reports, schema, and failure policy

Matrix mode writes exactly `<stem>.arena.md` and `<stem>.arena.json` in the
validated vault's `output` directory. Markdown contains per-model scorecards,
candidate prose, and local lint tables. JSON is metadata-only, with no candidate
prose, assembled prompts, addons, keys, matched text/suggestions, or API bodies.
Candidate identities are `<full-model-id>::candidate-<1-based-index>`.
JSON preserves requested model order and candidate index order; Markdown ranks
successful candidates **within each model** by the existing score/index rule,
then includes explicit failed requests. There is no cross-model winner.

JSON schema version 1:

- Root: `schema_version`, `mode="arena"`, `status`, `exit_code`, `strict`,
  `language`, `pov`, inclusive `bounds`, `qa`, `execution`, and `models`.
- `qa`: unchanged score formula and explicit limitations. Scores are deterministic
  structure plus Slovak-only configured heuristics, **not** grammar, prose-quality,
  output-language, scene-compliance, or safety certification.
- `execution`: per-model count, initial requests/limit, actual HTTP attempts,
  attempt budget, concurrency cap, timeout, max retries, and retry backoff.
- Each model: exact ID, status (`hard_pass`, `lint_findings`, `lint_failed`, or
  `api_failed`), effective `sampling`, `omitted_sampling_parameters`, `provider`,
  `scorecard`, and `candidates`.
- Scorecard: `requested`, `succeeded`, `api_failed`, `hard_pass_count`,
  `hard_pass_rate_requested`, `hard_error_count`, and `warning_count`.
  Pass-rate denominators include **all requested candidates**, including failures.
- Each candidate: stable ID, index, status, attempts, score, word/paragraph counts,
  hard-pass flag, hard-error/warning counts, redacted rule/severity/line `issues`,
  and `failure`. API failures have **null QA metrics/issues**, not fake zero scores;
  `failure` contains only a safe code, optional HTTP status, and redacted message.

Every planned request remains represented, including partial or complete API
failure. Report status and process exit are explicit:

| Matrix condition | Report status | Exit | Reports |
|---|---|---|---|
| Any API failure, with or without `--strict` | `api_failed` | 4 | Both explicitly failed reports |
| No API failure, `--strict`, any model has zero hard-passing candidates | `strict_lint_failed` | 5 | Both explicitly strict-failed reports |
| Otherwise, including non-strict hard lint findings | `completed` | 0 | Both review reports; findings remain explicit |
| Local/config/publication failure | No completed publication | 2 | No partial pair from this invocation |
| Storage boundary violation | No completed publication | 3 | No partial pair from this invocation |

Exit 0 means the comparison completed, not that all candidates were accepted.
Warnings alone do not fail strict mode. File/storage publication failures take
precedence over the planned matrix exit. Phase 1's no-draft API/strict failure
policy remains unchanged outside matrix mode.

Both report files reuse the existing containment rechecks, exclusive atomic
publication, no-overwrite policy, staging cleanup, and rollback if the second
publication fails. This is not a crash-atomic two-file transaction. Conflicts are
checked during rendering, after requests; repeated human live runs can incur
charges before an existing report blocks publication. Input sources, including
BOM/CRLF bytes, are never modified. Failed reports must also be archived or moved
inside the vault's output directory before reusing the same filenames.
Candidate prose prints only with explicit `--print-output`, **after both reports
publish**; matrix mode then prints all successful candidates with identities,
even in an explicitly failed comparison, never a selected winner.

## Source contracts and QA limits

The included [fixtures](tests/fixtures) demonstrate the currently supported format:

- One metadata HTML comment before the slot containing `POV: Male` or
  `POV: Female`. Slovak frames conventionally use `POV: Male (-l som)` or
  `POV: Female (-la som)`; English frames need no Slovak endings.
  Duplicate POV fields, even in one comment, fail.
- Exactly one `<!-- [TIER ... INSERT SLOT: 140–220 slov] ... -->` comment in
  Slovak mode, or e.g. `<!-- [TIER 1 INSERT SLOT: 20-80 words] ... -->` in English.
  Hyphens and en dashes work; omitted bounds default to 140–220.
  Explicit bounds must use `: MIN-MAX slov` for `sk` or `: MIN-MAX words` for
  `en`, without trailing text. A unit from the other language is rejected;
  it does not change the selected language.
  Malformed/reversed bounds and missing/duplicate slots fail explicitly.
- Up to two blank-line-separated prose paragraphs on each side, excluding HTML
  comments, ATX headings, and the leading UTF-8 BOM.
- Style sheet sections numbered 1 and 6 for both languages; Slovak lexicon
  sections numbered 3 and 4 only in Slovak mode.
  ATX headings such as `## 1. Title`, `## 1\. Title`, and `## §1 Title`
  are supported. Subsections and headings inside fenced examples are preserved.
- Each lexicon section contains a Markdown table with a header, banned literal
  token/phrase in the first column, and Slovak replacement in the second.
  Terms match case-insensitively at word boundaries; whitespace in phrases is
  flexible. Additional columns are ignored. Regexes and implicit inflection
  expansion are not supported.
- The fixed clinical/Harlequin denylist comes from the terms enumerated in the
  project specification, not automatic extraction from style section 4.

Prompts end with an authoritative output contract: the selected language only
(including dialogue), the frame's narrator POV, inclusive slot word bounds,
2-4 nonempty paragraphs, and prose-only output. Slovak retains its spelling,
vocabulary, Czech-form avoidance, and grammatical-gender guidance. English uses
English spelling, vocabulary, grammar, and first-person POV guidance without
Slovak grammatical endings. The word-count target is the integer midpoint of
the slot bounds. These requirements override conflicting guidance in style
examples, templates, scene instructions, or the addon, while the supplied style
sheet still controls writing register. Stronger wording does not guarantee
model compliance; lint and human review remain necessary.

Both languages share letter-based word counting (hyphenated and apostrophe-linked
words count as one), 2–4 nonempty paragraphs, warnings above 4 punctuation-delimited
sentences per paragraph, exact boundary-echo checks, scoring, and ranking.
Only Slovak applies `CZECHISM`, `CALQUE`, `CLINICAL_OR_HARLEQUIN`, and
`POV_DRIFT` rules. Slovak `„...“` dialogue is excluded from gender checks.
Blank-line paragraph boundaries support LF/CRLF and trailing spaces or tabs.
These are deterministic heuristics, not a full Slovak morphological analyzer.
Czechism detection covers configured literal terms and phrases only; unlisted
Czech vocabulary or grammatical forms can escape detection. Passing lint does
not certify natural Slovak.
Score is exactly `100 - 25 * errors - 5 * warnings` (not clamped).

**English QA is intentionally structural, not a grammar checker.** It does not
detect output language, spelling/grammar errors, narrator-gender/POV drift, scene
noncompliance, or unnatural English. Passing English lint certifies none of those;
human language-quality and scene-compliance review is required.

Frozen dataclasses use tuples for context and issues, and `FrameDocument` retains
the original source text for lossless splicing. `CandidateResult` holds the
1-based request index, text, and lint report. `FrameDocument.language` defaults to
`"sk"` and is appended to its existing fields. `parse_frame` retains the positional
context-window argument and adds keyword-only `language="sk"`. Existing Slovak
`lint_candidate(text, doc, rules)` calls remain supported; English uses
`lint_candidate(text, doc)` or an explicit `None`. Library calls also reject
Slovak lexicon rules on an English document rather than silently ignoring them.

## Validation

```powershell
# Fresh local C: test storage, outside D:, the workspace, and cloud locations.
$safeTests = Join-Path $env:LOCALAPPDATA ("Temp\zafo-tests-" + [guid]::NewGuid().ToString('N'))
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:MYPY_CACHE_DIR = Join-Path $safeTests 'mypy-cache'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp (Join-Path $safeTests 'pytest')
.\.venv\Scripts\ruff.exe check --no-cache src tests
.\.venv\Scripts\ruff.exe format --check --no-cache src tests
.\.venv\Scripts\mypy.exe src
```

Tests block real HTTP transports. BDD features cover vault rejection, parsing,
Slovak ranking, and end-to-end mocked injection. PowerShell bootstrap and Windows
junction tests use only temporary synthetic locations, never the real vault.
Both installed CLI entrypoints are exercised as subprocesses in dry-run and
lint-only modes with default Slovak, explicit Slovak, and explicit English,
including failure exit codes and unchanged BOM/CRLF sources. English tests cover
exact bounds, prompts, structural QA, lexicon independence/rejection, redaction,
ranking, output containment, no overwrites, and publication cleanup. Generation
remains in-process with mocked HTTP; no automated test validates live provider
behavior, response quality, latency, or cost.
Phase 2A adds synthetic unit/BDD coverage for static profiles, exact budgets and
overrides, report schema, both-language/entrypoint offline combinations, shared
concurrency, attempts/retries, explicit API/strict failures, report-only behavior,
redaction, hashes/immutable contracts, no overwrites, containment, rollback, and
cleanup. Existing single-model regressions remain covered. See the
[project sheet](<docs/project_sheet .md>) for the approval and validation record.

Fresh manual offline gate on 2026-11-07: the clean Phase 1 baseline passed 290
tests; the completed Phase 2A suite passed **519 tests**, Ruff lint/format passed
(30 Python files), and strict mypy passed (12 source files). These are local
synthetic/mocked checks, not hosted CI, live model acceptance, or production
readiness evidence.

### Human acceptance

The synthetic [style fixture](tests/fixtures/STYLE_SHEET.md) requests natural,
standard written Slovak without colloquialisms for acceptance experiments.
This is a test-only choice; other style sheets retain control of their register.
Separate benign English [frame](tests/fixtures/frame_en.md),
[style](tests/fixtures/STYLE_SHEET_EN.md), and
[candidate](tests/fixtures/candidate_en.txt) fixtures use natural, standard
written English, with a 20-80-word slot and a 50-word, two-paragraph candidate.

- **Offline:** choose an unsynchronized location outside D: and the workspace;
  bootstrap a disposable synthetic vault with explicit paths, check idempotence
  and `-Force`, then exercise both CLI entrypoints with `--dry-run` and
  `--lint-only`. Review strict exit codes, redacted output, and unchanged sources.
- **Optional live test (human only):** use synthetic Tier-1 inputs and an explicit
  disposable vault. Configure credentials privately and acknowledge that frame
  context, style anchors, instructions, and any addon are sent to OpenRouter.
  Capture the source hash immediately before each run in the same PowerShell
  session and compare afterward; a missing or stale baseline cannot establish
  whether the source changed. Archive existing drafts inside the synthetic
  vault's output directory before another request.
  Check provider/model availability, successful generation, lint review, output
  containment, no-overwrite behavior, and billing. Do not infer production
  readiness from offline or mocked results.
- **Live English acceptance (human only):** use the separate synthetic English
  frame/style with explicit `--language en` and `--vault-dir`, never the private
  default vault or real story prose. First verify dry-run and strict lint-only
  locally without `--lexicon`. Keep the API credential private in that synthetic
  vault's `.env` or process environment; do not paste or print it. Immediately
  before generation, capture fresh hashes of the frame, style, and any addon in
  the same PowerShell session. Archive existing drafts **inside that vault's
  output directory** before another request. A live request sends the assembled
  prompt to OpenRouter and may incur charges, including before an output conflict.
  Afterward compare source hashes, verify output containment and no overwrites,
  inspect lint findings, and review natural English, narrator POV, bounds,
  paragraphs, style register, continuity, and scene compliance manually.
  Human Slovak connectivity trials and mocked English passes are not proof of
  production readiness.

### Phase 2A human-only benchmark: smoke observed, formal runs pending

A human-executed English smoke on 2026-11-09 returned three successful responses
without retries or API failures. Magnum (87 words) and Euryale L3.1 (86) exceeded
the unchanged 20-80-word maximum; DeepSeek (75) passed structural QA. The run
correctly exited 5 with `strict_lint_failed` reports. Billed smoke cost was
USD 0.001980, with settlement human-confirmed.

The human preferred Magnum's prose and prioritizes fiction quality over minor
word-target deviations for model selection. Structural scores are not literary
rankings; this preference does not rewrite the recorded strict result. See the
[project sheet](<docs/project_sheet .md>) for the dated outcome, evidence limits,
and distinction between tested Euryale L3.1 and the desired, untested L3.3 target.
The formal English/Slovak benchmark below remains unexecuted; no further paid
stage is released by this record.

- Separately approve prompt transmission and a spending budget before any paid
  run. Request caps do **not** enforce a dollar cap; advertised prices, response
  token counts, provider availability, latency, and actual billing need human
  verification.
- Use the three approved models, three candidates each, once per language with
  existing benign Tier-1 frame/style fixtures and unchanged bounds. That means
  18 initial requests total and at most 54 HTTP attempts across two invocations.
  Within each language compare identical frame/style/addon/messages/bounds and
  record the effective sampling differences. Use explicit fresh unsynchronized
  synthetic C: vaults, never the real default vault or upstream story prose.
- Capture fresh source/style/addon hashes before and after, verify containment
  and no overwrites, and record costs, latency, attempts, and failures locally
  inside each synthetic vault's output directory.
- Small-benchmark acceptance requires no API failures and **every raw candidate**
  within inclusive word bounds and 2-4 paragraphs with all hard rules passing.
  Review warnings and independently review every candidate for language, grammar,
  naturalness, narrator POV, style, scene compliance, and continuity.
- Do not truncate, relax bounds, edit outputs into acceptance, or substitute a
  fixture/mock control for raw-generation evidence. Historical English raw
  outputs of 99 and 90 words failed 20-80 bounds; the 50-word passing fixture was
  only a control. The later 75-word DeepSeek smoke is a raw structural pass,
  not completion of the formal all-candidate benchmark or human quality review.
- Passing this small synthetic benchmark would still not certify production
  readiness, sustained provider performance, or real upstream compatibility.
