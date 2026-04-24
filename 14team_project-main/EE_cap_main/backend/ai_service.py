import google.generativeai as genai
import os
# test 용도로 무료인 gemini 우선 사용
# 환경 변수에 GEMINI_API_KEY를 설정해야 합니다.
genai.configure(api_key=os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY"))

def analyze_rehab_data(record_data: dict):
    # 1. 규칙 기반 위험도 분류 (Rule-based) [cite: 160, 163, 165]
    pain_score = record_data["pain_score"]
    actual_count = record_data["actual_count"]
    target_count = record_data["target_count"]
    
    risk_level = "정상"
    if pain_score >= 8:
        risk_level = "치료사 확인 필요"
    elif (actual_count / target_count) < 0.5 and pain_score >= 5:
        risk_level = "수행률 저하 + 통증 상승 (주의 필요)"

    # 2. LLM을 활용한 요약 문장 생성 [cite: 80, 81, 83]
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    당신은 재활 치료 보조 AI입니다. 환자의 오늘 운동 기록을 바탕으로 다음 두 가지를 작성해주세요.
    
    [환자 입력 데이터]
    - 운동명: {record_data['exercise_name']}
    - 목표/실제 횟수: {target_count} / {actual_count}
    - 통증 점수: {pain_score} (0~9)
    - 난이도: {record_data['difficulty']}
    - 환자 메모: {record_data.get('memo', '없음')}
    - 현재 시스템 판정 위험도: {risk_level}

    [요청 사항]
    1. 환자용 피드백: 환자를 격려하고 내일 운동을 위한 간단한 조언 (친절한 말투, 2문장 이내)
    2. 치료사용 요약: 환자의 수행 상태와 자유 메모를 전문적이고 간결하게 요약. 처방 유지/관찰/확인 필요 등 추천 문장 포함 (객관적 말투, 2문장 이내)
    
    결과를 아래와 같은 형식으로만 답변해주세요:
    환자용: (내용)
    치료사용: (내용)
    """

    response = model.generate_content(prompt)
    result_text = response.text

    # 파싱
    patient_feedback = ""
    therapist_summary = ""
    for line in result_text.split('\n'):
        if line.startswith("환자용:"):
            patient_feedback = line.replace("환자용:", "").strip()
        elif line.startswith("치료사용:"):
            therapist_summary = line.replace("치료사용:", "").strip()

    return {
        "risk_level": risk_level,
        "patient_feedback": patient_feedback,
        "therapist_summary": therapist_summary
    }