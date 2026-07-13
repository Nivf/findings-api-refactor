import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from database.models import FindingStatus
from store.findings_store import FindingNotFoundError, FindingsStore

logger = logging.getLogger(__name__)


class InvalidFindingsQueryError(ValueError):
    """Raised on bad input -- lets the API layer return 400, not 500."""


class InvalidFindingStatusTransitionError(ValueError):
    pass


class InvalidStatusUpdateRequestError(ValueError):
    """Raised on bad input -- lets the API layer return 400, not 500."""


DEFAULT_DELTA_HOURS = 24
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200  # prevents an unbounded/huge page from being requested


@dataclass
class FindingsQuery:
    """Request parameters, validated on construction."""

    delta_time_hours: int = DEFAULT_DELTA_HOURS
    algorithm_type: Optional[str] = None
    min_findings: Optional[int] = None
    exclude_statuses: Optional[List[str]] = None  # defaults to [COMPLETED] below
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE

    def __post_init__(self):
        if self.exclude_statuses is None:
            self.exclude_statuses = [FindingStatus.COMPLETED.value]

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
    """Response returned to the API layer."""

    findings: list
    total_count: int
    page: int
    page_size: int


@dataclass
class UpdateStatusRequest:
    """Request parameters for a batch status update, validated on
    construction -- same pattern as FindingsQuery."""

    finding_ids: List[str]
    new_status: str

    def __post_init__(self):
        if not isinstance(self.finding_ids, list) or not self.finding_ids:
            raise InvalidStatusUpdateRequestError("finding_ids must be a non-empty list")
        if self.new_status not in {s.value for s in FindingStatus}:
            valid = sorted(s.value for s in FindingStatus)
            raise InvalidStatusUpdateRequestError(f"status must be one of {valid}")


@dataclass
class UpdateStatusResult:
    updated: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)


def validate_finding_status_transition(current_status: str, new_status: str) -> None:
    if current_status == FindingStatus.COMPLETED.value and new_status != FindingStatus.COMPLETED.value:
        raise InvalidFindingStatusTransitionError(
            f"Cannot change status of a completed finding to '{new_status}'"
        )


class FindingsService:
    def __init__(self, findings_store: FindingsStore):
        self._findings_store = findings_store

    def get_findings(self, query: FindingsQuery) -> FindingsResult:
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=query.delta_time_hours)

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

    def update_statuses(self, request: UpdateStatusRequest) -> UpdateStatusResult:
        """Updates a batch of findings to `request.new_status`. All-or-
        nothing: if any finding is missing or fails the transition rule,
        nothing in the batch is committed."""
        try:
            with self._findings_store.begin_transaction() as tx:
                for finding_id in request.finding_ids:
                    finding = tx.get_finding(finding_id)
                    validate_finding_status_transition(finding.status, request.new_status)
                    finding.status = request.new_status
                    tx.save_finding(finding)
        except (FindingNotFoundError, InvalidFindingStatusTransitionError) as exc:
            logger.warning(
                "rolled back status update to %r for finding_ids=%s: %s: %s",
                request.new_status, request.finding_ids, type(exc).__name__, exc,
            )
            return UpdateStatusResult(updated=[], failed=request.finding_ids)

        return UpdateStatusResult(updated=request.finding_ids, failed=[])
