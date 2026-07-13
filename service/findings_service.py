from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from database.models import FindingStatus
from store.findings_store import FindingsStore


class InvalidFindingsQueryError(ValueError):
    """Raised on bad input -- lets the API layer return 400, not 500."""


DEFAULT_DELTA_HOURS = 24
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200  # prevents an unbounded/huge page from being requested


@dataclass
class FindingsQuery:
    """Request data model ("3. DataModel req" comment) -- validates itself
    instead of leaving validation scattered across the route and service."""

    delta_time_hours: int = DEFAULT_DELTA_HOURS
    algorithm_type: Optional[str] = None
    min_findings: Optional[int] = None
    exclude_statuses: List[str] = None  # defaults to [COMPLETED] below
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE

    def __post_init__(self):
        if self.exclude_statuses is None:
            self.exclude_statuses = [FindingStatus.COMPLETED.value]

        # "2. validate input" -- previously any bad value either silently
        # fell back to a default (see the delta_time bug noted in app.py)
        # or blew up as an unhandled 500 deep inside the store.
        if self.delta_time_hours <= 0:
            raise InvalidFindingsQueryError("delta_time must be a positive number of hours")
        if self.min_findings is not None and self.min_findings < 0:
            raise InvalidFindingsQueryError("min_findings cannot be negative")
        if self.page < 1:
            raise InvalidFindingsQueryError("page must be >= 1")
        if not (1 <= self.page_size <= MAX_PAGE_SIZE):
            raise InvalidFindingsQueryError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")


@dataclass
class FindingsResult:
    """Response data model ("res data model" comment)."""

    findings: list
    total_count: int
    page: int
    page_size: int


class FindingsService:
    def __init__(self, findings_store: FindingsStore):
        # Dependency Inversion: takes the FindingsStore interface, not a
        # concrete SqlAlchemyFindingsStore, and doesn't construct it itself
        # -- same fat-constructor/no-DI fix as ScanReportService. This is
        # what makes the "exclude completed findings by default" business
        # rule testable with a fake store, no DB required.
        self._findings_store = findings_store

    def get_findings(self, query: FindingsQuery) -> FindingsResult:
        cutoff_time = datetime.utcnow() - timedelta(hours=query.delta_time_hours)

        page = self._findings_store.get_findings(
            cutoff_time=cutoff_time,
            algorithm_type=query.algorithm_type,
            min_findings=query.min_findings,
            exclude_statuses=query.exclude_statuses,
            offset=(query.page - 1) * query.page_size,
            limit=query.page_size,
        )

        return FindingsResult(
            findings=page.items,
            total_count=page.total_count,
            page=query.page,
            page_size=query.page_size,
        )
