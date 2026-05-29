# 에이전트 상세 스펙

## BaseAgentWorker (agents/base.py)
- __init__(name, task_id)
- run(input_text) -> str (미구현 시 NotImplementedError)
- __repr__

## collector (반사형)
- 입력: 파일경로 줄바꿈 구분 문자열
- 출력: 파일별 "=== 파일명 ===" 구분자 포함 통합 텍스트
- 분기: .pdf→pypdf / .pptx→python-pptx / .mp4/.mov/.avi/.mkv→whisper / .txt→직접읽기

## topic_extractor (기본형, claude-sonnet-4-6)
- 입력: 강의자료 텍스트
- 출력: {"topics": [...], "key_concepts": [...], "tf_traps": [...]} JSON
- topics에는 importance, difficulty, knowledge_type, exam_use, source_file, concept_group, reason 메타데이터 포함
- tools/claude_client.py의 claude_generate_text() 사용 (ANTHROPIC_API_KEY 필요)

## topic_slicer (LLM 없음)
- 입력: collector가 만든 전체 강의 텍스트와 topic_extractor의 topics
- 출력: 각 topic에 evidence_text, source_refs를 붙인 topics
- 역할: 문제 생성기와 답안 생성기가 topic 이름만 보지 않고 관련 강의자료 조각도 볼 수 있게 함

## planner (계획형, flash)
- Chat 객체 사용 (교수자 요구사항 수정 가능하므로 히스토리 유지)
- 입력: {"topic_extraction": {...}, "requirements": "..."} JSON
- 출력: 문제 수, 난이도, 시험 표지 정보, question_plan 포함 JSON
- question_plan은 각 문항별 question_type, topic_name, target_concept, difficulty, reason, topic_meta를 포함
- TF 문항은 planner 단계에서 intended_answer와 tf_type을 배정함

## generators (agents/generators.py)
- ShortAnswerGenerator (기본형, claude-sonnet-4-6) — claude_generate_text() 사용
- EssayGenerator (기본형, claude-sonnet-4-6) — claude_generate_text() 사용
- TFGenerator (기본형, claude-sonnet-4-6) — claude_generate_text() 사용
- ApplicationGenerator (ReAct, flash)
  - 도구: search_arxiv (로컬) + Google Search (Gemini tool, 별도 요청)
- 기본 입력: {"plan_items": [...]} JSON
- 구형 fallback 입력: {"topics": [...], "count": N, "difficulty": "..."} JSON
- 출력: [{"id": "Q1", "type": "short/essay/application/tf", "question": "..."}] JSON
- short/tf는 문제 생성 시 answer도 함께 만들고 grading_seed에 넣음
- essay/application은 topic evidence와 출제 의도를 grading_seed에 넣음

## answer_generator (기본형/ReAct, 라우팅)
- 모든 유형을 ThreadPoolExecutor로 병렬 처리
- short/tf는 grading_seed의 expected_answer를 우선 사용
- essay는 flash-lite로 모범답안, rubric, grading_notes 생성
- application은 grading_seed가 부족할 때 arXiv + Google Search를 보조로 사용하고 flash/flash-lite로 답안과 rubric 생성
- 출력: [{"id", "type", "question", "answer", "rubric", "grading_notes"}] JSON

## quality_reviewer (기본형+HITL+반사형 라우터, flash)
- rule-based check 후 AI reviewer를 최대 2회 호출
- AI 자동 평가: 마크다운, 단답형 형식, 에세이형 열린 질문, 응용형 시나리오, 문제 개수, TF 형식 등 검토
- 문제 발견 시 _apply_fixes에서 해당 문제만 자동 수정
- 현재 수정 순서: 1회차 동일 지적은 refiner, 2회차 동일 지적은 generator 재생성, 3회차는 unresolved 기록
- 입력: {"questions": [...], "plan": {...}} JSON
- 출력: {"pass": bool, "issues": [{"id", "type", "reason"}]} JSON

## refiner (targeted refine, flash)
- 입력: {"problem": {...}, "feedback": "..."} JSON
- 피드백을 반영해 같은 JSON 형식의 수정 문제를 1회 생성
- 자기평가 루프는 현재 구현에 없음
- 출력: 수정된 문제 JSON

## assembler (반사형, 없음)
- 입력: 최종 문제+답안 JSON
- 출력: output/exam.docx, output/answer_key.docx
