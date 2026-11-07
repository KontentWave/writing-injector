# `project_sheet.md` — `zafo-injector` (Living Technical Specification)

> **Project:** `zafo-injector` — Isolated-Vault OpenRouter Slot Injector & Slovak/English QA **Framework:** Iterative Scrum-XP (`PLAN -> DRAFT -> SPECIFY (.feature) -> EXECUTE (BDD/TDD) -> AUDIT`) **Target Runtime:** Windows 11 \+ PowerShell 7 \+ Python 3.12+ (zero heavy ML dependencies) **Primary Model Target:** `anthracite-org/magnum-v4-72b` via OpenRouter Chat Completions API

---

## 1\. Current State ("As-Built" Present)

- **Version:** `0.1.0` (Phase 1 and report-only Phase 2A implemented and offline-validated; human-run Phase 1 synthetic API connectivity observed, but raw English generation acceptance remains unpassed).
- **Implemented Modules:** Bootstrapper, frozen models, configuration/storage checks, static model-profile registry, language-aware parser/prompt builder/shared QA, shared single/matrix OpenRouter execution, renderer/publication helpers, CLI, and synthetic unit/BDD tests. Phase 1 supports explicit `--language sk|en` with Slovak remaining the default. Phase 2A adds opt-in report-only `--models`; no track integration, path-based track detection, tail checks, translation workflows, or Phase 3 UI is implemented. See [README](../README.md) for executable commands and supported formats.
- **Upstream Content Interfaces (Read-Only):**  
  - Story frames: `../zafo-shorts/blog/posts/post_XXX.md` (e.g., `post_002.md`)  
  - Style & prompt anchors: `../zafo-shorts/blog/docs/STYLE_SHEET.md` (§1 Pinned Sample, §6 Slot-Injector Prompt)  
  - Slovak QA rules: `../zafo-shorts/blog/docs/SLOVAK_LEXICON.md` (§3 Czechism Trap Table, §4 English Calque Kill-List, §6 `TIER4_ADDON.txt` skeleton)  
- **External Vault Boundary (Outside Google Drive & Workspace):**  
  - **Confirmed constraint:** the whole `D:\` drive is forbidden for vault storage and generated output, including resolved links.  
  - Default vault path: `C:/Users/<User>/zafo-local/` (override via `ZAFO_VAULT_DIR`)  
  - Contains: `.env` (`OPENROUTER_API_KEY`), `TIER4_ADDON.txt`, and `output/`

### Phase 1 Delivery, Validation & Acceptance Record

- **Implementation baseline:** [PR #1](https://github.com/KontentWave/writing-injector/pull/1) merged as `7d5fe51`, retaining Slovak prompt/diagnostic commit `2daf039` and English-support commit `2a825bd`. The merged implementation tree matched the freshly validated feature tree.
- **Completed offline quality gate:** 290 tests passed; Ruff lint and format checks passed (26 files already formatted); strict mypy passed for 11 source files. These were manual offline checks, not hosted CI results; PR #1 had no GitHub check results.
- **Post-merge offline checks:** Slovak and English dry-run/strict lint-only checks passed across the module and console entrypoints. The Slovak fixture had 37 words and score 100; the English fixture had 50 words and score 100. No API calls, credential/addon reads, or vault/output writes occurred in those checks.
- **Human-run evidence:** The following results came from human-provided terminal output using benign synthetic inputs, not assistant-executed live requests. Historical Slovak trials established reported API connectivity and strict structural passes, but human review found language-quality limitations. Neither those trials nor the English results below establish production readiness.

The English fixture slot required 20-80 words:

| Human English Run | Words | Paragraphs | Score | Exit | Outcome |
|---|---|---|---|---|---|
| Strict generation | 99 | 3 | 70 | 5 | Word-count failure; no drafts written. |
| Non-strict diagnostic generation | 90 | 2 | 75 | 0 | Word-count failure; review report and merged diagnostic saved for manual review, not accepted output. |

- The strict run also had a sentence-count warning: a paragraph exceeded four sentences. Three paragraphs themselves were within the allowed 2-4 range.
- **Fixture control:** A separate copy of the existing English candidate fixture passed strict lint with 50 words, two paragraphs, and score 100. It was neither a shortened edit of the 90-word response nor a successful raw model output.
- **Source and credential handling:** Both human generation runs reported unchanged fresh before/after frame, style, and synthetic-addon hashes, and cleanup of the terminal's process API key. Original diagnostic evidence was preserved inside the synthetic vault's output directory. No credentials, addons, draft prose, or private vault paths are recorded here.
- **Remaining acceptance gap:** Raw English word-bound compliance remains unpassed. English QA is structural only; passing lint does not certify output language, grammar, POV, scene compliance, or natural writing. Provider availability, sustained performance, billing, and real upstream compatibility are not certified by these small synthetic trials.

---

## 2\. Canonical Repository Layout

```
zafo-injector/
├── AGENTS.md                          # Workspace guardrail: forbids agent execution of live injector or reading ~/zafo-local
├── pyproject.toml                     # Python 3.12 package metadata, CLI entrypoint, pytest, pytest-bdd, ruff, mypy
├── docs/
│   ├── PROJECT_ROADMAP.md             # Strategic vision & phased backlog (Step 1: PLAN)
│   ├── project_sheet.md               # Living technical spec & phase blueprints (Step 2: DRAFT)
│   └── adr/                           # Architectural Decision Records (e.g., ADR-001 Air-Gapped Vault)
├── specs/
│   └── features/                      # Executable Gherkin specifications (Step 3: SPECIFY)
│       ├── vault_airgap.feature
│       ├── slot_parsing.feature
│       ├── slovak_linter.feature
│       └── slot_injection.feature
├── scripts/
│   └── init_local_vault.ps1           # PowerShell bootstrapper for ~/zafo-local/
├── src/
│   └── zafo_injector/
│       ├── __init__.py
│       ├── __main__.py                # python -m zafo_injector entrypoint
│       ├── markdown.py                # Shared numbered-section and rule-table extraction
│       ├── models.py                  # Frozen dataclasses: SlotSpec, FrameDocument, LintIssue, LintReport, CandidateResult
│       ├── model_profiles.py          # Static validated matrix registry, overrides, and global request budget
│       ├── config.py                  # VaultConfig loader (.env + air-gap path containment check)
│       ├── parser.py                  # Extracts POV metadata, slot instructions, word-target bounds, and context window
│       ├── prompt_builder.py          # Combines STYLE_SHEET (§1 + §6) + TIER4_ADDON.txt + sliced frame context
│       ├── slovak_lint.py             # Shared structural QA; Slovak-only lexicon and morphological POV checks
│       ├── openrouter_client.py       # Shared single/matrix requests, global concurrency, bounded retries, redacted failures
│       ├── renderer.py                # Legacy drafts or report-only *.arena.md/*.arena.json, shared safe publication
│       └── cli.py                     # CLI (`python -m zafo_injector` / `zafo-inject`)
└── tests/
    ├── fixtures/                      # Separate Tier-1 non-explicit Slovak/English fixtures & mock API payloads
    ├── unit/                          # Inner-loop TDD unit tests
    └── bdd/                           # Outer-loop pytest-bdd step definitions
```

---

## 3\. Core Architecture & Data Contracts (`models.py`)

- **`SlotSpec`**  
  - `raw_comment: str` — Full `<!-- [TIER ... EXPLICIT INSERT SLOT: ...] ... -->` block.  
  - `min_words: int` / `max_words: int` — Parsed from header (e.g., `140`, `220`; defaults to `140–220`).  
  - `instructions: str` — Bullet instructions inside the slot comment.  
  - `slot_start_idx: int` / `slot_end_idx: int` — Exact character offsets in source frame for lossless splicing.  
- **`FrameDocument`**  
  - `source_path: Path`  
  - `source_text: str` — Original source including BOM and line endings, retained for lossless splicing.  
  - `pov: Literal["male", "female"]` — Explicit `POV: Male` / `POV: Female` metadata; Slovak suffix conventions remain supported but are not required in English.  
  - `context_before: tuple[str, ...]` — Up to 2 paragraphs immediately preceding the slot.  
  - `context_after: tuple[str, ...]` — Up to 2 paragraphs immediately following the slot.  
  - `slot: SlotSpec`  
  - `language: Literal["sk", "en"] = "sk"` — Explicit selection, appended to preserve existing constructor call patterns; frozen with the other fields.  
- **`ModelParams`**  
  - `model: str = "anthracite-org/magnum-v4-72b"`  
  - `temperature: float = 0.68`  
  - `min_p: float = 0.06`  
  - `top_p: float = 0.90`  
  - `repetition_penalty: float = 1.05`  
  - `quantizations: tuple[str, ...] = ("bf16", "fp16", "fp8")`  
- **`LintIssue` & `LintReport`**  
  - `LintIssue(rule_id: str, severity: Literal["error", "warn"], match: str, suggestion: str, line: int)`  
  - `LintReport(word_count: int, paragraph_count: int, issues: tuple[LintIssue, ...], score: int, passed: bool)`
- **Phase 2A frozen contracts**
  - `ModelProfile(params: ModelParams, supported_parameters: tuple[str, ...])` filters effective sampling and records unsupported omissions; matrix provider routing requires parameter support.
  - `CandidateResponse(model_id, index, attempts, text, failure)` retains the full model ID and 1-based request identity, with either text or an explicit `RequestFailure`, never both. Text is excluded from its representation.
  - `RequestFailure(code, http_status)` supplies only fixed redacted messages, never remote response bodies or transport exception text.
  - `ArenaCandidate(response, report)` has QA only for successful requests. `ArenaRun` keeps immutable profile/candidate tuples, validates complete model/index coverage and budgets, and derives API/strict status without choosing a winner.
  - Existing `ModelParams` defaults, `CandidateResult(index, text, report)`, and `generate_candidates(messages, params, n)` call patterns remain unchanged. Both execution modes reuse request construction, transport settings, cleanup, retries, shared QA/ranking, and the same safe two-file publisher.

---

### Implementation decisions (Phase 1)

- "Air-gap" means storage isolation, not network isolation: live generation sends the assembled prompt and optional local addon to OpenRouter.
- Context collections are immutable tuples. `FrameDocument.source_text` retains the source verbatim; `CandidateResult(index, text, report)` supplies deterministic tie-breaking.
- Dry-run prints a redacted structure report, performs no writes, and never reads credentials or the addon. Lint-only does not access the vault.
- `--language sk|en`, `--strict`, `--print-output`, `--style-sheet`, and `--lexicon` are implemented. Style defaults resolve relative to the frame's `posts` directory; only Slovak loads the neighboring lexicon. Explicit `--lexicon` in English is rejected with exit 2 before file/vault access. No language auto-detection is performed.
- Any API failure aborts the batch without drafts. Existing drafts are not overwritten. Strict all-failed batches produce exit 5 without drafts; non-strict failures are explicitly reported.
- Entire-drive `D:\` rejection supplements workspace, known Google Drive names, configured `GOOGLE_DRIVE_DIR`, and ancestor marker checks. Custom cloud mount discovery is not exhaustive.
- Real upstream formats, sustained live provider performance, and billing remain to be verified by a human. The synthetic connectivity evidence above is not production acceptance; assistants accessed no real vault and executed no live generation.
- Offline validation includes subprocess checks for both entrypoints, redirected vault children, staged-output failures, and partial mocked API failures. Parser bounds consume the complete target field, duplicate POV fields fail, and a leading BOM is excluded from context without changing source offsets. Markdown section discovery ignores fenced examples; lint paragraph boundaries tolerate trailing whitespace and LF/CRLF.
- Prompts end with selected-language-only, POV, inclusive word-bound, paragraph, and prose-only requirements, with an integer midpoint word-count target. Slovak grammatical guidance is retained; English receives first-person POV guidance without Slovak endings. These override conflicting anchors while the style sheet controls writing register. Generation prints redacted per-candidate rule IDs and line numbers, including before strict failure.
- Both languages reuse word/paragraph bounds, sentence warnings, exact boundary echoes, scoring, and ranking. Only Slovak applies `CZECHISM`, `CALQUE`, `CLINICAL_OR_HARLEQUIN`, and morphological `POV_DRIFT`. English does not check grammar, spelling, output language, narrative POV, or scene compliance. Passing lint does not certify natural language quality; human review remains required.
- Separate English frame/style/candidate fixtures use natural standard written English. Offline tests exercise both entrypoints, lexicon independence and explicit rejection, inclusive thresholds, immutable contracts, BOM/CRLF preservation, strict/non-strict redaction, and mocked HTTP generation with unchanged payload parameters and output safety. Existing Slovak coverage is retained.

<!-- PHASE_1_START -->

&nbsp;

## 4\. Phase 1 (MVP): Isolated-Vault Blog Slot Injector & Slovak/English QA

### Action

Deliver a tested, storage-isolated CLI pipeline that parses hybrid story frames, generates `N` slot candidates from `anthracite-org/magnum-v4-72b` via OpenRouter, scores shared structural QA plus Slovak-only lexicon/morphology checks, and writes reviewable \+ merged drafts exclusively to the validated external vault's `output/`. Use `--language sk|en`, defaulting to Slovak. The existing Slovak-lexicon bootstrapper is unchanged; English-only synthetic vaults can be prepared manually by a human without loading a Slovak lexicon.

### Task (Ordered Technical Steps)

1. **Project Foundation & Guardrail (`pyproject.toml`, `AGENTS.md`, `scripts/init_local_vault.ps1`):**  
   - Configure `pyproject.toml` with Python `>=3.12`, `httpx` (or stdlib `urllib.request` transport abstraction), and dev dependencies (`pytest`, `pytest-bdd`, `ruff`, `mypy`).  
   - Author `AGENTS.md` instructing workspace AI assistants never to run live slot injection without `--dry-run` and never to read or index `~/zafo-local/`.  
   - Implement `scripts/init_local_vault.ps1` (idempotent: never overwrites an existing `.env` or filled `TIER4_ADDON.txt` unless `-Force` is passed) creating `~/zafo-local/.env`, `~/zafo-local/TIER4_ADDON.txt` (extracted from `SLOVAK_LEXICON.md` §6), and `~/zafo-local/output/`.  
2. **Air-Gap & Configuration Loader (`src/zafo_injector/config.py`):**  
   - Implement `VaultConfig.load(vault_dir: Path | None, workspace_root: Path) -> VaultConfig`.  
   - Enforce **Hard Containment Check**: resolve canonical real paths (`Path.resolve()`) and raise `AirGapViolationError` if `vault_dir` or `output_dir` resides inside `workspace_root` (`Bookstore`) or any Google Drive mount containing `.gdoc` /workspace markers.  
   - Parse `.env` cleanly without mutating global OS environment variables; mask `api_key` in `__repr__`.  
3. **Frame & Slot Parser (`src/zafo_injector/parser.py`):**  
   - Implement `parse_frame(markdown_text: str, source_path: Path, window_paragraphs: int = 2, *, language: Literal["sk", "en"] = "sk") -> FrameDocument`.  
   - Extract explicit `POV: Male` or `POV: Female` from the top metadata comment, preserving the Slovak `(-l som)` / `(-la som)` conventions.  
   - Match one `<!-- [TIER ... INSERT SLOT: <min>–<max> slov] ... -->` in Slovak or `<min>–<max> words` in English (hyphen/en-dash supported; omitted bounds remain 140–220). Consume the complete target field, reject malformed or wrong-language units and missing/duplicate slots, and preserve exact offsets.  
   - Slice up to `window_paragraphs` clean prose paragraphs before and after the slot (skipping HTML comments and `#` headings).  
4. **Prompt Assembler (`src/zafo_injector/prompt_builder.py`):**  
   - Implement `build_messages(doc: FrameDocument, style_sheet_path: Path, tier4_addon_path: Path | None) -> list[dict[str, str]]`.  
   - Extract §1 and §6 from the supplied style sheet, adapt Slovak female POV anchors only in Slovak mode, append a non-empty local addon, and construct `system` \+ `user` messages. Context labels are Slovak in `sk` and English in `en`; the final authoritative contract selects language/POV/length/paragraphs without overriding style register.  
5. **Shared QA with Slovak Lexicon & Morphology (`src/zafo_injector/slovak_lint.py`):**  
   - Implement `LexiconRules.from_markdown(lexicon_path: Path) -> LexiconRules` parsing banned Czechisms (§3) and English AI calques (§4) from `SLOVAK_LEXICON.md`, supplemented by built-in inflected regex patterns (case-insensitive Unicode word boundaries `\b...\b`).  
   - Implement `lint_candidate(text: str, doc: FrameDocument, rules: LexiconRules | None = None) -> LintReport`. Slovak requires rules; English accepts only `None` and never reads a default lexicon. All following vocabulary/gender checks are Slovak-only:  
     - `WORD_COUNT`: verify `doc.slot.min_words <= words <= doc.slot.max_words`.  
     - `PARAGRAPH_BOUNDS`: verify `2 <= paragraphs <= 4` and flag paragraphs exceeding 4 sentences (`warn`).  
     - `CZECHISM` / `CALQUE`: flag exact banned token/phrase matches (`error`) with suggested Slovak replacements from `SLOVAK_LEXICON.md`.  
     - `CLINICAL_OR_HARLEQUIN`: flag banned terms from `STYLE_SHEET.md` §4 (*pohlavný úd, súlož, lono, jeho mužstvo, kvet lona, vlny rozkoše*).  
     - `POV_DRIFT`: in `"male"` POV, flag 1st-person feminine past-tense sequences (`\b\w+la som\b`, excluding quoted dialogue `„...“`); in `"female"` POV, flag unquoted `\b\w+[^a]l som\b`.  
     - `BOUNDARY_ECHO`: flag if the candidate repeats the last sentence of `context_before` or first sentence of `context_after`.  
     - Compute deterministic `score` (`100 - 25 * errors - 5 * warnings`) for automatic candidate ranking.  
6. **OpenRouter Client (`src/zafo_injector/openrouter_client.py`):**  
   - Implement `OpenRouterClient.generate_candidates(messages, params: ModelParams, n: int) -> list[str]`.  
   - Send OpenAI-compatible payload to `https://openrouter.ai/api/v1/chat/completions` including OpenRouter-specific `min_p`, `repetition_penalty`, and `provider: {"quantizations": list(params.quantizations), "allow_fallbacks": True}`.  
   - Strip accidental surrounding markdown fences or echoed slot tags if emitted by the model; handle HTTP `429`/`5xx` with bounded exponential backoff (max 2 retries).  
7. **Renderer & CLI (`src/zafo_injector/renderer.py`, `src/zafo_injector/cli.py`):**  
   - Implement `render_outputs(doc, ranked_candidates, output_dir)`:  
     - Writes `<stem>.candidates.md` (all `N` candidates sorted by `LintReport.score`, with inline lint table and word counts).  
     - Splices the top-scoring candidate into `doc` (replacing the `<!-- [TIER ...] -->` block) and writes `<stem>.merged.md` into `output_dir` while leaving the source `post_002.md` completely untouched.  
   - Implement CLI flags:  
     - `zafo-inject <post_path> [--language sk|en] [--candidates 3] [--model anthracite-org/magnum-v4-72b] [--temp 0.68] [--min-p 0.06] [--vault-dir PATH] [--dry-run] [--lint-only FILE]`  
     - `--dry-run` prints metadata/word-window/linter readiness and writes the redacted `Tier 1–2` prompt structure check without calling OpenRouter or printing `TIER4_ADDON.txt`.

### Accessibility (CLI Ergonomics & Terminal Output)

- **UTF-8 Slovak Diacritics Safety:** Explicitly reconfigure `sys.stdout` / `sys.stderr` to `utf-8` on Windows PowerShell so `ľ, š, č, ť, ž, ô, ä` never mojibake regardless of console codepage.  
- **`NO_COLOR` & Plain-Text Screen-Reader Compatibility:** Respect the `NO_COLOR` environment variable; never rely solely on ANSI red/green colors—always emit explicit `[PASS]`, `[WARN]`, and `[FAIL]` text prefixes and aligned Markdown/ASCII summary tables.  
- **Zero-Noise Exit Codes:** Standardize exit codes (`0` \= completed operation, including non-strict diagnostics rather than guaranteed lint acceptance; `2` \= CLI/configuration/parse/output error; `3` \= air-gap security violation; `4` \= OpenRouter API failure; `5` \= strict lint failure).

### Test Plan (Unit, BDD & Integration — Using 100% Tier-1 Synthetic Fixtures)

> **Fixture Rule:** Repository fixtures use benign, non-explicit `Tier 1` Slovak or English prose with synthetic slot comments. Temporary vaults and pytest storage must be fresh, outside the whole D: drive/workspace/cloud locations. Real HTTP transports are blocked; English generation is tested with mocked HTTP only.

- **Unit Tests (`tests/unit/`):**  
  - English selection/header/prompt/QA and mocked-generation coverage lives in `test_english.py`, with both languages covered by subprocess and lossless-rendering regression tests. The standard written English acceptance candidate has exactly 50 words and two paragraphs within the 20–80-word fixture slot.  
  - `test_config_rejects_vault_inside_workspace`: Verifies `AirGapViolationError` when `vault_dir` points inside `Bookstore` or a subdirectory.  
  - `test_config_redacts_api_key_in_repr_and_errors`: Ensures `OPENROUTER_API_KEY` never leaks into string representations or tracebacks.  
  - `test_parser_extracts_slot_bounds_and_male_pov`: Validates parsing `140–220 slov`, `-l som` POV, and exact 2-paragraph before/after slicing on a `post_002`\-shaped fixture.  
  - `test_parser_fails_on_missing_or_duplicate_slots`: Verifies `SlotParseError` on 0 or 2+ slot blocks.  
  - `test_prompt_builder_injects_golden_sample_and_addon`: Confirms `STYLE_SHEET.md` §1 \+ §6 \+ mock addon assembly.  
  - `test_linter_catches_czechisms_and_calques`: Tests detection of *vůbec, zrovna, záda, polštář, udělal jsem se* and *"vydýchol som dych, o ktorom som nevedel"*.  
  - `test_linter_enforces_pov_gender_lock_ignoring_dialogue`: Ensures unquoted *povedala som* triggers `POV_DRIFT` in male POV, while quoted `„Povedala som mu,“` passes cleanly\!  
  - `test_linter_checks_word_and_paragraph_bounds`: Verifies `<140w` / `>220w` errors and `>4` sentence paragraph warnings.  
  - `test_openrouter_payload_pins_quantizations_and_magnum_params`: Uses mock transport to assert exact JSON body (`temperature: 0.68`, `min_p: 0.06`, `repetition_penalty: 1.05`, `provider.quantizations`).  
  - `test_renderer_leaves_source_frame_untouched`: Confirms source file mtime/hash is unchanged and merged output lands strictly in `vault_dir/output/`.  
- **BDD Scenarios (`specs/features/` via `pytest-bdd`):**  
  - `vault_airgap.feature` — Blocking accidental Google Drive / workspace output paths.  
  - `slot_parsing.feature` — Extracting hybrid frame context and word targets.  
  - `slovak_linter.feature` — Ranking clean Slovak above Czech-bleed / romance-calque candidates.  
  - `slot_injection.feature` — End-to-end mocked CLI run producing `*.candidates.md` and `*.merged.md`.

### Perf / Security / Air-Gap Notes

- **Hard Air-Gap Enforcement:** `renderer.py` re-verifies output path containment right before `open(..., "w")` (defense in depth) and never echoes generated candidate text to `stdout` unless `--print-output` is explicitly passed by a human in an external terminal.  
- **Secret Hygiene:** `OPENROUTER_API_KEY` is read exclusively from `~/zafo-local/.env` or process env, transmitted only over HTTPS (`https://openrouter.ai`), and stripped from exception logs.  
- **Latency & Cost Target (Unverified):** Parallelize the `N=3` candidate completions (`concurrent.futures.ThreadPoolExecutor(max_workers=3)` with 45s per-request timeout). At most 2 retries per request can extend total runtime beyond 45 seconds. The original \~6–10 second / \~\$0.003 target is not a measured guarantee; live latency, provider availability, and billing require human verification.
- **Human-only English Acceptance:** Use only synthetic English inputs and an explicit unsynchronized vault outside D:. Keep credentials private. Capture fresh source hashes immediately before generation, archive old drafts inside that vault's output directory, acknowledge prompt transmission and possible costs, compare hashes afterward, and review natural English, POV, scene compliance, style, continuity, and structural bounds. Storage isolation is not a network air gap; mocked tests and historical Slovak connectivity trials do not establish production readiness. See the [README checklist](../README.md#human-acceptance).

<!-- PHASE_1_END -->

&nbsp;

---

<!-- PHASE_2_START -->

&nbsp;

## 5\. Phase 2: Implemented Comparison Arena (2A) & Deferred Track Support (2B)

### Action

Phase 2A's grouped design gate was approved on 2026-11-07, followed by implementation and synthetic offline validation. Its scope is a report-only comparison arena, not automatic selection/merging or production model acceptance. Phase 2B requires separate design and approval; no tracks, path inference, `CLEAN_TAIL_CHECK`, translation workflows, or UI were added.

### Phase 2A (Implemented): Offline-Validated Multi-Model Comparison Arena

1. Opt-in `--models m1,m2,...` selects 2-3 exact registered full IDs. Whitespace is trimmed; empty/duplicate/unknown/retired IDs are rejected without substitution. `--model` and `--models` are mutually exclusive, including the explicit legacy default. Existing single-model defaults, payloads, execution modes, public call patterns, retries, and output policy are retained.
2. The parser, style/prompt assembly, selected language, sliced frame context, bounds, shared QA, and per-model deterministic score/index ranking are reused. Messages are assembled once for the whole comparison. Explicit `--temp` overrides all profiles; explicit `--min-p` requires support in every selected model before file/vault access. Effective settings and omissions are recorded.
3. Matrix mode writes only `<stem>.arena.md` (per-model scorecards, candidate prose and local lint tables) and `<stem>.arena.json` (version-1 metadata-only schema). Full model/candidate identities, scores, word/paragraph counts, hard passes, warnings, attempts and explicit failures are preserved. No winner or merged draft is generated; scores are structure/Slovak heuristic QA, not grammar, language-quality, scene-compliance or safety certification.
4. Every planned candidate remains represented. Any API failure publishes explicitly `api_failed` reports and exits 4. With no API failures, strict mode publishes `strict_lint_failed` reports and exits 5 if any model has zero hard-passing candidates. Otherwise exit 0 means completed comparison, not universal acceptance. Local/publication errors exit 2 and storage violations exit 3, rolling back partial publications. Phase 1 still writes no drafts for API or strict all-failed batches.
5. A common per-model count defaults to 3, with at most 9 initial requests and 27 HTTP attempts per matrix run. One shared executor caps global concurrency at 3, preserves 45-second timeouts, and retries only 429/5xx at most twice with existing backoff. Actual attempts are reported; there is no new single-model candidate cap.
6. Both CLI entrypoints support both languages. Matrix dry-run validates roster/settings/budget without credential/addon reads, requests or writes; matrix lint-only is rejected. English never loads a default Slovak lexicon and still rejects explicit `--lexicon`. Candidate prose prints only with explicit `--print-output`, all successful candidates with identities, after both reports publish.
7. Development uses only benign Tier-1 fixtures, fresh validated C: pytest/cache storage, synthetic vaults, and mocked HTTP with existing real-HTTP blockers. Source hashes/BOM/CRLF and immutable contracts are preserved. Both report files reuse the Phase 1 containment/no-overwrite/staging/rollback/cleanup mechanism, including failed reports. No live generation, private-vault access, dependency installation, commit, push, or remote Git operation is part of this implementation task.

### Phase 2A Offline Validation Record (2026-11-07)

- **Verified starting state:** clean local `main` at `d45e3ead7ebd52d996e0f6d500795c89d2a5d7dc`, matching the existing local `origin/main` tracking ref. No fetch or other remote Git operation was performed. Fresh full baseline: 290 tests passed in 65.90 seconds, Ruff lint/format passed (26 Python files), and strict mypy passed (11 source files).
- **Completed fresh manual gate:** **519 tests passed in 111.47 seconds**; `ruff check --no-cache src tests` passed; `ruff format --check --no-cache src tests` passed (30 Python files); strict `mypy --cache-dir <fresh-safe-C-cache> src` passed (12 source files). Pytest used `-q -p no:cacheprovider --basetemp <fresh-safe-C-pytest-path>` with `PYTHONDONTWRITEBYTECODE=1`. Test storage, temporary vaults, and caches were fresh validated local C: locations outside D:/workspace/cloud storage.
- **Development evidence:** 185 focused core/single-model regression tests passed, followed by 171 post-fix arena/single-model tests in 29.70 seconds (including 77 arena tests). A confirmed argparse object-identity defect allowed programmatic callers reusing the exact default model string to bypass `--model`/`--models` mutual exclusion. Default resolution now occurs after parsing; both argument orders reject before file access, with unchanged Phase 1 payload defaults. Strict type findings were corrected without casts or caller breakage; a test setup mistakenly combining existing mutually exclusive offline modes was corrected. Pylance verified all 13 existing public client call sites and all three lint-diagnostic helper call sites remained compatible.
- **Scope and limitations:** These are local manual synthetic/mocked checks, not hosted CI or live acceptance. Both entrypoints/languages, shared concurrency, payloads, actual attempts/retries, exact bounds, explicit API/strict failures, deterministic schema/ranking, source immutability, output containment/no-overwrite/rollback/cleanup, and legacy regressions were exercised. No live generation or private-vault access occurred. The human arena benchmark remains unexecuted; historical raw English bounds and language-quality acceptance gaps remain unchanged.

### Phase 2B (Deferred): Track Integration & Continuity-Tail Checks

1. Resolve `blog`, `serial`, and `dark-romance` tracks and corresponding style sheets only after a separate design and approval. Define explicit selection, any optional path inference, override precedence, and rejection of ambiguous paths; develop against synthetic layouts and styles, not real upstream prose or private addons.
2. Define which text a `CLEAN_TAIL_CHECK` examines before implementing the proposed closing 150-250-word post-scene continuity check. Clarify whether the target is an existing episode tail or assembled output, not an unrelated short insertion candidate.
3. Tail length, structure, and configured heuristics may be checked deterministically. Passing such a rule must not be represented as certification that prose is safe Tier 1-2 content; human safety and scene-compliance review remains necessary.
4. Keep selected-language QA consistent. Track rules must not introduce Slovak lexicon or morphological checks into English mode.

### Approved Phase 2A Decisions and Public Metadata Snapshot (2026-11-07)

- Public [catalog](https://openrouter.ai/api/v1/models) and individual model `/endpoints` metadata were read without credentials, prompts, or inference. These are planning snapshots, never offline runtime/test dependencies or live availability/billing guarantees.

| Approved full ID | Supported matrix sampling | Catalog input/output USD per million tokens |
|---|---|---|
| `anthracite-org/magnum-v4-72b` | temperature, top_p, min_p, repetition_penalty | 2.50 / 5.00 |
| `deepseek/deepseek-chat-v3-0324` | temperature, top_p | 0.29 / 1.14 |
| `sao10k/l3.1-euryale-70b` | temperature, top_p, min_p, repetition_penalty | 0.85 / 0.85 |

- Each approved ID had an fp8 endpoint with status 0. The status-0 DeepSeek endpoint advertised 0.25 / 1.00 rather than the catalog aggregate. The old `sao10k/l3.3-euryale-70b` ID was absent from the catalog with zero endpoints; replacement by the listed **3.1** ID was explicitly approved, not silently substituted.
- Defaults: temperature 0.68/top_p 0.90; min_p 0.06/repetition_penalty 1.05 only where supported, omitted for DeepSeek. Matrix provider settings retain bf16/fp16/fp8 and `allow_fallbacks=true`, adding `require_parameters=true` to avoid silently ignored parameters. Explicit overrides take precedence as specified above.
- JSON root fields: schema_version, mode, status/exit/strict, language/POV/bounds, QA limitations/formula, execution budgets/attempts, and models. Each model records effective settings/support omissions/provider, status, scorecard and candidates. Pass rates use all requested candidates, including API failures, as denominator. Each candidate has stable ID/index, attempts, status, nullable score/word/paragraph/pass/error/warning metrics, redacted rule/severity/line issues, and a safe failure code/status/message. API failures have null QA metrics/issues, never zero-score success-shaped placeholders. Prose/matched text/suggestions appear only in the vault-local Markdown review. Full schema and failure table are in [README](../README.md#arena-reports-schema-and-failure-policy).
- Future human-only benchmark is **defined, not executed**: three models x three candidates x two languages = 18 initial requests / at most 54 attempts, using identical per-language synthetic frame/style/addon/messages and unchanged inclusive bounds. Separate approval of prompt transmission and a dollar budget is required before paid testing; request caps do not enforce a dollar cap. Record actual billing/latency/attempts/failures and fresh source hashes in the synthetic vault output directory.
- Small-benchmark acceptance: no API failures; every raw candidate within word/2-4-paragraph bounds and passing all hard QA rules; warnings reviewed, and independent human language/grammar/naturalness/POV/style/scene/continuity review. No truncation, relaxed bounds, edited-output substitution or fixture/mock acceptance. Historical English 99/90-word failures remain unpassed; the 50-word fixture is only a control. Even passing this benchmark is not production readiness or upstream/provider certification.

### Accessibility

- Tabular model-vs-model scorecards in plain Markdown and terminal ASCII (`NO_COLOR` compliant). Terminal output remains metadata-only unless `--print-output` is explicitly requested; prose-bearing reports belong exclusively in the validated external vault's output directory.

### Test Plan

- Phase 2A: synthetic unit/BDD tests cover profile validation/overrides and exact request limits, both entrypoints/languages with approved offline combinations/rejections, mocked payloads/identical messages/stable mapping, deterministic per-model reports/version-1 schema, one global executor and retries/actual attempts, explicit API/strict/non-strict failures, redaction/explicit printing, raw 19/20/80/81/90/99-word threshold controls, unchanged source hashes/BOM/CRLF, immutable contracts, no automatic winner/merge, containment, no overwrites, competing publication, rollback and cleanup. Existing Phase 1 regressions remain covered.
- Phase 2B, only after separate approval: synthetic track-selection/path-inference tests and precisely scoped continuity-tail tests. No test result certifies semantic Tier 1-2 safety.

### Perf / Security Notes

- The approved and implemented shared three-request concurrency cap is not a guarantee of per-key rate-limit compliance. Raising it requires separate approval and validation.
- Three models with three candidates each mean nine initial requests and at most 27 attempts per invocation. 45-second per-request timeouts and bounded retries do not guarantee total run latency or a dollar budget. Publication conflicts are still checked after generation, so repeated human live requests can incur charges before reports are blocked.
- Assistants never execute live generation or inspect private vaults, credentials, addons, or real upstream prose. Human live comparisons transmit assembled prompts to OpenRouter and may incur charges; storage isolation is not a network air gap.

<!-- PHASE_2_END -->

&nbsp;

---

<!-- PHASE_3_START -->

&nbsp;

## 6\. Phase 3 (Optional Backlog): Localhost Candidate Picker & Inline Diff UI

### Action

Provide an optional `zafo-inject --serve` localhost-only (`127.0.0.1`) web picker to inspect lint highlights side-by-side, make quick Slovak line-edits, and export the final merged file in one click.

### Task (High-Level)

1. Serve a zero-dependency local HTML/CSS/JS view bound strictly to `127.0.0.1` (random ephemeral port \+ CSRF token).  
2. Highlight `CZECHISM`, `CALQUE`, and `POV_DRIFT` spans inline with click-to-apply Slovak replacements from `SLOVAK_LEXICON.md`.  
3. Save edited selection to `~/zafo-local/output/<stem>.merged.md`.

### Accessibility (ARIA)

- Semantic landmarks (`<main>`, `<section aria-labelledby="...">`), keyboard-navigable candidate selection (`role="radiogroup"`), `<mark>` annotations paired with `aria-describedby` tooltips (not color-alone), and `aria-live="polite"` save confirmations.

### Test Plan

- Local HTTP endpoint unit tests (`127.0.0.1` binding, CSRF rejection, save handler) \+ DOM/ARIA attribute assertions.

### Perf / Security Notes

- Reject non-loopback `Host` headers; zero external CDN assets or telemetry calls (100% offline localhost rendering).

<!-- PHASE_3_END -->