# zafo-injector

Python 3.12+ / PowerShell 7 CLI for Slovak prose slot parsing, deterministic QA,
and optional OpenRouter candidate generation. Phase 1 is implemented and tested
with benign synthetic fixtures and mocked HTTP; real upstream Markdown and live
provider behavior have not been verified.

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
```

Only a human should invoke generation without `--dry-run` or `--lint-only`.
Default generation requests 3 candidates with up to 3 concurrent requests,
45-second request timeouts, and at most 2 exponential-backoff retries for
HTTP 429/5xx. Total run time can exceed 45 seconds. Latency and cost depend on
the provider and are not guaranteed.

Other flags: `--candidates`, `--model`, `--temp`, `--min-p`, `--vault-dir`,
`--style-sheet`, `--lexicon`, `--strict`, and `--print-output`.
Style and lexicon paths default to the frame's neighboring `blog\docs` directory
(`post_path.parent.parent / "docs"`).

Dry-run prints only redacted structure, POV, counts, and readiness; it does not
print frame excerpts or a local addon. Lint-only prints rule IDs and line numbers,
not the candidate text. Terminal messages are UTF-8, plain text, and never ANSI
colored, including when `NO_COLOR` is set.

### Output and failure policy

- Writes only `<stem>.candidates.md` and `<stem>.merged.md` in the validated
  vault's `output` directory. Every candidate has a lint table and counts.
- Candidates sort by score descending, with original request index breaking ties.
  The highest score is merged. Sources, BOMs, and newlines outside the slot are
  preserved; candidate prose replaces exactly the slot comment.
- Existing drafts are **never overwritten**. Move them before running again.
  Files are staged and atomically published without replacement; a failed second
  publication rolls back the first. There is no crash-atomic two-file transaction.
- Any remote candidate failure fails the batch: no partial-success drafts.
  Errors show actionable, redacted messages without API response bodies.
- Lint failures are review findings, not fatal by default. `--strict` returns 5
  and writes nothing if **all** candidates fail hard rules. A failed top-ranked
  draft is explicitly warned about. Lint-only uses 5 for a strict hard-rule failure.
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

- One metadata HTML comment before the slot containing `POV: Male (-l som)` or
  `POV: Female (-la som)`. Duplicate POV fields, even in one comment, fail.
- Exactly one `<!-- [TIER ... INSERT SLOT: 140–220 slov] ... -->` comment.
  Hyphens and en dashes work; omitted bounds default to 140–220.
  Explicit bounds must use `: MIN-MAX slov` without trailing text.
  Malformed/reversed bounds and missing/duplicate slots fail explicitly.
- Up to two blank-line-separated prose paragraphs on each side, excluding HTML
  comments, ATX headings, and the leading UTF-8 BOM.
- Style sheet sections numbered 1 and 6; lexicon sections numbered 3 and 4.
  ATX headings such as `## 1. Title`, `## 1\. Title`, and `## §1 Title`
  are supported. Subsections and headings inside fenced examples are preserved.
- Each lexicon section contains a Markdown table with a header, banned literal
  token/phrase in the first column, and Slovak replacement in the second.
  Terms match case-insensitively at word boundaries; whitespace in phrases is
  flexible. Additional columns are ignored. Regexes and implicit inflection
  expansion are not supported.
- The fixed clinical/Harlequin denylist comes from the terms enumerated in the
  project specification, not automatic extraction from style section 4.

The linter counts letter-based words (including hyphenated words), requires
2–4 nonempty paragraphs, warns above 4 punctuation-delimited sentences per
paragraph, checks literal lexicon rules, narrator gender patterns, and exact
boundary echoes. Slovak `„...“` dialogue is excluded from gender checks.
Blank-line paragraph boundaries support LF/CRLF and trailing spaces or tabs.
These are deterministic heuristics, not a full Slovak morphological analyzer.
Score is exactly `100 - 25 * errors - 5 * warnings` (not clamped).

Frozen dataclasses use tuples for context and issues, and `FrameDocument` retains
the original source text for lossless splicing. `CandidateResult` holds the
1-based request index, text, and lint report.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\ruff.exe format --check src tests
.\.venv\Scripts\mypy.exe src
```

Tests block real HTTP transports. BDD features cover vault rejection, parsing,
Slovak ranking, and end-to-end mocked injection. PowerShell bootstrap and Windows
junction tests use only temporary synthetic locations, never the real vault.
Both installed CLI entrypoints are also exercised as subprocesses in dry-run and
lint-only modes, including failure exit codes and unchanged BOM/CRLF sources.
Generation remains in-process with mocked HTTP; no automated test validates live
provider behavior, response quality, latency, or cost.

### Human acceptance

- **Offline:** choose an unsynchronized location outside D: and the workspace;
  bootstrap a disposable synthetic vault with explicit paths, check idempotence
  and `-Force`, then exercise both CLI entrypoints with `--dry-run` and
  `--lint-only`. Review strict exit codes, redacted output, and unchanged sources.
- **Optional live test (human only):** use synthetic Tier-1 inputs and an explicit
  disposable vault. Configure credentials privately and acknowledge that frame
  context, style anchors, instructions, and any addon are sent to OpenRouter.
  Check provider/model availability, successful generation, lint review, output
  containment, no-overwrite behavior, and billing. Do not infer production
  readiness from offline or mocked results.
