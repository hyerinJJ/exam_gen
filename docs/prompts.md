# Claude Code 요청 스크립트

순서대로 복사해서 붙여넣기.

---

## Step 1 — requirements.txt
```
requirements.txt 만들어줘. 라이브러리: google-genai, pypdf, python-pptx, openai-whisper, arxiv, python-docx, requests, python-dotenv
```

## Step 2 — 폴더 구조
```
폴더 구조 만들어줘. exam_gen/ 아래 main.py, agents/__init__.py+base.py+collector.py+topic_extractor.py+planner.py+generators.py+answer_generator.py+quality_reviewer.py+refiner.py+assembler.py, tools/__init__.py+file_readers.py+search_tools.py+file_writers.py, docs/, tests/test_tools.py+test_agents.py, .env.example, .gitignore
```

## Step 3 — 환경 설정 (.env.example, .gitignore, client 유틸)
```
.env.example, .gitignore, tools/client.py 만들어줘.

.env.example: GCP_PROJECT_ID, GCP_LOCATION=us-central1, GEMINI_API_KEY (둘 중 하나만)
.gitignore: .env, __pycache__, *.pyc, output/
tools/client.py: get_client() 함수 — GCP_PROJECT_ID 있으면 Vertex AI, 없으면 GEMINI_API_KEY로 AI Studio 방식. 없으면 ValueError.
```

## Step 4 — BaseAgentWorker
```
agents/base.py 구현. BaseAgentWorker: __init__(name,task_id), run(input_text)->str (NotImplementedError), __repr__
```

## Step 5 — 파일 읽기 도구
```
tools/file_readers.py 구현. read_pdf(pypdf), read_pptx(python-pptx 슬라이드별), read_video(whisper base모델), read_file(확장자 분기 라우터: .pdf/.pptx/.ppt/.mp4/.mov/.avi/.mkv/.txt, 그외 ValueError)
```

## Step 6 — collector
```
agents/collector.py 구현. BaseAgentWorker 상속. name="Content Collector", task_id="Task 0". run()은 줄바꿈 구분 파일경로 받아서 각 파일 read_file()로 읽고 "=== 파일명 ===" 구분자로 합쳐 반환. 오류 시 해당 파일 건너뜀.
```

## Step 7 — topic_extractor
```
agents/topic_extractor.py 구현. BaseAgentWorker 상속. name="Topic Extractor", task_id="Task 1". 모델 gemini-2.5-flash-lite. tools/client.py의 get_client() 사용. 강의자료 텍스트 받아서 {"topics":[...],"key_concepts":[...]} JSON 반환.
```

## Step 8 — arXiv + Google Search 도구
```
tools/search_tools.py 구현. search_arxiv(query, max_results=3): arxiv 라이브러리로 논문 제목/요약/연도 텍스트 반환. search_with_google(query): Google Search 플러그인(types.Tool(google_search=types.GoogleSearch())) + gemini-2.5-flash로 검색 결과 반환.
```

## Step 9 — generators
```
agents/generators.py 구현. ShortAnswerGenerator(기본형, flash-lite), EssayGenerator(기본형, flash-lite), ApplicationGenerator(ReAct, flash, search_arxiv+search_with_google). 입력: {"topics":[...],"count":N,"difficulty":"..."} JSON. 출력: [{"id","type","question"}] JSON.
```

## Step 10 — answer_generator
```
agents/answer_generator.py 구현. BaseAgentWorker 상속. name="Answer Generator". 입력: 문제 리스트 JSON. type=="application"이면 ReAct+flash+검색도구, 그외 기본형+flash-lite. 출력: [{"id","type","question","answer"}] JSON.
```

## Step 11 — planner
```
agents/planner.py 구현. BaseAgentWorker 상속. name="Question Planner". 계획형. Chat 객체(flash). 입력: "토픽:[...]\n요구사항:..." 문자열. 출력: {"단답형":5,"에세이형":3,"응용형":2,"난이도":"mixed"} JSON.
```

## Step 12 — quality_reviewer
```
agents/quality_reviewer.py 구현. BaseAgentWorker 상속. name="Quality Reviewer". ReAct+HITL. flash. AI 1차 평가 후 콘솔 출력. input()으로 p/i/r 입력받기. i면 문제번호도 추가 입력. 출력: {"decision":"pass/individual/regenerate","feedback":"...","problem_ids":[...]} JSON.
```

## Step 13 — refiner
```
agents/refiner.py 구현. BaseAgentWorker 상속. name="Question Refiner". 성찰형. flash. 입력: {"problem":{...},"feedback":"..."} JSON. 피드백 반영 재생성 → 자기평가(1-5점) → 4점 미만 재생성 (최대 3회). 출력: 수정된 문제 JSON.
```

## Step 14 — assembler + file_writers
```
tools/file_writers.py: save_exam_docx(questions,output_path), save_answer_key_docx(qa_pairs,output_path). python-docx 사용. 한글 폰트 설정 포함.
agents/assembler.py: BaseAgentWorker 상속. name="Exam Assembler". 반사형(LLM없음). 입력: 최종 문제+답안 JSON. output/ 폴더에 exam.docx, answer_key.docx 저장.
```

## Step 15 — main.py
```
main.py 구현. run_pipeline(file_paths, requirements) 함수. 순서: collector → topic_extractor → planner → ThreadPoolExecutor(short/essay/application 병렬) → answer_generator → 품질검토루프(pass:조립 / individual:refiner후재검토 / regenerate:planner부터) → assembler. if __name__=="__main__": 예시 실행.
```

## Step 16 — 테스트
```
tests/test_tools.py: read_file 라우터 분기 테스트, search_arxiv 실제 호출("machine learning").
tests/test_agents.py: TopicExtractorAgent 샘플텍스트 입력, ShortAnswerGenerator 샘플토픽, 각 출력이 유효한 JSON인지 검증.
```
