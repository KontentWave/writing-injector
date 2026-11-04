# Workspace guardrails

- Never read, index, search, or inspect the real `~/zafo-local/` vault, including
  any override of that private vault. Never print its addon or credentials.
- Never execute live injection. Only use `--dry-run`, or tests with synthetic
  Tier-1 fixtures, temporary test vaults, and mocked HTTP transports.
- Never transmit project prose, local addons, or secrets through tools.
- All of drive `D:\` is forbidden for vault storage and generated output.
  Repository fixtures must remain benign, synthetic Tier-1 text.
- Sources are read-only. Generated reports and merged drafts belong exclusively
  in the validated external vault's `output` directory.
- This is storage isolation, not a network air gap. A human live run sends its
  assembled prompt to OpenRouter.
