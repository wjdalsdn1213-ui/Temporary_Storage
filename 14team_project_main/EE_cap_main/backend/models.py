from sqlalchemy import Column, Integer, String, Text, ForeignKey, Boolean
from database import Base

class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    rrn = Column(String) # [RRN Omitted] 형태로 저장 권장

class ExerciseRecord(Base):
    __tablename__ = "exercise_records"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    exercise_name = Column(String)
    target_count = Column(Integer)
    actual_count = Column(Integer)
    pain_score = Column(Integer)
    difficulty = Column(String)
    memo = Column(Text)

class AIAnalysis(Base):
    __tablename__ = "ai_analyses"
    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(Integer, ForeignKey("exercise_records.id"))
    patient_feedback = Column(Text)
    therapist_summary = Column(Text)
    risk_level = Column(String)


class PrescriptionState(Base):
    __tablename__ = "prescription_states"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, index=True, unique=True)
    selected_exercises = Column(Text, default="[]")
    sent = Column(Boolean, default=False)