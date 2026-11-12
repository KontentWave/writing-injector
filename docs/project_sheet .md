# `project_sheet.md` — `zafo-injector` (Living Technical Specification)

> **Project:** `zafo-injector` — Isolated-Vault OpenRouter Slot Injector & Slovak/English QA **Framework:** Iterative Scrum-XP (`PLAN -> DRAFT -> SPECIFY (.feature) -> EXECUTE (BDD/TDD) -> AUDIT`) **Target Runtime:** Windows 11 \+ PowerShell 7 \+ Python 3.12+ (zero heavy ML dependencies) **Primary Model Target:** `anthracite-org/magnum-v4-72b` via OpenRouter Chat Completions API

---

## 1\. Current State ("As-Built" Present)

- **Version:** `0.1.0` (Phase 1, report-only Phase 2A, and the first Phase 2B explicit-track increment are implemented and offline-validated; explicit tracks are merged through [PR #5](https://github.com/KontentWave/writing-injector/pull/5). Human-run Phase 1 connectivity, a Phase 2A English smoke, a successful Phase 2B English Magnum structural smoke with positive user-supplied quality feedback, and Slovak follow-ups with human-reported language-quality rejection are recorded. The human now prefers English drafting followed by manual Slovak translation and editing. Formal English/Slovak benchmark acceptance and continuity-tail implementation remain pending).
- **Implemented Modules:** Bootstrapper, frozen models, configuration/storage checks, static model-profile registry, language-aware parser/prompt builder/shared QA, shared single/matrix OpenRouter execution, renderer/publication helpers, CLI resource resolution, and synthetic unit/BDD tests. Phase 1 supports explicit `--language sk|en` with Slovak remaining the default. Phase 2A adds opt-in report-only `--models`; the first Phase 2B increment adds paired explicit `--track`/`--tracks-root` selection. No automatic track detection, tail checks, translation workflows, or Phase 3 UI is implemented. See [README](../README.md) for executable commands and supported formats.
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
- **Remaining acceptance gap at this Phase 1 checkpoint:** These trials did not establish raw English word-bound compliance; the later Phase 2A smoke is recorded separately below. English QA is structural only; passing lint does not certify output language, grammar, POV, scene compliance, or natural writing. Provider availability, sustained performance, billing, and real upstream compatibility are not certified by these small synthetic trials.

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

## 5\. Phase 2: Comparison Arena (2A) & First Explicit-Track Increment (2B)

### Action

Phase 2A's grouped design gate was approved on 2026-11-07, followed by implementation and synthetic offline validation. Its scope is a report-only comparison arena, not automatic selection/merging or production model acceptance. The first Phase 2B explicit-track contract and feature-branch creation were separately approved on 2026-11-10; after offline validation and separate publication approvals, [PR #5](https://github.com/KontentWave/writing-injector/pull/5) merged that day. This increment does not complete all Phase 2B work: automatic track detection is excluded, and `CLEAN_TAIL_CHECK`, all continuity-tail functionality, translation workflows, and UI remain deferred.

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

### Phase 2A Human Offline Preparation Checkpoint (2026-11-08)

Recorded from human-provided metadata-only JSON and redacted terminal diagnostics for runbook sections A0/A2, using unchanged benign English fixtures at repository baseline `062480282681605b8376dad3a9ab9167d150c786`. This is project-status evidence, not a live benchmark report.

- **A0 complete:** Shared setup and all eight runbook helpers were reported loaded in PowerShell 7.6.9; the existing virtualenv Python and console executable paths were present.
- **A2 complete, dry-run only:** Both entrypoints' English `--models --dry-run` previews passed the helper's exit-0 guards. Metadata matched all three approved full IDs, English/no lexicon, male POV, unchanged 20-80-word bounds, one candidate per model, 3 planned initial requests / at most 9 HTTP attempts, and concurrency 3. Sampling/omissions and displayed provider restrictions matched the approved profiles. The QA-limitation notices were expected, not failed checks.
- **Storage and inputs:** A fresh, unredirected synthetic C: vault passed path validation; its genuinely unsynchronized parent was confirmed by the human. Output contained **0 entries**, including hidden entries, and no addon existed. Reported SHA-256 hashes of the [English frame](../tests/fixtures/frame_en.md) and [style](../tests/fixtures/STYLE_SHEET_EN.md) matched the approved baseline. No private vault paths, credentials, prose, or benchmark report contents are recorded here.
- **Stopped boundary at this checkpoint:** **A0/A2 were complete; B1 remained unreleased on 2026-11-08, with the workflow paused before paid English smoke.** No Phase 2A live generation or raw-candidate acceptance was established at that point. Authentication, billing/headroom, and fresh public availability remained unverified. No dependency installation or Python test-suite rerun occurred; the historical raw English bounds and language-quality acceptance gaps remained unchanged.

### Phase 2A Human English Smoke Checkpoint (2026-11-09)

This project-status summary records human-provided redacted diagnostics, an explicitly identified metadata-only projection, a human-supplied daily/model billing export, and qualitative feedback. Original benchmark reports and records remain in the validated external vault's output; no credentials, private vault paths, prompts, addons, or candidate prose are included here.

- **Human-only execution:** After refreshed A0/A2 preparation and explicit B1 release, the human ran one English candidate per approved model with unchanged benign Tier-1 frame/style inputs, 20-80-word bounds, 2-4 paragraphs, no addon, and no Slovak lexicon. All three requests succeeded on their first attempt: **3 initial requests, 3 actual HTTP attempts, no retries or API failures**, against an approved maximum of 9 attempts and global concurrency 3. Whole-invocation elapsed time was **7.817 seconds**, not per-model/request latency.
- **Configuration and immutability:** Metadata matched the approved sampling, DeepSeek omissions, and provider restrictions. Fresh before/after English frame/style SHA-256 values matched each other and the approved baseline; sources were unchanged. Storage validation passed for the fresh synthetic C: vault, whose unsynchronized parent was human-confirmed.

| Approved full model ID | Words | Paragraphs | Score | Hard QA | Billed USD |
|---|---:|---:|---:|---|---:|
| `anthracite-org/magnum-v4-72b` | 87 | 2 | 75 | `WORD_COUNT` failure | 0.001390 |
| `deepseek/deepseek-chat-v3-0324` | 75 | 2 | 100 | Pass | 0.000207 |
| `sao10k/l3.1-euryale-70b` | 86 | 2 | 75 | `WORD_COUNT` failure | 0.000383 |

- **Strict outcome:** All candidates had zero QA warnings and one attempt. The original run correctly published `strict_lint_failed` reports and exited **5**, because Magnum and Euryale exceeded the unchanged maximum. No automatic winner or merged draft was produced. No candidate was truncated or edited into acceptance, and the historical strict result is not reclassified.
- **Billing evidence:** The export's three 2026-11-09 model/day entries total **USD 0.001980** for three requests; settlement was human-confirmed. The supplied export does not identify actual providers, token counts, or per-request latency. Routing restrictions and catalog prices are not substitutes for those observations. The human revised the cumulative benchmark budget to **USD 10 total**, including earlier spending, not daily or per stage; request limits still do not enforce a dollar cap.
- **Human quality preference:** The human preferred Magnum's prose and explicitly prioritized fiction quality over minor word-target deviations for model selection. This is a legitimate qualitative preference, separate from the strict constraint result: DeepSeek's structural score does not establish superior writing, and Magnum's word-count failure does not establish inferior writing. Full categorical language, grammar, naturalness, POV, style, scene, continuity, and benign-content review was not supplied. No independent prose-quality certification is claimed.
- **Intended use and model-version distinction:** Human-stated interests are Magnum v4 72B for mature-fiction scenes, immersive prose, and character interactions, and Euryale L3.3 70B v2.3 for emotional interaction, character consistency, and roleplay. These are intended evaluation goals, not capabilities established by this benign smoke. The actual Euryale tested here was **L3.1 70B v2.2**, `sao10k/l3.1-euryale-70b`; the desired L3.3 target was not tested or approved as a registry replacement. Exact availability, provider support, pricing, and any roster change require a fresh explicit decision before a future human run.
- **Acceptance and next boundary:** The human considers controlled live evaluation necessary for judging fiction quality; offline checks and word-count scores cannot replace that assessment. Nevertheless, this diagnostic smoke is not formal benchmark acceptance. Formal English and Slovak runs remain unexecuted. Any future quality-first acceptance policy must be agreed prospectively, separately from the unchanged strict QA implementation. This record releases no rerun or further paid stage, changes no code/profiles/fixtures/bounds, and does not authorize upstream/private prose access or assistant-executed inference.

### Phase 2B (First Increment): Explicit Track Integration

1. `--track blog|serial|dark-romance` and `--tracks-root ROOT` must be supplied together. Both entrypoints use the same CLI resolver. The root is explicit, with no environment default, ancestor search, or inference from paths, filenames, headers or prose. Without either flag, existing defaults and behavior remain unchanged.
2. The approved synthetic layout has `ROOT\<track>\docs\STYLE_SHEET.md` for Slovak and `STYLE_SHEET_EN.md` for English, plus shared `ROOT\docs\SLOVAK_LEXICON.md` for Slovak only. Frames may be nested beneath the selected track directory; `posts`/`episodes` are illustrative, not discovery rules. Only selected/consumed resources are required. The [README contract](../README.md#explicit-tracks-first-phase-2b-increment) documents the layout and safe previews; no real upstream layout or story prose was inspected.
3. Explicit `--style-sheet` and Slovak `--lexicon` independently replace defaults, including with paths outside the source root. Shared styles require an explicit override; no shared, cross-track or cross-language fallback occurs. A missing/malformed effective resource fails with exit 2. A missing replaced default is irrelevant. Explicit resource overrides never bypass frame/track membership validation.
4. The root and selected track directory must exist; the selected directory must not be redirected. The resolved frame must stay under that directory, and consumed default resources inside their designated `docs` directory. Invalid tracks, unpaired flags, mismatches and invalid layouts fail with exit 2. Fixed paths eliminate discovery ambiguity: alternative layouts are not searched or guessed.
5. Language remains explicitly `sk|en`, default `sk`; English never loads Slovak lexicon or morphological checks and rejects explicit `--lexicon` before file/vault access. Wrong-language slot units still fail. Override prose is not used to infer language or track. No-track English still defaults to neighboring `STYLE_SHEET.md`; only tracked English defaults to `STYLE_SHEET_EN.md`.
6. Dry-run validates effective resources and vault paths without credential/addon reads, HTTP or writes. Lint-only validates the mapping and applicable lexicon but neither reads/requires styles nor accesses the vault; matrix lint-only remains rejected. Legacy and matrix generation reuse existing prompt/QA/model/publication behavior, with messages assembled once for the matrix and unchanged request/retry/concurrency limits.
7. Track/default/override indicators appear only in redacted terminal metadata for explicitly tracked runs. Persisted Markdown formats, version-1 arena JSON fields, renderer contracts, output filenames and merged-draft behavior are unchanged. Reports do not persist track provenance in this increment. Same-stem cross-track runs retain existing no-overwrite conflicts.
8. Development and validation use only benign synthetic Tier-1 trees, fresh validated assistant-owned C: test/cache storage, and mocked HTTP. Sources remain read-only during invocation; generated reports/drafts stay inside the validated synthetic vault's `output`. Implementation approval did not authorize publication or live testing; commit/push/PR creation, merging, and fetching/local-main synchronization were separately approved and are recorded below. No paid testing, private-vault/credential/addon/upstream inspection or branch deletion was part of this delivery.

### Phase 2B Explicit-Track Offline Validation Record (2026-11-10)

- The initial focused contract test failed on the then-unsupported track flags before implementation. After implementation, the focused track/BDD run passed **88 tests**.
- The combined relevant regression run passed **426 tests in 104.96 seconds**: track unit/subprocess checks, existing both-entrypoint CLI checks, renderer/legacy behavior, English QA, arena reports, arena client limits/retries/concurrency, and BDD features. This was a targeted compatibility gate, not a full-suite rerun; the 88-test run overlaps it and is not an additional test count.
- Ruff lint and format checks passed for all four modified Python files; strict mypy passed for all 12 source files. Pylance reported no CLI diagnostics, and syntax checks passed for the CLI and new track tests.
- All execution evidence is offline, using benign synthetic fixtures and mocked HTTP with fresh validated C: temporary/cache storage. No live generation, paid request, private-data inspection or production/upstream acceptance is established.

### Phase 2B Publication & Current Checkpoint (Merged 2026-11-10; Reverified 2026-11-11)

- **Published increment:** Commit `607af582d35587bb8938dd337d11fb2d01254e6b` on `feature/phase2b-explicit-tracks` was committed, pushed and submitted as [PR #5](https://github.com/KontentWave/writing-injector/pull/5) after explicit authorization. A later, separate authorization released the merge. Direct pre-merge review found no blocking findings; GitHub reported no check results, so the validation record above remains manual offline evidence, not hosted CI.
- **Merged baseline:** PR #5 merged on 2026-11-10 as `f6e53e8acaf8ae45b29977d02c2ac4eaff0db71a`. Its tree `1dd514add5b792b0559a3231f4e9038a720e8b85` exactly matched the offline-validated feature tree; the merge introduced no additional implementation changes.
- **Local synchronization:** After separate approval, `origin/main` was fetched and local `main` fast-forwarded without force/reset. Read-only checks on 2026-11-11 reconfirmed local HEAD, local `origin/main`, and independently queried GitHub `main` all at the merged baseline, with a clean worktree before this documentation update. The local and GitHub feature branches were retained at `607af582d35587bb8938dd337d11fb2d01254e6b`.
- **Compatibility and remaining scope:** Both entrypoints, explicit language separation, no-track defaults, model profiles, QA/scoring/strict exits, arena limits and report/output contracts remain as documented above. Track provenance is terminal-only; same-stem output conflicts retain the no-overwrite policy. This is the first Phase 2B increment, not completion of continuity-tail work or production/upstream acceptance.
- **Earlier stop point:** On 2026-11-11, the user initially chose to document progress rather than start live testing; no Phase 2B live request had occurred at that checkpoint. The later human-only English smoke below received separate prompt-transmission and spending approval. Merge approval itself released neither paid testing nor formal benchmark acceptance.
- **Initial documentation-only follow-up:** The publication checkpoint used read-only repository/GitHub metadata and tree-identity checks. No Python tests were rerun, dependencies installed, runtime code changed, private data inspected or new Git publication performed during that follow-up.
- **Published smoke documentation:** [PR #6](https://github.com/KontentWave/writing-injector/pull/6) merged on 2026-11-11 as `1694494311bb6d13e0bd81750dc0d12e7c69bba3`, recording the English and initial Slovak smoke checkpoints below. GitHub main and the merge metadata were independently verified through WSL `gh` before preparing the later Slovak follow-up record. This documentation baseline introduced no runtime changes.

### Phase 2B Human English Magnum Smoke Checkpoint (2026-11-11)

This checkpoint records human-provided redacted terminal diagnostics, a reported cost, and a user-supplied qualitative assessment. The assistant did not open the human live vault or its prose-bearing reports. No credentials, addons, prompts, candidate prose or private vault paths are reproduced here.

- **Scope and model attribution:** The human invoked single-model generation with `--track blog`, explicit `--tracks-root`, `--language en`, `--model anthracite-org/magnum-v4-72b`, `--candidates 1` and `--strict`, without an addon or Slovak lexicon. The recorded request was already **Magnum v4 72B**, not GPT; references to a GPT baseline or a subsequent switch to Magnum in the supplied review do not match the posted command. No Euryale trial or model-registry change was part of this smoke.
- **Inputs and offline preparation:** A separate benign synthetic Tier-1 English adaptation preserved an empty insertion slot followed by existing closing prose. Its insertion bounds were unchanged at **140-220 words**, with a 190-word existing ending. A prepared control fixture, not a model response, had 180 words, three paragraphs and score 100. Both entrypoints passed dry-run and strict lint-only with unchanged input hashes/mtimes. Before credential setup, a fresh external C: human-smoke vault path passed existing storage validation; offline checks neither created that vault nor performed inference.
- **Human execution:** The first invocation failed local API-key validation with exit 2, before inference. The human corrected the private configuration and repeated the invocation with fresh source/style hashes. This local failure is not an API retry or a second generated candidate.

| Invocation | Words | Paragraphs | Score | Exit | Outcome |
|---|---:|---:|---:|---:|---|
| Initial local configuration failure | - | - | - | 2 | Rejected before inference; no drafts. |
| Corrected human live invocation | 174 | 4 | 100 | 0 | Generated candidate passed strict structural QA; both drafts published. |

- **Publication and immutability:** Terminal output reported `frame_en.candidates.md` and `frame_en.merged.md` written inside the fresh synthetic vault's `output` directory. Fresh before/after source and style hashes were reported unchanged for both invocations. The no-addon warning was expected. This was legacy single-model publication, not an arena comparison.
- **Reported cost and execution limits:** The human reported **USD 0.00241**, within the separately approved USD 0.10 smoke budget. Billing was not independently inspected. Existing retry limits allowed at most three HTTP attempts for the successful invocation; its actual attempt count, provider, token usage and latency were not supplied. Request limits do not enforce a dollar cap.
- **User-supplied quality assessment:** The supplied review judged the English smoke solidly satisfactory, with natural entry/exit transitions, appropriate style, concrete details and good continuity. Minor editorial notes concerned explanatory telling, a procedural closing summary and a possible physical-staging ambiguity. This is qualitative feedback supplied by the user, not an independent full-text assessment by the assistant or a new deterministic acceptance rule. General claims about other models' tendencies were not established by this run.
- **Acceptance and next boundary:** This is a successful human-run English structural smoke with positive qualitative feedback, not formal English/Slovak benchmark acceptance, production readiness or prose/content-safety certification. The distinct 140-220-word fixture does not retroactively pass earlier 20-80-word failures. QA, scoring, strict exits, model profiles, sampling and output contracts remain unchanged. No further paid invocation is released by this record; continuity-tail design and implementation remain paused and unapproved.

### Phase 2B Human Slovak Magnum Smoke Checkpoint (2026-11-11)

This checkpoint records human-provided redacted terminal diagnostics only. The assistant did not open the human live vault or any candidate/report content. No credentials, addons, prompts, candidate prose or private vault paths are reproduced here.

- **Scope and preparation:** A fresh benign synthetic Tier-1 Slovak library-volunteer fixture used the explicit `blog` track, a track-local Slovak style sheet and shared synthetic Slovak lexicon. It retained the 140-220-word insertion bounds. The separately prepared control fixture, not a model response, had 173 words, three paragraphs, score 100 and no findings. Both entrypoints passed dry-run and strict lint-only; focused in-memory probes confirmed one hard rejection each for a Czechism, the configured English calque and female narrator morphology. A fresh external C: human-smoke vault path passed both exact-argument dry-run checks without being created.
- **Human execution:** The human then invoked single-model generation with `--track blog`, explicit `--tracks-root`, `--language sk`, `--model anthracite-org/magnum-v4-72b`, `--candidates 1` and `--strict`, without an addon. The candidate had 118 words and six paragraphs, violating both required structural bounds.

| Candidate | Words | Paragraphs | Score | Exit | Outcome |
|---|---:|---:|---:|---:|---|
| Human live candidate 1 | 118 | 6 | 50 | 5 | Failed `WORD_COUNT` and `PARAGRAPH_BOUNDS`; strict mode wrote no drafts. |

- **Immutability and execution limits:** Terminal output reported unchanged hashes for the frame, style sheet and lexicon. The expected no-addon warning appeared. Existing retry limits allowed up to three HTTP attempts, but actual attempt count, provider, token usage, latency and billed cost were not supplied. Because generation occurred, a charge may have been incurred even though strict mode prevented publication.
- **Interpretation and next boundary:** This is a failed Slovak structural smoke, not a prose-quality finding, formal Slovak benchmark acceptance, a reason to change word/paragraph QA, or evidence that the offline fixture/control is invalid. No output publication, rerun, model replacement, sampling change or further paid invocation is released by this record. Any subsequent paid test requires separate approval.

### Phase 2B Slovak Magnum Follow-Ups and Human Workflow Decision (2026-11-11)

This record uses human-provided redacted terminal diagnostics and the human's qualitative assessment. The assistant did not inspect the human live vault, credentials, addons, candidate/report prose or upstream content. No prompt, generated prose, credential or private vault path is reproduced here.

- **Scope and unchanged contract:** The follow-up commands selected single-model `anthracite-org/magnum-v4-72b`, explicit `--track blog` and `--tracks-root`, `--language sk`, `--candidates 1` and `--strict`, without an addon. A disclosed benign synthetic Tier-1 library-volunteer fixture retained inclusive 140-220-word bounds and 2-4 nonempty paragraphs. Prompts, sampling defaults, model profiles, QA rules, scoring and strict exits were not changed to obtain a pass. The prospectively agreed smoke success criteria additionally required score 100 and verified fresh before/after source hashes.
- **Offline preparation:** A separate session-local PowerShell wrapper, not a new repository CLI feature, passed **23 offline checks** with disposable synthetic C: storage and fake CLI execution for paid-dispatch paths. Real CLI execution during assistant validation used dry-run only. Fresh source copies matched all three recorded preparation SHA-256 values; this did not establish the earlier live invocation's source integrity. The guarded human command checked output conflicts, performed dry-run preflight, pinned the synthetic input hashes and captured fresh before/after hashes. Its invocation was never automatically retried.

| Observed human generation | Words | Paragraphs | Score | CLI exit | Outcome |
|---|---:|---:|---:|---|---|
| First follow-up | 109 | 4 | 75 | Not printed | `WORD_COUNT` failure; strict rejection reported no drafts. |
| Latest guarded run | 151 | 3 | 95 | 0 | No hard QA errors; one warning; both drafts reported published. |

- **First follow-up evidence limits:** Changing the selected vault root left its expected output directory absent. Both hash-file writes and the subsequent comparison failed, but the original PowerShell sequence did not stop before generation. Fresh source immutability was therefore unverified. The strict-failure diagnostic was visible, but its numeric process exit was not printed; it is not represented as an independently observed exit 5.
- **Separate unresolved invocation and local guard stops:** An intervening invocation could not be classified because its initial terminal diagnostics were unavailable and the human later reported deleting its before/after hash files and run metadata. A reported missing credential file does not establish zero requests or zero cost, because a process API-key variable could also supply the credential. That invocation's execution, result and billing remain **unverified**; deleted evidence was not reconstructed. Subsequent posted output-readiness conflict diagnostics, including printed wrapper exit 2, occurred before CLI preflight or generation. Those local stops are not additional generated candidates or API retries. The later paid invocation received renewed explicit transmission, budget and exact-command approval; the assistant did not clear the vault or execute it.
- **Latest publication and integrity:** The latest human terminal output reported `frame.candidates.md` and `frame.merged.md` written inside the explicitly selected synthetic C: vault's `output` directory. It also reported the frozen source baseline and fresh before/after frame/style/lexicon hashes verified, with both CLI and wrapper exits **0**. These are terminal-reported observations, not assistant inspection of the live files.
- **Warning and acceptance distinction:** The warning was `PARAGRAPH_BOUNDS` at line 3. In the unchanged linter this warning means a paragraph exceeded four heuristically counted sentences; the three-paragraph count itself passed. One warning and no errors produce score **95**, and warnings do not fail strict mode. This was a hard-QA pass, **not full planned smoke acceptance**: it missed the agreed score-100 criterion and the human rejected its language quality. No candidate was edited, truncated or rescored into acceptance.
- **Human quality assessment and workflow decision:** The human judged the latest Magnum Slovak output **unusable** and chose English drafting followed by **manual translation into Slovak and human Slovak editing**, stopping further paid Slovak smokes at this checkpoint. This is a user-supplied assessment of the observed output, not an independent assistant prose review or a general capability benchmark. No automated translation feature, replacement model or new paid English stage was implemented or released by this decision.
- **Cost, limits and remaining boundary:** The latest invocation had a separately approved **USD 0.03** human-monitored allowance, not a CLI-enforced dollar cap. Existing retry behavior allowed up to three HTTP attempts with 45-second per-request timeouts. Actual HTTP-attempt count, provider, token usage, latency and billed cost were not supplied in the posted diagnostics; one requested candidate is not proof of one HTTP attempt. These observations establish neither formal Slovak benchmark acceptance nor production readiness. No further paid invocation is released by this record; continuity-tail design and implementation remain paused and unapproved.

### Phase 2B (Still Deferred): Continuity-Tail Checks

1. Define which text a `CLEAN_TAIL_CHECK` examines before implementing the proposed closing 150-250-word post-scene continuity check. Clarify whether the target is an existing episode tail or assembled output, not an unrelated short insertion candidate.
2. Tail length, structure, and configured heuristics may be checked deterministically. Passing such a rule must not be represented as certification that prose is safe Tier 1-2 content; human safety and scene-compliance review remains necessary.
3. Keep selected-language QA consistent. Future tail rules must not introduce Slovak lexicon or morphological checks into English mode. No tail functionality or tail-length rule is part of the explicit-track increment.
4. The 2026-11-11 design discussion considered an explicit opt-in check of a marked, existing post-slot ending, with inclusive 150-250-word bounds and a separate strict gate. These were tentative design preferences, not approval of the concrete contract or a feature branch. Footer handling and formatting-only context items remain unresolved; the human smoke above exercised existing injection, not `CLEAN_TAIL_CHECK`.

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
- First Phase 2B increment: synthetic nested track trees cover all explicit tracks/languages, independent default/override resolution, shared resources, missing/malformed resources, invalid/unpaired arguments, source mismatches, Windows junction escapes, lint-only style independence/no-vault access, dry-run redaction/no-private reads/no writes, both entrypoints, mocked single/matrix prompts and outputs, unchanged version-1 schema/filenames, and source hashes/BOM/CRLF. Existing no-track/English/arena regressions remain applicable.
- Remaining Phase 2B continuity-tail tests require a separately approved scope before implementation. Automatic track inference is excluded. No test result certifies semantic Tier 1-2 safety or literary quality.

### Perf / Security Notes

- The approved and implemented shared three-request concurrency cap is not a guarantee of per-key rate-limit compliance. Raising it requires separate approval and validation.
- Three models with three candidates each mean nine initial requests and at most 27 attempts per invocation. 45-second per-request timeouts and bounded retries do not guarantee total run latency or a dollar budget. Publication conflicts are still checked after generation, so repeated human live requests can incur charges before reports are blocked.
- Assistants never execute live generation or inspect private vaults, credentials, addons, or real upstream prose. Human live comparisons transmit assembled prompts to OpenRouter and may incur charges; storage isolation is not a network air gap.

<!-- PHASE_2_END -->

&nbsp;

---

<!-- PHASE_3_START -->

&nbsp;

## 6\. Phase 3: Configuration-Driven CLI (Increment A) & Deferred Human-Run Launcher

### Action

Deliver explicit, non-secret run defaults through the existing shared CLI. Keep the optional thin PowerShell launcher and localhost picker deferred rather than introduce another generation pipeline.

### Status and Approval Boundary

- **Increment A explicitly approved and implemented locally on 2026-11-11.** Approval covers the TOML loader, shared `--config` interface, synthetic offline tests, and directly related documentation only. At that stage, this was an unpublished working-tree implementation, not Git publication or live acceptance.
- The human approved vault precedence `CLI > ZAFO_VAULT_DIR > TOML > legacy fallback` and effective track/root pairing after merging, including mixed CLI/TOML origins. Launcher implementation was explicitly deferred.
- That implementation approval did not authorize real-vault creation or inspection, migration, Git publication, prompt transmission, or paid generation. Assistants remain limited to benign synthetic C: test vaults and mocked HTTP.
- **Scoped Git publication separately approved on 2026-11-12.** Approval covers the six Phase 3A configuration, test and documentation files through a feature branch, scoped commit, push, PR review/checks, merge and return to `main`. The pre-existing ignore-file edit was excluded and remained local at that stage; its subsequent rollback was verified during the CI-gate work below. This changes only the Git publication boundary, not the restrictions on real-vault access, prompt transmission, live generation or deferred features.
- The proposed per-user layout below remains uncreated, uninspected, and unvalidated by the assistant. It is not a new CLI default or automatic discovery rule. The human must privately confirm genuinely unsynchronized, nonredirected storage; neither the path string nor `LOCALAPPDATA` proves that property.

### Configuration and Storage Contract

```text
%LOCALAPPDATA%\WritingInjector\
    settings.toml        Non-secret run defaults, outside the vault
    vault\
        .env             Credentials
        TIER4_ADDON.txt   Private addon
        output\          Generated reports and drafts
```

- A human must select genuinely unsynchronized, nonredirected storage outside the workspace. The whole D: drive remains forbidden for vaults and generated output, including resolved links. An environment-derived example path is not a storage-validation exemption.
- Keep credentials in the selected external vault's `.env`, or the existing process environment; do not introduce a credential-bearing repository `.env`. The credential file is not a general run-settings source.
- The optional UTF-8 `.toml` file contains only allowlisted, typed defaults corresponding to existing non-secret CLI settings. It must not contain credentials, addon contents, prompt text, source prose, or draft prose. The README contains only a benign synthetic example, not personal runtime configuration.
- Keep TOML outside the vault so offline commands can read non-secret settings without opening credentials or addons. Operation modes, `--strict`, permission for paid generation, and `--print-output` remain command-line concerns, not persisted settings. The existing direct CLI generation default is unchanged.
- Original writing remains separate from the application vault and read-only during injection. No bulk move or automatic migration is required or permitted by this proposal. Generated reports and drafts belong exclusively in the validated selected vault's `output` directory.

### Implemented Increment A

1. Both entrypoints accept explicit `--config FILE`, implemented with standard-library `tomllib` in [settings.py](../src/zafo_injector/settings.py) and merged once in [cli.py](../src/zafo_injector/cli.py). No automatic discovery, settings environment variable, includes, file creation, or dependency changes were introduced.
2. The flat allowlist is `language` (`sk|en` string), `candidates` (integer >=1), `model` (nonblank legacy single-model ID string), `models` (array of 2-3 distinct registered full ID strings, trimming surrounding whitespace), `temp` (finite number 0-2 inclusive), `min_p` (finite number 0-1 inclusive), `track` (`blog|serial|dark-romance` string), and nonblank path strings `tracks_root`, `style_sheet`, `lexicon`, `vault_dir`. Booleans are not numbers. Unknown fields/tables, duplicate TOML keys, wrong types, invalid scalar domains, or both model selectors reject even if overridden. Empty TOML retains existing defaults.
3. Ordinary precedence is explicit CLI > TOML > existing fallback, including CLI values equal to legacy defaults. Vault precedence is explicit `--vault-dir` > existing `ZAFO_VAULT_DIR` > TOML `vault_dir` > existing home fallback. Empty-but-present vault environment values retain their legacy handling rather than falling through to TOML. Nonempty process `OPENROUTER_API_KEY` still overrides the selected vault `.env`, without mutating the environment.
4. CLI `--model` or `--models` replaces the whole configured selector group. Both explicit CLI selectors still reject before settings access, including the exact legacy-default model object. Argparse's `--model` default remains `None` and legacy resolution stays deferred. Configured sampling counts as an override; effective matrix support/budgets, paired tracks, English lexicon rejection and matrix lint-only rejection are validated after merging.
5. Relative `--config` and existing CLI paths use the invocation's working directory. Relative TOML paths use the selected settings file's normalized absolute pathname directory, not a linked file target's directory. TOML paths expand `~`, not `%VARIABLE%` or `$VARIABLE`; Windows drive-relative/root-relative partial paths and null characters reject. Parsing never resolves, stats, or inspects a configured vault.
6. Help reads no settings/sources/vault, including with a missing settings file. Dry-run reads settings and consumed source resources and validates vault paths, but reads no credentials/addons, calls no HTTP and writes nothing. Lint-only retains no vault access and neither reads nor requires styles, even when configured. Settings cannot choose operation modes, source frames, output destinations, prose printing, paid permissions, or provider/request/retry controls.
7. Missing/unreadable settings, invalid UTF-8/TOML, unsupported fields/types and invalid effective combinations exit 2 with redacted diagnostics and no fallback into generation. Existing storage 3, HTTP 4 and strict 5 exits remain unchanged.
8. No-configuration compatibility is retained: prompts, model profiles, sampling defaults, QA bounds/scoring, strict exits, request/retry/concurrency limits, report schemas, filenames, source immutability and no-overwrite/publication behavior are unchanged. No launcher, bootstrap, vault-loader, HTTP-client, renderer or QA implementation changes are included.

### Accessibility (CLI)

- Preserve plain UTF-8, metadata-only diagnostics, stable exit codes, and `NO_COLOR` behavior. Configuration failures must be explicit and redacted; do not echo settings contents, credentials, or prose, or fall back into generation after an error.

### Offline Validation (2026-11-11)

- A focused contract test first failed on the unsupported `--config` flag before implementation.
- The combined targeted manual gate passed **655 tests in 108.20 seconds**: settings contracts, both CLI entrypoints, vault configuration, tracks, renderer/publication, English QA, arena behavior/client limits, model profiles and Slovak lint. This was not a full-suite or hosted-CI run.
- After strengthening populated-TOML matrix payload/report equivalence against equivalent CLI runs, the final settings-only confirmation passed **82 tests in 4.08 seconds**. This overlaps the combined gate; counts must not be added.
- Tests cover malformed/unknown/forbidden settings, exact types and sampling boundaries, redacted parser/file failures, explicit-default overrides, whole-selector replacement, effective combinations and mixed-origin tracks, environment/credential precedence, relative/home/literal-variable paths, and source/report byte equivalence. Help/dry-run preserve no credential/addon reads, HTTP or writes; lint-only blocks configured-vault resolution/stat/loading and ignores styles.
- Ruff lint/format checks passed for all four changed Python files; strict mypy passed for all **13** source files. Final syntax parsing passed for all four changed Python files without bytecode writes.
- All temporary test storage, `TEMP`/`TMP`, synthetic vaults and type caches used fresh validated assistant-owned C: storage; bytecode and pytest/linter caches were disabled. Existing storage/link, source hash/BOM/CRLF, strict/scoring, no-overwrite and publication rollback regressions passed. Generation tests used mocked HTTP; no live generation, private-vault access, dependency installation or Git publication occurred.
- Offline checks establish neither prose quality nor paid-provider/production acceptance. A launcher generation-dispatch test is not part of this increment because no launcher was implemented.

### Bounded Offline Hardening (2026-11-12)

- Scoped local metadata matched `main` at `16ac0be9e8c888e2378546be03d2911839cf94b2` (the PR #7 merge baseline). Existing tracked edits and both untracked Phase 3A Python files were included and preserved; the earlier ignore-file and documentation changes were not reverted. Nothing was staged or published.
- On CPython **3.12.4**, a real synthetic TOML file containing **2,000 nested arrays** reproduced an uncaught `RecursionError`, despite a valid explicit CLI `--model` override. The smallest new regression failed before the correction (**1 failed in 0.21 seconds**) and passed afterward (**1 passed in 0.20 seconds**).
- The only production correction adds `RecursionError` alongside `ValueError` at the TOML-loading boundary. It raises the existing generic, redacted `ConfigurationError` with `from None`; no CLI merge, path-normalization, vault, HTTP, renderer, dependency or QA behavior was changed.
- Parser coverage blocks source-resource selection/reads, vault loading, HTTP construction and both renderers before rejection. Four additional subprocess variants (module/console, Slovak/English) verify actual exit **2**, no traceback or settings sentinel disclosure, unchanged sources and no output, including with the explicit selector override.
- The linked-settings regression successfully created an assistant-owned **C: Windows junction**. Distinct valid styles beside the selected pathname and linked target prove, through the actual mocked request's assembled messages, that relative resources use the normalized selected-pathname directory. The junction was removed in `finally`; this contract was exercised, not skipped.
- The existing dry-run test now guards actual `builtins.open`, `io.open` and `os.open` calls for the synthetic vault's `.env` and `TIER4_ADDON.txt`, including binary opens, while permitting settings/source reads. Existing no-HTTP, no-render, no-output and source-hash assertions remain; lint-only vault/style isolation remains intact.
- The fresh combined settings/subprocess gate passed **280 tests in 75.72 seconds, with no skips**. This includes the smallest regression; neither preliminary results nor the historical **655** and overlapping **82** test runs above are added to this count. No full-suite or hosted-CI run was performed.
- Final no-cache Ruff lint and format checks passed for all four Phase 3A Python files. The initial format check requested two new test-hunk formatting changes, which Ruff applied. Existing strict mypy passed for all **13** source files. Pylance syntax calls were unavailable because the service timed out; protected local `ast.parse` validation with Python 3.12 grammar passed for the same four files instead.
- Before Python execution, bytecode and pytest/linter caches were disabled; `TEMP`, `TMP`, pytest base directories and the mypy cache used fresh, nonredirected, assistant-owned C: storage that passed the existing storage validator. Subprocesses inherited these protections. All four identified test/cache subdirectories, their empty task root and the scoped-diff tool scratch file were removed, with absence verified and without following links.
- This evidence covers CPython 3.12.4 and the Windows junction case, not every supported interpreter/link variant or live provider behavior. No dependencies were installed/upgraded, no real vault or personal settings were inspected, and no live request, launcher work or Git publication occurred.

The exact targeted runner/check commands were as follows. `$root` denotes the fresh validated C: task directory, now removed. These processes used `PYTHONDONTWRITEBYTECODE=1`, `RUFF_NO_CACHE=1`, `TEMP=$root`, `TMP=$root`, and `MYPY_CACHE_DIR=$root\mypy-cache`; pytest runners also used `PYTEST_ADDOPTS=-p no:cacheprovider`. Runtime, pytest and mypy wrappers removed private vault/key/cloud environment overrides from their process without reading the values.

```powershell
# Before the correction: expected failure; after the correction: pass.
.\.venv\Scripts\python.exe -B -m pytest -q --tb=line -p no:cacheprovider --basetemp "$root\pytest-repro" tests\unit\test_settings.py::test_recursive_settings_reject_before_consumption_even_with_cli_selector_override
.\.venv\Scripts\python.exe -B -m pytest -q --tb=line -p no:cacheprovider --basetemp "$root\pytest-fixed" tests\unit\test_settings.py::test_recursive_settings_reject_before_consumption_even_with_cli_selector_override
.\.venv\Scripts\python.exe -B -m pytest -q -rs --tb=short -p no:cacheprovider --basetemp "$root\pytest-targeted" tests\unit\test_settings.py tests\unit\test_cli_subprocess.py
.\.venv\Scripts\ruff.exe format --no-cache tests\unit\test_settings.py tests\unit\test_cli_subprocess.py
.\.venv\Scripts\ruff.exe check --no-cache src\zafo_injector\settings.py src\zafo_injector\cli.py tests\unit\test_settings.py tests\unit\test_cli_subprocess.py
.\.venv\Scripts\ruff.exe format --check --no-cache src\zafo_injector\settings.py src\zafo_injector\cli.py tests\unit\test_settings.py tests\unit\test_cli_subprocess.py
.\.venv\Scripts\python.exe -B -m mypy --strict --cache-dir "$root\mypy-cache" src
$code = @'
import ast
from pathlib import Path

paths = (
    Path(r"src\zafo_injector\settings.py"),
    Path(r"src\zafo_injector\cli.py"),
    Path(r"tests\unit\test_settings.py"),
    Path(r"tests\unit\test_cli_subprocess.py"),
)
for path in paths:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 12))
print("AST syntax validation passed for all four Phase 3A Python files.")
'@
.\.venv\Scripts\python.exe -B -c $code
```

### Bounded Windows Offline CI Gate (2026-11-12; Local, Unpublished)

- Baseline verification found a clean `main`, with local HEAD, `origin/main`, and GitHub `main` all at `cba3012ff7999ef9f32b3464633da3b4d22db458`. PR #8 was merged with exactly the six approved Phase 3A files; GitHub reported zero workflows. The reported subsequent ignore-file rollback was verified: no staged or unstaged ignore-file change existed, and none was reinstated.
- Implementation approval covered one [workflow](../.github/workflows/windows-offline.yml), directly related README/project-sheet updates, offline validation and the new local branch `ci/bounded-windows-offline-gate`. It did not authorize staging, committing, pushing, PR creation, hosted workflow execution, production-code changes, dependency upgrades or launcher work. Nothing was staged or published.
- The workflow uses GitHub-hosted `windows-2022`, Python 3.12, pull requests and pushes to `main`, `contents: read`, and a ten-minute timeout. Its single pytest invocation combines settings/subprocess coverage and rejects unexpected skips without hard-coding a test count. Ruff lint/format checks cover only the four Phase 3A Python files; existing strict mypy checks `src`. There is no full-suite/version matrix, `pull_request_target`, application-secret use or artifact upload.
- **Narrow platform exception explicitly approved before implementation:** GitHub-managed checkout/action/runtime/control infrastructure may use D:, including inline scripts and runner environment files. GitHub documents non-static runner paths; its runner writes inline scripts before executing project steps. `RUNNER_TEMP` is not assumed to be on C:. This exception includes action-managed Python runtime bootstrap, not project build/install/test/cache storage, and does not change application storage validation. See [GitHub runner filesystems](https://docs.github.com/en/actions/reference/runners/github-hosted-runners#file-systems) and [runner script handling](https://github.com/actions/runner/blob/main/src/Runner.Worker/Handlers/ScriptHandler.cs).
- Preparation creates an unredirected GUID-named C: root and exports committed public `HEAD` with `git archive`; ignored/local/private content is never recursively copied. Builds and egg-info stay in the C: source copy. A separate C: test area passes the existing `validate_storage_path` check before project installation or tests. The selected CI interpreter must be on C: and version 3.12. Declared `.[dev]` dependencies install into that test area's disposable virtual environment, placing the real console executable beside its Python executable.
- Before interpreter setup, PowerShell guards against redirected storage ancestors and exports C: `TEMP`, `TMP`, `TMPDIR`, bytecode/cache locations and a disabled pip configuration. Bytecode writes and pytest/Ruff caches are disabled. The project step removes credential/vault/cloud overrides without printing values; subprocesses inherit the protections. Existing synthetic Tier-1 fixtures, mocked HTTP, offline-mode guards, source hashes/BOM/CRLF and junction assertions are unchanged.
- Fresh local validation used the committed public C: source export and a separate validated C: test area. The existing read-only local virtual environment supplied CPython **3.12.4**, pytest **9.2.0**, Ruff **0.17.3** and mypy **2.4.1**; nothing was installed or upgraded locally. Pytest collected **280** tests and passed **280 in 184.00 seconds, with no skips**. Both module/console entrypoints and the Windows junction regression were exercised. Ruff lint and format passed for all four selected files; strict mypy passed for all **13** source files. These counts are fresh observations, not required constants or additions to historical results.
- PowerShell **7.6.10** parsed both inline workflow blocks successfully. Local trigger/permission/scope assertions passed; an initial CRLF-sensitive assertion was corrected in the temporary validation harness without changing the workflow. The exact preparation block and exact Python storage preflight also executed successfully. Pylance reported no syntax errors for the storage snippet, and VS Code reported no workflow diagnostics. No standalone YAML/Actions validator was available in the existing environment; none was installed. These checks do not establish full hosted Actions validation.
- **Hosted CI remains unverified.** No workflow was triggered. Action resolution, runner-managed D: infrastructure, hosted Python provisioning and clean dependency/virtual-environment installation were not exercised locally. The local console tests used the existing installed entrypoint; the new hosted installation path still requires an observed hosted run after separate publication approval.
- Both specifically identified assistant-owned C: roots, their public source archives/copies, synthetic test vaults/outputs, type cache and temporary runner-environment file were removed, with absence verified. Cleanup removed links as links without descending into them. Original source/configuration/test files, dependencies and the ignore file remained unchanged. No real vault or personal application settings were inspected, and no live generation occurred.

The targeted local commands below ran from the committed C: source export. `$root` denotes the now-removed local task root; `$area` was its separately validated `test-area`. All Python processes used `PYTHONDONTWRITEBYTECODE=1`, `PYTHONIOENCODING=utf-8`, `TEMP=$area`, `TMP=$area`, `TMPDIR=$area`, `PYTHONPYCACHEPREFIX=$area\bytecode`, `PYTEST_ADDOPTS=-p no:cacheprovider`, `RUFF_NO_CACHE=1`, `NO_COLOR=1` and `MYPY_CACHE_DIR=$area\mypy-cache`. Wrappers removed `OPENROUTER_API_KEY`, `ZAFO_VAULT_DIR`, `GOOGLE_DRIVE_DIR`, `PYTHONPATH`, `PYTHONHOME` and `PYTEST_PLUGINS` from their own environments without printing values.

```powershell
$python = 'D:\zafo-injector\.venv\Scripts\python.exe'
$area = Join-Path $root 'test-area'
Set-Location -LiteralPath (Join-Path $root 'source')
$files = @(
    'src\zafo_injector\settings.py',
    'src\zafo_injector\cli.py',
    'tests\unit\test_settings.py',
    'tests\unit\test_cli_subprocess.py'
)
& $python -B -m pytest -rs --tb=short -p no:cacheprovider --basetemp "$area\pytest" tests\unit\test_settings.py tests\unit\test_cli_subprocess.py |
    Tee-Object -Variable pytestOutput
if ($LASTEXITCODE -ne 0) { throw 'Targeted offline tests failed.' }
if ($pytestOutput -match '\bskipped\b') { throw 'Unexpected skipped coverage in the Windows gate.' }
& $python -B -m ruff check --no-cache @files
& $python -B -m ruff format --check --no-cache @files
& $python -B -m mypy --strict --cache-dir $env:MYPY_CACHE_DIR src
```

### Perf / Security Notes

- No assistant access to real vaults, credentials, addons, reports, candidates, or upstream prose, including any vault override. No automatic setup, file moves, deletion, or cleanup of human evidence.
- Storage isolation is not a network air gap. A separately approved human live invocation sends assembled prompt content to OpenRouter; configuration or a launcher does not add a dollar cap or change existing retry/cost exposure.

### Deferred Work

- The optional thin `writing-injector.ps1` launcher requires separate implementation approval. The planning interface is bare help, otherwise injected dry-run, with only explicit human `-Generate -CliArgs <string[]>` permitting generation dispatch and explicitly forwarded `--print-output` permitting prose printing. Settings cannot enable either action. A future launcher must forward token arrays without expression evaluation, preserve caller-relative paths and child exit codes, and test paid-dispatch branches only with a fake executable. No human paid invocation is approved by this planning interface.
- The localhost candidate picker and inline diff/editor remain a later optional backlog, not part of this configuration increment. No `--serve` implementation is approved.
- If revisited, retain loopback-only `127.0.0.1` binding, an ephemeral port, CSRF protection, non-loopback `Host` rejection, no external assets/telemetry, keyboard-accessible semantic candidate selection and annotations, and accessible save confirmations. Edited exports must use the validated selected vault's `output`, not a hard-coded home path.
- Continuity-tail work and automatic translation remain unapproved. The human workflow remains English drafting followed by manual Slovak translation and editing; this proposal does not authorize more paid Slovak smokes.

<!-- PHASE_3_END -->