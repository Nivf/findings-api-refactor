from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, List, Optional

from database.models import FindingDBModel, PatientDBModel, StudyDBModel


@dataclass
class FindingSummary:
    """Response shape for one finding -- replaces the raw dict literal
    ("Add to Data Model" comment)."""

    prediction_id: str
    accession_number: str
    patient_name: str
    patient_age: Optional[int]
    patient_gender: Optional[str]
    algorithm_type: str
    num_findings: int
    status: str
    creation_date: str
    study_date: str


@dataclass
class FindingsPage:
    """A page of results plus the TRUE total across all pages -- not just
    len(this page), which is what the original `total_count` actually
    measured once pagination exists."""

    items: List[FindingSummary]
    total_count: int


# Dependency Inversion Principle (DIP): FindingsService depends on this
# interface, not on SqlAlchemyFindingsStore directly -- same pattern as
# ReportRepository in the ScanReportService exercise. Lets the service be
# unit-tested with an in-memory fake, no real DB needed.
class FindingsStore(ABC):
    @abstractmethod
    def get_findings(
        self,
        cutoff_time: datetime,
        algorithm_type: Optional[str],
        min_findings: Optional[int],
        exclude_statuses: List[str],
        offset: int,
        limit: int,
    ) -> FindingsPage:
        ...


class SqlAlchemyFindingsStore(FindingsStore):
    """Real implementation, backed by Postgres/sqlite via SQLAlchemy."""

    def __init__(self, session_factory: Callable = None):
        # Injected rather than imported-and-called directly inside the
        # method -- same DI lever as everywhere else: tests can hand this a
        # fake/in-memory session factory instead of touching a real DB.
        if session_factory is None:
            from database.session import get_db_session

            session_factory = get_db_session
        self._session_factory = session_factory

    def get_findings(
        self,
        cutoff_time: datetime,
        algorithm_type: Optional[str],
        min_findings: Optional[int],
        exclude_statuses: List[str],
        offset: int,
        limit: int,
    ) -> FindingsPage:
        session = self._session_factory()
        try:
            # Single joined query replaces the original per-row nested
            # queries (1 finding query + 2 extra round-trips PER finding --
            # classic N+1). All filtering that CAN happen in SQL now does,
            # instead of fetching everything and discarding rows in Python.
            findings_query = (
                session.query(FindingDBModel, StudyDBModel, PatientDBModel)
                .join(StudyDBModel, FindingDBModel.accession_number == StudyDBModel.accession_number)
                .join(PatientDBModel, StudyDBModel.patient_id == PatientDBModel.patient_id)
                .filter(
                    FindingDBModel.creation_date >= cutoff_time,
                    FindingDBModel.is_removed.is_(False),
                )
            )

            if algorithm_type:
                findings_query = findings_query.filter(FindingDBModel.algorithm_type == algorithm_type)

            if min_findings is not None:
                findings_query = findings_query.filter(FindingDBModel.num_findings >= min_findings)

            if exclude_statuses:
                findings_query = findings_query.filter(FindingDBModel.status.notin_(exclude_statuses))

            # True total across the whole filtered set, computed before
            # paging -- this is what makes "total_count" meaningful once
            # pagination exists, instead of just echoing back page size.
            total_count = findings_query.count()

            rows = (
                findings_query.order_by(FindingDBModel.creation_date.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )

            items = [
                FindingSummary(
                    prediction_id=finding.finding_id,
                    accession_number=finding.accession_number,
                    patient_name=patient.patient_name,
                    patient_age=patient.patient_age,
                    patient_gender=patient.patient_gender,
                    algorithm_type=finding.algorithm_type,
                    num_findings=finding.num_findings,
                    status=finding.status,
                    creation_date=finding.creation_date.isoformat(),
                    study_date=study.study_date.isoformat(),
                )
                for finding, study, patient in rows
            ]
            return FindingsPage(items=items, total_count=total_count)
        finally:
            session.close()
