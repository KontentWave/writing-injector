# zafo-injector

Python 3.12+ / PowerShell 7 CLI for Slovak and English prose slot parsing,
deterministic QA, and optional OpenRouter candidate generation. Phase 1 uses
explicit language selection: Slovak is the backward-compatible default.
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

Other flags: `--candidates`, `--model`, `--temp`, `--min-p`, `--vault-dir`,
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
