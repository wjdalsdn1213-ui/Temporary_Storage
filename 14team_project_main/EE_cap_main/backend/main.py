from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import engine, Base, get_db
import models, schemas, ai_service
import json

# DB 테이블 생성
Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 배포 시 실제 도메인으로 변경
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_prescription_clients: dict[int, set[WebSocket]] = {}


def _serialize_prescription(row: models.PrescriptionState | None, patient_id: int) -> dict:
    if not row:
        return {"patient_id": patient_id, "selected_exercises": [], "sent": False}
    try:
        selected = json.loads(row.selected_exercises or "[]")
        if not isinstance(selected, list):
            selected = []
    except Exception:
        selected = []
    return {
        "patient_id": row.patient_id,
        "selected_exercises": selected,
        "sent": bool(row.sent),
    }


async def _broadcast_prescription(patient_id: int, payload: dict) -> None:
    clients = _prescription_clients.get(patient_id, set())
    if not clients:
        return
    dead = []
    for ws in clients:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)
    if not clients and patient_id in _prescription_clients:
        del _prescription_clients[patient_id]


@app.get("/api/prescriptions/{patient_id}")
def get_prescription(patient_id: int, db: Session = Depends(get_db)):
    row = (
        db.query(models.PrescriptionState)
        .filter(models.PrescriptionState.patient_id == patient_id)
        .first()
    )
    return _serialize_prescription(row, patient_id)


@app.put("/api/prescriptions/{patient_id}")
async def upsert_prescription(
    patient_id: int, payload: schemas.PrescriptionUpdate, db: Session = Depends(get_db)
):
    if payload.patient_id != patient_id:
        return {"status": "error", "message": "patient_id 불일치"}

    row = (
        db.query(models.PrescriptionState)
        .filter(models.PrescriptionState.patient_id == patient_id)
        .first()
    )
    if not row:
        row = models.PrescriptionState(patient_id=patient_id)
        db.add(row)

    row.selected_exercises = json.dumps(payload.selected_exercises, ensure_ascii=False)
    row.sent = bool(payload.sent)
    db.commit()
    db.refresh(row)

    data = _serialize_prescription(row, patient_id)
    await _broadcast_prescription(patient_id, data)
    return {"status": "success", "data": data}


@app.websocket("/ws/prescriptions/{patient_id}")
async def ws_prescriptions(websocket: WebSocket, patient_id: int):
    await websocket.accept()
    bucket = _prescription_clients.setdefault(patient_id, set())
    bucket.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        bucket.discard(websocket)
        if not bucket and patient_id in _prescription_clients:
            del _prescription_clients[patient_id]


@app.post("/api/records/submit")
def submit_exercise_record(record: schemas.RecordCreate, db: Session = Depends(get_db)):
    db_record = models.ExerciseRecord(**record.dict())
    db.add(db_record)
    db.commit()
    db.refresh(db_record)

    ai_result = ai_service.analyze_rehab_data(record.dict())

    db_ai_analysis = models.AIAnalysis(
        record_id=db_record.id,
        patient_feedback=ai_result["patient_feedback"],
        therapist_summary=ai_result["therapist_summary"],
        risk_level=ai_result["risk_level"],
    )
    db.add(db_ai_analysis)
    db.commit()

    return {
        "status": "success",
        "message": "기록이 성공적으로 저장되고 분석되었습니다.",
        "ai_feedback": ai_result,
    }
