# zafo-injector

Isolated-vault CLI for injecting AI-generated scene prose into Markdown story frames via OpenRouter, with deterministic structural QA and optional multilingual heuristics.

## Purpose

`zafo-injector` fills a single marked scene slot inside an existing episode or post frame without modifying source files, while keeping API credentials, private creative guidance, and generated drafts strictly inside an external `C:` vault.

It is built around two authoring goals:

1. **Explicit/mature scenes, immersive prose, and character interactions** (primary model: `anthracite-org/magnum-v4-72b`).
2. **Emotional interactions, character consistency, and roleplay** (single-model drafting or side-by-side comparison across `anthracite-org/magnum-v4-72b`, `sao10k/l3.1-euryale-70b`, and `deepseek/deepseek-chat-v3-0324`).

**Active workflow:** Draft in English (`language = "en"` in `settings.toml`) through [writing-injector.ps1](./writing-injector.ps1), then edit or manually translate into Slovak in VS Code. Existing `--language sk|en` support (with `sk` as the bare-CLI fallback when unconfigured) remains intact for backward compatibility and optional multilingual contributors.

For architecture contracts, full schemas, CI gates, and historical validation records, see [docs/project_sheet .md](<./docs/project_sheet .md>).

---

## Short Manual

### 1. Setup

Requires Windows 11, PowerShell 7 (`pwsh`), and Python 3.12+:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\writing-injector.ps1
```

Both `.\.venv\Scripts\python.exe -m zafo_injector` and `.\.venv\Scripts\zafo-inject.exe` expose the same CLI; [writing-injector.ps1](./writing-injector.ps1) wraps `.venv\Scripts\zafo-inject.exe` with safe-by-default preview protection.

### 2. Isolated Vault & Settings

**Storage and privacy boundaries:**
- **Drive `D:\` and the repository workspace are forbidden** for vaults and generated outputs (including through symlinks or junctions).
- Place your vault on a genuinely unsynchronized local `C:` directory outside Google Drive / cloud folders.
- **Storage isolation is not a network air gap:** a human `-Generate` run sends the style anchors, slot instructions, 2-paragraph before/after context, and any `TIER4_ADDON.txt` to OpenRouter over HTTPS.
- Coding assistants must never inspect real vaults or execute live generation (see [AGENTS.md](./AGENTS.md)).

**Recommended external layout (example under `%LOCALAPPDATA%\WritingInjector`):**

```text
%LOCALAPPDATA%\WritingInjector\
    settings.toml          # Non-secret CLI defaults (outside the vault)
    vault\
        .env               # OPENROUTER_API_KEY=...
        TIER4_ADDON.txt    # Optional private scene/style guidance (English for language = "en")
        output\            # Generated .candidates.md, .merged.md, or .arena.* files
```

*(For Slovak lexicon-based vault bootstrap, `.\scripts\init_local_vault.ps1` is also available; for English-only use, create `vault\.env`, `vault\output`, and an optional English `vault\TIER4_ADDON.txt` directly.)*

**Example `settings.toml`:**

```toml
language = "en"
candidates = 1
model = "anthracite-org/magnum-v4-72b"
style_sheet = 'C:\path\to\STYLE_SHEET_EN.md'
vault_dir = 'vault'
```

- `--config FILE` is always explicit (no automatic settings discovery).
- Precedence: `CLI flag > settings.toml > legacy fallback` (`vault_dir` uses `--vault-dir > ZAFO_VAULT_DIR > settings.toml > ~/zafo-local`; `OPENROUTER_API_KEY` prefers nonempty process env over `vault\.env`).
- Relative paths inside `settings.toml` resolve from the directory containing `settings.toml` (`~` expands; `%VAR%` / `$VAR` do not).
- Allowed TOML keys: `language`, `candidates`, `model` *or* `models` (mutually exclusive), `temp` (`0..2`), `min_p` (`0..1`), `track`, `tracks_root`, `style_sheet`, `lexicon`, `vault_dir`.

### 3. Story Frame & Style Sheet Format

1. **POV comment before the slot:** include one HTML comment declaring `POV: Male` or `POV: Female`, e.g. `<!-- POV: Male -->`.
2. **Single insertion slot comment:**
   ```markdown
   <!-- [TIER 4 INSERT SLOT: 140-220 words] Describe the scene beat, emotional shift, and staging... -->
   ```
   Use `words` when `language = "en"` (`slov` when `language = "sk"`), or omit `: MIN-MAX ...` to use the `140-220` default.
3. **Context window (`2` before / `2` after):** the parser sends **only up to two prose paragraphs before and two after the slot**—not the full chapter. Put any character traits, relationship dynamics, or physical staging not visible in those four neighboring paragraphs into the slot instructions, style sheet, or `TIER4_ADDON.txt`.
4. **Style sheet sections:** must include numbered ATX headings `1.` (Pinned Sample) and `6.` (Slot Rules), e.g. `## 1. Pinned Sample` and `## 6. Slot-Injector Prompt`.
5. **Optional multi-track layout (`--track blog|serial|dark-romance` + `--tracks-root ROOT`):** expects `ROOT\<track>\docs\STYLE_SHEET_EN.md` for English (`STYLE_SHEET.md` + `ROOT\docs\SLOVAK_LEXICON.md` for Slovak), unless overridden via `--style-sheet` / `--lexicon`.

### 4. Daily Commands (`writing-injector.ps1`)

[writing-injector.ps1](./writing-injector.ps1) requires a PowerShell string array (`-CliArgs @(...)`). Without `-Generate`, it **automatically prepends `--dry-run`** so accidental live API calls cannot happen.

```powershell
$appHome = Join-Path $env:LOCALAPPDATA 'WritingInjector'
$cfg = Join-Path $appHome 'settings.toml'

# 1. Free offline preview (validates frame, POV, bounds, style, and vault path; no API or writes)
.\writing-injector.ps1 -CliArgs @(
    'C:\stories\episode_01.md',
    '--config', $cfg
)

# 2. Generate English draft (writes <stem>.candidates.md and <stem>.merged.md to vault\output)
.\writing-injector.ps1 -Generate -CliArgs @(
    'C:\stories\episode_01.md',
    '--config', $cfg
)

# 3. Side-by-side model comparison (report-only: writes <stem>.arena.md and <stem>.arena.json)
.\writing-injector.ps1 -Generate -CliArgs @(
    'C:\stories\episode_01.md',
    '--config', $cfg,
    '--models', 'anthracite-org/magnum-v4-72b,sao10k/l3.1-euryale-70b',
    '--candidates', '2'
)

# 4. Offline lint check on a standalone passage (no API call, no vault access)
.\writing-injector.ps1 -CliArgs @(
    'C:\stories\episode_01.md',
    '--config', $cfg,
    '--lint-only', 'C:\drafts\passage.txt'
)
```

**No-overwrite rule:** Existing `<stem>.candidates.md`, `<stem>.merged.md`, or `<stem>.arena.*` files in `vault\output` are **never overwritten**. Move or rename previous outputs inside `vault\output` before running `-Generate` again for the same frame stem (conflict checks happen after API generation).

### 5. Flags, QA & Exit Codes

| Flag | Purpose |
|---|---|
| `--config FILE` | Load flat UTF-8 `.toml` non-secret defaults |
| `--language sk\|en` | Explicit output language (`sk` bare-CLI fallback if unconfigured) |
| `--model ID` | Single-model OpenRouter ID (mutually exclusive with `--models`) |
| `--models m1,m2[,m3]` | Compare 2–3 registered models (`anthracite-org/magnum-v4-72b`, `sao10k/l3.1-euryale-70b`, `deepseek/deepseek-chat-v3-0324`; max 9 total requests) |
| `--candidates N` | Candidates per model (default `3`; `1` recommended for single-draft Magnum runs) |
| `--temp` / `--min-p` | Sampling overrides (`0..2` and `0..1`; `--min-p` rejected if a matrix model lacks support) |
| `--style-sheet` / `--lexicon` | Explicit style/lexicon paths (`--lexicon` is rejected in English mode) |
| `--track` + `--tracks-root` | Paired track (`blog`, `serial`, `dark-romance`) and root directory |
| `--vault-dir DIR` | Override vault directory on `C:` |
| `--dry-run` / `--lint-only FILE` | Offline validation or standalone passage lint |
| `--strict` | Fail with exit `5` (and write no single-model drafts) if hard QA rules fail |
| `--print-output` | Print generated candidate prose to stdout after output files are published |

**QA behavior:**
- Score formula: `100 - 25 * errors - 5 * warnings`.
- Shared structural rules check inclusive slot word bounds, `2–4` nonempty paragraphs, boundary echoes, and warn above `4` sentences in one paragraph.
- **English QA is structural only** (no grammar, language, or POV classifier). Leave `--strict` **off** (default diagnostic mode) during creative runs so slightly over-length candidates are still saved to `vault\output` for human review.

| Exit | Meaning |
|---:|---|
| `0` | Completed (including non-strict diagnostic runs with QA findings) |
| `2` | Invalid arguments, configuration, frame/style format, or existing output file conflict |
| `3` | Storage/air-gap boundary violation (`D:\`, workspace, or cloud marker) |
| `4` | OpenRouter transport or API failure |
| `5` | `--strict` hard QA failure |

### 6. Developer Checks

Run offline tests and static checks using isolated `C:` temporary storage (real HTTP is blocked in tests):

```powershell
$safeTests = Join-Path $env:LOCALAPPDATA ('Temp\zafo-tests-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $safeTests -ErrorAction Stop | Out-Null
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:TEMP = $safeTests; $env:TMP = $safeTests
$env:MYPY_CACHE_DIR = Join-Path $safeTests 'mypy-cache'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp (Join-Path $safeTests 'pytest')
.\.venv\Scripts\ruff.exe check --no-cache src tests
.\.venv\Scripts\ruff.exe format --check --no-cache src tests
.\.venv\Scripts\mypy.exe --strict src
```
