from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, ContextManager, List, Optional

from database.models import FindingDBModel, PatientDBModel, StudyDBModel


class FindingNotFoundError(Exception):
    pass


@dataclass
class FindingSummary:
    """Response shape for one finding."""

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
    """A page of results, plus the total count across the whole filtered
    set (not just this page)."""

    items: List[FindingSummary]
    total_count: int


class FindingsTransaction(ABC):
    """Unit of work scoped to one batch of writes. get_finding()/
    save_finding() calls made through this object all commit together on a
    clean exit, or none of them do."""

    @abstractmethod
    def get_finding(self, finding_id: str) -> FindingDBModel:
        ...

    @abstractmethod
    def save_finding(self, finding: FindingDBModel) -> None:
        ...

    @abstractmethod
    def __enter__(self) -> "FindingsTransaction":
        ...

    @abstractmethod
    def __exit__(self, exc_type, exc, tb) -> bool:
        ...


# FindingsService depends on this interface, not on SqlAlchemyFindingsStore
# directly -- lets the service be unit-tested against an in-memory fake,
# no real database needed.
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

    @abstractmethod
    def begin_transaction(self) -> FindingsTransaction:
        ...


class SqlAlchemyFindingsStore(FindingsStore):
    """Real implementation, backed by Postgres/sqlite via SQLAlchemy."""

    def __init__(self, session_factory: Callable = None):
        if session_factory is None:
            from database.session import get_db_session

            session_factory = get_db_session
        self._session_factory = session_factory

    def begin_transaction(self) -> FindingsTransaction:
        return _SqlAlchemyFindingsTransaction(self._session_factory())

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
            # Single joined query -- avoids a separate query per finding
            # for its study and patient.
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

            # Computed before paging, so it reflects the whole filtered set.
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


class _SqlAlchemyFindingsTransaction(FindingsTransaction):
    """Adapts a SQLAlchemy Session's own begin/commit/rollback to the
    FindingsTransaction interface. No manual staging/rollback logic is
    needed here -- the Session already tracks changes to objects loaded
    through it, and `session.begin()` used as a context manager commits on
    a clean exit or rolls back on an exception."""

    def __init__(self, session):
        self._session = session
        self._session_transaction = None

    def get_finding(self, finding_id: str) -> FindingDBModel:
        finding = self._session.get(FindingDBModel, finding_id)
        if finding is None:
            raise FindingNotFoundError(f"no finding with id {finding_id!r}")
        return finding

    def save_finding(self, finding: FindingDBModel) -> None:
        # No-op: `finding` was loaded through this same session, so
        # SQLAlchemy is already tracking the mutation. Kept so callers
        # don't need to know that detail.
        pass

    def __enter__(self) -> FindingsTransaction:
        self._session_transaction = self._session.begin()
        self._session_transaction.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            self._session_transaction.__exit__(exc_type, exc, tb)
        finally:
            self._session.close()
        return False
