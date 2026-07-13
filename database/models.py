from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class FindingStatus(str, Enum):
    """Type-safe status values -- replaces magic strings like "completed"
    scattered across the service/store layers (same fix as ARCHIVED_STATUS
    in the ScanReportService exercise)."""

    PENDING = "pending"
    COMPLETED = "completed"
    IN_REVIEW = "in_review"


class PatientDBModel(Base):
    __tablename__ = "patients"

    patient_id = Column(String, primary_key=True)  # identifier from the source system
    patient_name = Column(String, nullable=False)
    patient_age = Column(Integer, nullable=True)
    patient_gender = Column(String, nullable=True)
    creation_date = Column(DateTime, default=datetime.utcnow, nullable=False)

    studies = relationship("StudyDBModel", back_populates="patient")


class StudyDBModel(Base):
    """A single imaging scan."""

    __tablename__ = "studies"

    accession_number = Column(String, primary_key=True)  # study's unique identifier from the source system
    patient_id = Column(String, ForeignKey("patients.patient_id"), nullable=False, index=True)
    study_date = Column(DateTime, nullable=False)
    modality = Column(String, nullable=True)
    creation_date = Column(DateTime, default=datetime.utcnow, nullable=False)

    patient = relationship("PatientDBModel", back_populates="studies")
    findings = relationship("FindingDBModel", back_populates="study")


class FindingDBModel(Base):
    """A single result for a study, produced by an algorithm."""

    __tablename__ = "findings"

    finding_id = Column(String, primary_key=True)
    accession_number = Column(String, ForeignKey("studies.accession_number"), nullable=False, index=True)
    algorithm_type = Column(String, nullable=False, index=True)
    num_findings = Column(Integer, default=0, nullable=False)
    status = Column(String, default=FindingStatus.PENDING.value, nullable=False)
    is_removed = Column(Boolean, default=False, nullable=False)
    # Missing feature #2 (beyond pagination): every /api/findings call filters
    # on creation_date >= cutoff_time with no index backing it -- on a real
    # findings table this is a full scan under load. Added here.
    creation_date = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    last_update_date = Column(DateTime, default=datetime.utcnow, nullable=False)

    study = relationship("StudyDBModel", back_populates="findings")
