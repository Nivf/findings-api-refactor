import pytest

from service.findings_service import FindingsQuery, FindingsService, InvalidFindingsQueryError
from store.findings_store import FindingsPage, FindingsStore, FindingSummary


class FakeFindingsStore(FindingsStore):
    """Proves the DI payoff: FindingsService is testable with zero DB."""

    def __init__(self, page: FindingsPage):
        self.page = page
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
