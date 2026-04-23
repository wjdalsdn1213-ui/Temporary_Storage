from pydantic import BaseModel
from typing import Optional

class RecordCreate(BaseModel):
    patient_id: int
    exercise_name: str
    target_count: int
    actual_count: int
    pain_score: int
    difficulty: str
    memo: Optional[str] = None


class PrescriptionUpdate(BaseModel):
    patient_id: int
    selected_exercises: list[str]
    sent: bool = True