# 에이전트 상세 스펙

## BaseAgentWorker (agents/base.py)
- __init__(name, task_id)
- run(input_text) -> str (미구현 시 NotImplementedError)
- __repr__

## collector (반사형)
- 입력: 파일경로 줄바꿈 구분 문자열
- 출력: 파일별 "=== 파일명 ===" 구분자 포함 통합 텍스트
- 분기: .pdf→pypdf / .pptx→python-pptx / .mp4/.mov/.avi/.mkv→whisper / .txt→직접읽기

## topic_extractor (기본형, flash-lite)
- 입력: 강의자료 텍스트
- 출력: {"topics": [...], "key_concepts": [...]} JSON

## planner (계획형, flash)
- Chat 객체 사용 (교수자 요구사항 수정 가능하므로 히스토리 유지)
- 입력: "토픽: [...]\n요구사항: ..." 문자열
- 출력: {"단답형": 5, "에세이형": 3, "응용형": 2, "난이도": "mixed"} JSON

## generators (agents/generators.py)
- ShortAnswerGenerator (기본형, flash-lite)
- EssayGenerator (기본형, flash-lite)
- ApplicationGenerator (ReAct, flash)
  - 도구: search_arxiv (로컬) + Google Search (플러그인, 별도 요청)
- 입력: {"topics": [...], "count": N, "difficulty": "..."} JSON
- 출력: [{"id": "Q1", "type": "short/essay/application", "question": "..."}] JSON

## answer_generator (기본형/ReAct, 라우팅)
- type=="application" → ReAct + flash
- 그 외 → 기본형 + flash-lite
- 출력: [{"id", "type", "question", "answer"}] JSON

## quality_reviewer (기본형+HITL+반사형 라우터, flash)
- AI 자동 평가: 마크다운, 단답형 형식, 에세이형 열린 질문, 응용형 시나리오, 문제 개수 검토
- 문제 발견 시 해당 문제만 유형별 generator로 자동 재생성 (반사형 라우터)
- 입력: {"questions": [...], "plan": {...}} JSON
- 출력: {"pass": bool, "issues": [{"id", "type", "reason"}]} JSON

## refiner (성찰형, flash)
- 입력: {"problem": {...}, "feedback": "..."} JSON
- 피드백 반영 → 자기평가(1-5점) → 4점 미만 시 재생성 (최대 3회)
- 출력: 수정된 문제 JSON

## assembler (반사형, 없음)
- 입력: 최종 문제+답안 JSON
- 출력: output/exam.docx, output/answer_key.docx
