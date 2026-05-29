# Claude Code 요청 스크립트

순서대로 복사해서 붙여넣기.

---

## Step 1 — package_requirements.txt
```
package_requirements.txt 만들어줘. 라이브러리: google-genai, anthropic, pypdf, python-pptx, openai-whisper, arxiv, python-docx, requests, python-dotenv
```

## Step 2 — 폴더 구조
```
폴더 구조 만들어줘. exam_gen/ 아래 main.py, agents/__init__.py+base.py+collector.py+topic_extractor.py+planner.py+generators.py+answer_generator.py+quality_reviewer.py+refiner.py+assembler.py, tools/__init__.py+file_readers.py+search_tools.py+file_writers.py, docs/, tests/test_tools.py+test_agents.py, .env.example, .gitignore
```

## Step 3 — 환경 설정 (.env.example, .gitignore, client 유틸)
```
.env.example, .gitignore, tools/client.py 만들어줘.

.env.example: 기본은 GCP_PROJECT_ID, GCP_LOCATION=us-central1, ANTHROPIC_API_KEY. 예외적으로 GEMINI_API_KEY 사용 가능.
.gitignore: .env, __pycache__, *.pyc, output/
tools/client.py: get_client() 함수 — GCP_PROJECT_ID 있으면 Vertex AI, 없으면 GEMINI_API_KEY로 AI Studio 방식. 없으면 ValueError.
tools/claude_client.py: ANTHROPIC_API_KEY로 Claude client 생성. 기본 모델 claude-sonnet-4-6. 429/500/529 재시도.
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
agents/topic_extractor.py 구현. BaseAgentWorker 상속. name="Topic Extractor", task_id="Task 1". Claude API 사용. 강의자료 텍스트 받아서 {"topics":[...],"key_concepts":[...],"tf_traps":[...]} JSON 반환. topic에는 importance, difficulty, knowledge_type, exam_use, source_file, concept_group, reason 포함.
```

## Step 7.5 — topic_slicer
```
agents/topic_slicer.py 구현. LLM 없이 전체 강의 텍스트에서 각 topic과 관련된 텍스트 조각을 찾아 evidence_text, source_refs를 붙임.
```

## Step 8 — arXiv + Google Search 도구
```
tools/search_tools.py 구현. search_arxiv(query, max_results=3): arxiv 라이브러리로 논문 제목/요약/연도 텍스트 반환. search_with_google(query): Google Search 플러그인(types.Tool(google_search=types.GoogleSearch())) + gemini-2.5-flash로 검색 결과 반환.
```

## Step 9 — generators
```
agents/generators.py 구현. ShortAnswerGenerator/EssayGenerator/TFGenerator는 Claude 사용. ApplicationGenerator는 flash + search_arxiv + search_with_google 사용. 기본 입력은 {"plan_items":[...]} JSON이고, fallback으로 {"topics":[...],"count":N,"difficulty":"..."}도 지원. short/tf는 answer를 함께 생성해 grading_seed로 전달. essay/application은 topic evidence와 출제 의도를 grading_seed로 전달.
```

## Step 10 — answer_generator
```
agents/answer_generator.py 구현. BaseAgentWorker 상속. name="Answer Generator". 입력: 문제 리스트 JSON. 문제별 ThreadPoolExecutor 병렬 처리. short/tf는 grading_seed의 expected_answer 우선 사용. essay는 flash-lite로 모범답안/rubric/grading_notes 생성. application은 grading_seed가 부족할 때 검색을 보조로 쓰고 flash/flash-lite로 답안과 rubric 생성. 출력은 answer, rubric, grading_notes 포함.
```

## Step 11 — planner
```
agents/planner.py 구현. BaseAgentWorker 상속. name="Question Planner". 계획형. Chat 객체(flash). 입력: {"topic_extraction":{...},"requirements":"..."} JSON. 출력: 문제 수, 난이도, 시험 표지 정보, question_plan 포함 JSON. question_plan은 각 문항의 topic, target_concept, difficulty, reason, topic_meta를 포함. TF는 intended_answer와 tf_type을 미리 배정.
```

## Step 12 — quality_reviewer
```
agents/quality_reviewer.py 구현. BaseAgentWorker 상속. name="Quality Reviewer". flash. 입력 {"questions":[...],"plan":{...}}. 출력 {"pass":bool,"issues":[{"id","type","reason"}]}. main.py에서 rule-based check 후 AI reviewer를 최대 2회 호출하고, 지적 문항만 자동 수정.
```

## Step 13 — refiner
```
agents/refiner.py 구현. BaseAgentWorker 상속. name="Question Refiner". targeted refine. flash. 입력: {"problem":{...},"feedback":"..."} JSON. 피드백 반영 후 같은 JSON 형식의 수정 문제를 1회 생성. 자기평가 루프 없음.
```

## Step 14 — assembler + file_writers
```
tools/file_writers.py: save_exam_docx(questions,output_path), save_answer_key_docx(qa_pairs,output_path). python-docx 사용. 한글 폰트 설정 포함.
agents/assembler.py: BaseAgentWorker 상속. name="Exam Assembler". 반사형(LLM없음). 입력: 최종 문제+답안 JSON. output/ 폴더에 exam.docx, answer_key.docx 저장.
```

## Step 15 — main.py
```
main.py 구현. run_pipeline(file_paths, requirements) 함수. 순서: collector → topic_extractor → topic_slicer → planner → assign_points → ThreadPoolExecutor(tf/short/essay/application 병렬 생성) → answer_generator 병렬 답안 생성 → rule-based 품질검사 → AI reviewer 최대 2회 → assembler → 교수자 콘솔 피드백/refiner → 재조립. if __name__=="__main__": input/requirements.txt와 강의자료 자동 로드.
```

## Step 16 — 테스트
```
tests/test_tools.py: read_file 라우터 분기 테스트, search_arxiv 실제 호출("machine learning").
tests/test_agents.py: TopicExtractorAgent 샘플텍스트 입력, ShortAnswerGenerator 샘플토픽, 각 출력이 유효한 JSON인지 검증.
```
