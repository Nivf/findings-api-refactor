# Findings API refactor

A Flask + SQLAlchemy findings-lookup endpoint, refactored from a legacy
version for readability, testability, and correctness. Refactor highlights:

- Fixed an N+1 query bug in the store (single SQL join instead of one query
  per related row).
- Added pagination (`page`/`page_size`), with a true `total_count` across
  the filtered set.
- Added input validation (`FindingsQuery`) so bad request params return a
  400 instead of a 500 or silently-wrong behavior.
- Dependency-injected `FindingsStore` interface into `FindingsService`
  (constructor injection, testable with an in-memory fake, no DB required).
- Flask app factory (`create_app`) instead of a module-level app built at
  import time.
- Type-safe `FindingStatus` enum instead of magic status strings.

## Run

```
pip install -r requirements.txt
pytest
```

## Structure

- `app.py` — Flask route + request parsing/validation.
- `service/findings_service.py` — orchestration, request/response DTOs.
- `store/findings_store.py` — persistence interface + SQLAlchemy
  implementation.
- `database/` — SQLAlchemy models and session setup.
- `tests/` — unit tests against a fake store (no DB needed).
