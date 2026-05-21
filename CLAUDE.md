# 자동 시험 생성 시스템

## 프로젝트
교수자 강의자료(PDF/PPTX/영상) → 시험 문제 + 모범답안 자동 생성 멀티 에이전트 시스템

## 스택
- Gemini API (Vertex AI 또는 AI Studio)
- pypdf, python-pptx, openai-whisper, arxiv, python-docx

## 폴더 구조
```
exam_gen/
├── main.py
├── agents/base.py, collector.py, topic_extractor.py, planner.py
│         generators.py, answer_generator.py, quality_reviewer.py
│         refiner.py, assembler.py
├── tools/file_readers.py, search_tools.py, file_writers.py
├── docs/agents.md, prompts.md, setup.md
└── tests/
```

## 에이전트 요약
| 에이전트 | 유형 | 모델 | 도구 |
|---|---|---|---|
| collector | 반사형 | 없음 | pypdf/pptx/whisper |
| topic_extractor | 기본형 | flash-lite | 없음 |
| planner | 계획형 | flash | 없음 |
| short/essay generator | 기본형 | flash-lite | 없음 |
| application generator | ReAct | flash | Google Search + arXiv |
| answer_generator | 기본형/ReAct | flash-lite/flash | 라우팅 |
| quality_reviewer | 기본형+HITL+반사형 라우터 | flash | 없음 |
| refiner | 성찰형 | flash | 없음 |
| assembler | 반사형 | 없음 | python-docx |

## 핵심 규칙
- 모든 에이전트는 BaseAgentWorker 상속, run(input_text) -> str 구현
- 환경변수: GCP_PROJECT_ID (Vertex AI) 또는 GEMINI_API_KEY (AI Studio)
- .env는 git 제외 (.gitignore에 포함)
- 단답형/에세이형/응용형 생성은 ThreadPoolExecutor로 병렬 실행
- Google Search 플러그인과 로컬 함수 도구는 같은 요청에 동시 사용 불가

## 피드백 루프
품질 검토 → 통과: 조립 / 개별재검토: refiner → 품질검토 / 전체재생성: planner부터

## 상세 문서
- 에이전트 구현 상세: @docs/agents.md
- Claude Code 요청 스크립트: @docs/prompts.md
- 환경 설정: @docs/setup.md
