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
- Added `PATCH /api/findings` to update a batch of findings' status,
  wrapped in a single all-or-nothing transaction (SQLAlchemy's
  `Session.begin()`) -- if any finding in the batch is missing or fails
  the status-transition rule, nothing in the batch is committed.

## Endpoints

- `GET /api/findings?delta_time=24&algorithm_type=ich&min_findings=1&page=1&page_size=50`
- `PATCH /api/findings` — partial update to a batch of existing findings.
  Body: `{"finding_ids": ["f1", "f2"], "status": "completed"}`

## Run

```
pip install -r requirements.txt
pytest
```

## Structure

- `app.py` — Flask routes; delegates parsing to `FindingsRequestParser` and
  work to `FindingsService`, both injected via `create_app(...)`.
- `request_parser.py` — turns raw HTTP request data into validated
  request objects, independent of Flask (testable without a test client).
- `service/findings_service.py` — orchestration, request/response DTOs.
- `store/findings_store.py` — persistence interface + SQLAlchemy
  implementation.
- `database/` — SQLAlchemy models and session setup.
- `tests/` — unit tests against a fake store and a fake request (no DB,
  no Flask app needed).
