from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from database import engine, Base, get_db
import models, schemas, ai_service

# DB 테이블 생성
Base.metadata.create_all(bind=engine)

app = FastAPI()

# CORS 설정 (웹 프론트엔드와 통신하기 위함)
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 배포 시 실제 도메인으로 변경
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/records/submit")
def submit_exercise_record(record: schemas.RecordCreate, db: Session = Depends(get_db)):
    # 1. 환자 기록 DB 저장 [cite: 59, 89]
    db_record = models.ExerciseRecord(**record.dict())
    db.add(db_record)
    db.commit()
    db.refresh(db_record)

    # 2. AI 분석 수행 [cite: 61, 90]
    ai_result = ai_service.analyze_rehab_data(record.dict())

    # 3. AI 분석 결과 DB 저장 
    db_ai_analysis = models.AIAnalysis(
        record_id=db_record.id,
        patient_feedback=ai_result["patient_feedback"],
        therapist_summary=ai_result["therapist_summary"],
        risk_level=ai_result["risk_level"]
    )
    db.add(db_ai_analysis)
    db.commit()

    return {
        "status": "success",
        "message": "기록이 성공적으로 저장되고 분석되었습니다.",
        "ai_feedback": ai_result
    }

# 서버 실행 명령어: uvicorn main:app --reload