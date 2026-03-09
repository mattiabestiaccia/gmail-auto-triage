---
phase: 02-classification
plan: 03
subsystem: cli-pipeline
tags: [cli, dry-run, pipeline-integration, rate-limiting, idempotency]
requirements_completed:
  - OPS-06
---

## What Was Built

Wired classification engine (02-01) and label management (02-02) into the CLI pipeline with `--dry-run` flag and end-of-run classification summary.

## Key Decisions

- `--dry-run` performs real LLM classification but skips `apply_labels()` — user sees what would happen without side effects
- 4-second delay between LLM calls to respect Gemini Flash free tier ~15 RPM limit
- Per-email error handling: one failure doesn't crash the batch, error is logged and processing continues
- Idempotency filter runs before GenAI client init, saving LLM calls on already-triaged emails
- Summary always shown (both dry-run and real mode)

## Changes

### Modified
- `src/email_triage/cli.py` — Full classify+label pipeline: fetch → idempotency filter → classify with delay → label (or skip if dry-run) → summary
- `src/email_triage/output.py` — Added `print_classification_summary()` and `print_classification_result()` functions

## Self-Check: PASSED

- [x] `--dry-run` flag in `--help` output
- [x] 75 tests pass (no regression)
- [x] CLI imports from classifier.py and labels.py
- [x] `is_already_triaged` check before `classify_email` call
- [x] `time.sleep(4)` between LLM calls
- [x] Per-email try/except with error count
- [x] `print_classification_summary` called at end of run

## key-files

### modified
- src/email_triage/cli.py
- src/email_triage/output.py
