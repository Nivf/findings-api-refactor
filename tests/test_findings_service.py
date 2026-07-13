import pytest

from service.findings_service import (
    FindingsQuery,
    FindingsService,
    InvalidFindingsQueryError,
    InvalidStatusUpdateRequestError,
    UpdateStatusRequest,
)
from store.findings_store import (
    FindingNotFoundError,
    FindingsPage,
    FindingsStore,
    FindingsTransaction,
    FindingSummary,
)


class FakeFinding:
    def __init__(self, finding_id, status):
        self.finding_id = finding_id
        self.status = status

    def clone(self):
        return FakeFinding(self.finding_id, self.status)


class FakeFindingsTransaction(FindingsTransaction):
    """In-memory stand-in for _SqlAlchemyFindingsTransaction: stages
    clones of committed findings, and only promotes them on a clean exit --
    same all-or-nothing contract as the real one."""

    def __init__(self, store):
        self._store = store
        self._pending = None

    def __enter__(self):
        self._pending = {fid: f.clone() for fid, f in self._store.committed.items()}
        return self

    def get_finding(self, finding_id):
        finding = self._pending.get(finding_id)
        if finding is None:
            raise FindingNotFoundError(finding_id)
        return finding

    def save_finding(self, finding) -> None:
        self._pending[finding.finding_id] = finding

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._store.committed = self._pending
        self._pending = None
        return False


class FakeFindingsStore(FindingsStore):
    """Proves the DI payoff: FindingsService is testable with zero DB."""

    def __init__(self, page: FindingsPage = None, findings=None):
        self.page = page
        self.committed = {f.finding_id: f for f in (findings or [])}
        self.last_call = None

    def get_findings(self, cutoff_time, algorithm_type, min_findings, exclude_statuses, offset, limit):
        self.last_call = dict(
            cutoff_time=cutoff_time,
            algorithm_type=algorithm_type,
            min_findings=min_findings,
            exclude_statuses=exclude_statuses,
            offset=offset,
            limit=limit,
        )
        return self.page

    def begin_transaction(self) -> FindingsTransaction:
        return FakeFindingsTransaction(self)


def make_summary(finding_id="f1", status="pending"):
    return FindingSummary(
        prediction_id=finding_id,
        accession_number="a1",
        patient_name="Jane Doe",
        patient_age=40,
        patient_gender="F",
        algorithm_type="ich",
        num_findings=2,
        status=status,
        creation_date="2026-01-01T00:00:00",
        study_date="2026-01-01T00:00:00",
    )


def test_excludes_completed_by_default():
    store = FakeFindingsStore(FindingsPage(items=[make_summary()], total_count=1))
    service = FindingsService(store)

    service.get_findings(FindingsQuery())

    assert store.last_call["exclude_statuses"] == ["completed"]


def test_pagination_maps_to_offset_and_limit():
    store = FakeFindingsStore(FindingsPage(items=[], total_count=0))
    service = FindingsService(store)

    service.get_findings(FindingsQuery(page=3, page_size=20))

    assert store.last_call["offset"] == 40
    assert store.last_call["limit"] == 20


def test_result_reports_true_total_not_just_page_length():
    store = FakeFindingsStore(FindingsPage(items=[make_summary()], total_count=137))
    service = FindingsService(store)

    result = service.get_findings(FindingsQuery(page=1, page_size=1))

    assert len(result.findings) == 1
    assert result.total_count == 137


@pytest.mark.parametrize(
    "kwargs",
    [
        {"delta_time_hours": 0},
        {"delta_time_hours": -5},
        {"min_findings": -1},
        {"page": 0},
        {"page_size": 0},
        {"page_size": 9999},
    ],
)
def test_rejects_invalid_query_params(kwargs):
    with pytest.raises(InvalidFindingsQueryError):
        FindingsQuery(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"finding_ids": [], "new_status": "completed"},
        {"finding_ids": None, "new_status": "completed"},
        {"finding_ids": "f1", "new_status": "completed"},  # a string, not a list
        {"finding_ids": ["f1"], "new_status": "not-a-real-status"},
    ],
)
def test_rejects_invalid_update_status_request(kwargs):
    with pytest.raises(InvalidStatusUpdateRequestError):
        UpdateStatusRequest(**kwargs)


def test_update_statuses_happy_path():
    store = FakeFindingsStore(findings=[FakeFinding("f1", "pending"), FakeFinding("f2", "pending")])
    service = FindingsService(store)

    result = service.update_statuses(UpdateStatusRequest(["f1", "f2"], "completed"))

    assert result.updated == ["f1", "f2"]
    assert result.failed == []
    assert store.committed["f1"].status == "completed"
    assert store.committed["f2"].status == "completed"


def test_update_statuses_is_all_or_nothing_on_invalid_transition():
    store = FakeFindingsStore(
        findings=[FakeFinding("f1", "pending"), FakeFinding("f2", "completed")]
    )
    service = FindingsService(store)

    result = service.update_statuses(UpdateStatusRequest(["f1", "f2"], "in_review"))

    assert result.updated == []
    assert result.failed == ["f1", "f2"]
    # f1 must NOT be committed even though it was valid on its own --
    # the whole batch rolled back because f2 failed.
    assert store.committed["f1"].status == "pending"
    assert store.committed["f2"].status == "completed"


def test_update_statuses_rolls_back_on_missing_finding():
    store = FakeFindingsStore(findings=[FakeFinding("f1", "pending")])
    service = FindingsService(store)

    result = service.update_statuses(UpdateStatusRequest(["f1", "does-not-exist"], "completed"))

    assert result.updated == []
    assert result.failed == ["f1", "does-not-exist"]
    assert store.committed["f1"].status == "pending"


def test_completed_finding_can_be_re_completed():
    # Boundary case: COMPLETED -> COMPLETED is a no-op transition, not
    # blocked by the same rule that blocks COMPLETED -> anything else.
    store = FakeFindingsStore(findings=[FakeFinding("f1", "completed")])
    service = FindingsService(store)

    result = service.update_statuses(UpdateStatusRequest(["f1"], "completed"))

    assert result.updated == ["f1"]
    assert result.failed == []
