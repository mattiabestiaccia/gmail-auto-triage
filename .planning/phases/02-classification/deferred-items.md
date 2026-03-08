# Deferred Items - Phase 02: Classification

## Pre-existing Issues

### 1. test_classifier.py import error
- **Found during:** 02-02 execution (full test suite run)
- **Issue:** `tests/test_classifier.py` imports `email_triage.classifier` which doesn't exist yet (part of plan 02-01)
- **Impact:** Full `pytest` run fails with collection error; individual test files work fine
- **Resolution:** Will resolve when plan 02-01 creates `classifier.py`
