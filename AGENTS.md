# 자동 시험 생성 시스템

## 프로젝트
교수자 강의자료(PDF/PPTX/영상) → 시험 문제 + 모범답안 자동 생성 멀티 에이전트 시스템

## 스택
- Gemini API (Vertex AI 또는 AI Studio)
- Claude API (Anthropic) — topic_extractor, short/essay/tf generator
- pypdf, python-pptx, openai-whisper, arxiv, python-docx

## 폴더 구조
```
exam_gen/
├── main.py
├── agents/base.py, collector.py, topic_extractor.py, planner.py
│         topic_slicer.py, generators.py, answer_generator.py, quality_reviewer.py
│         refiner.py, assembler.py
├── tools/file_readers.py, search_tools.py, search_cache.py, scoring.py,
│         file_writers.py, client.py, claude_client.py
├── docs/agents.md, prompts.md, setup.md
└── tests/
```

## 에이전트 요약
| 에이전트 | 유형 | 모델 | 도구 |
|---|---|---|---|
| collector | 반사형 | 없음 | pypdf/pptx/whisper |
| topic_extractor | 기본형 | claude-sonnet-4-6 | 없음 |
| topic_slicer | 규칙 기반 | 없음 | 정규식/텍스트 슬라이싱 |
| planner | 계획형 | flash | 없음 |
| short/essay/tf generator | 기본형 | claude-sonnet-4-6 | 없음 |
| application generator | ReAct | flash | Google Search + arXiv |
| answer_generator | 기본형/ReAct | flash-lite/flash | 라우팅 + 검색 cache |
| quality_reviewer | 기본형+규칙검사+반사형 라우터 | flash | quality_rules |
| refiner | targeted refine | flash | 없음 |
| assembler | 반사형 | 없음 | python-docx |

## 핵심 규칙
- 모든 에이전트는 BaseAgentWorker 상속, run(input_text) -> str 구현
- 환경변수: GCP_PROJECT_ID (Vertex AI) 또는 GEMINI_API_KEY (AI Studio), ANTHROPIC_API_KEY (Claude API)
- .env는 git 제외 (.gitignore에 포함)
- 진위형/단답형/에세이형/응용형 생성은 ThreadPoolExecutor로 병렬 실행
- answer_generator도 문제별 ThreadPoolExecutor 병렬 실행
- Google Search 플러그인과 로컬 함수 도구는 같은 요청에 동시 사용 불가

## 피드백 루프
rule-based 품질검사 → AI reviewer 최대 2회 → 지적 문항 자동 수정.
현재 자동 수정 순서: 1회차 동일 지적은 refiner, 2회차 동일 지적은 generator 재생성, 3회차는 unresolved 기록.
조립 후 교수자 콘솔 피드백은 refiner로 반영하고 다시 docx를 조립.

## 상세 문서
- 에이전트 구현 상세: @docs/agents.md
- 환경 설정: @docs/setup.md
