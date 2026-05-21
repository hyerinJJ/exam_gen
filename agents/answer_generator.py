import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from agents.base import BaseAgentWorker
from tools.client import get_client, retry_call
from tools.search_tools import search_arxiv, search_with_google
from tools.search_cache import get_cached, set_cached

FLASH_LITE = "gemini-2.5-flash-lite"
FLASH = "gemini-2.5-flash"

_NO_MARKDOWN = "마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오."

_CORE_PRINCIPLE = """핵심 원칙: 문제가 요구하는 것에만 정확히 답한다. 요구 이상 절대 확장 금지.
문제를 먼저 읽고 학생이 어떻게 답해야 하는가를 판단한 후 그 형식으로만 작성하라."""

SHORT_ANSWER_PROMPT = f"""{_CORE_PRINCIPLE}
{_NO_MARKDOWN}

단답형 유형별 규칙:
- 단어/용어: 정답 용어만 한 줄 (예: 비지도 학습(Unsupervised Learning))
- 순서/단계 (N개): 각 단계를 줄바꿈으로 나열, 번호 불필요
- 항목 나열 (N가지): 항목만 줄바꿈으로 나열

설명 문장 금지. 정답만.

문제: {{question}}"""

ESSAY_PROMPT = f"""{_CORE_PRINCIPLE}
{_NO_MARKDOWN}

문제 유형에 따라 아래 형식 중 하나만 사용하라. 서론·결론·도입부 금지.
- 설명/서술 요구 → 핵심 내용만 3~5문장
- 비교/차이점 요구 → 비교 항목과 차이만
- 단계/절차 요구 → 번호 붙여 각 단계 1~2문장
- 계산 요구 → 풀이 과정과 결과값만
- 사례 제시 요구 → 구체적 사례 1~2개만

문제: {{question}}"""

APPLICATION_PROMPT = f"""{_CORE_PRINCIPLE}
{_NO_MARKDOWN}

시나리오 재서술 금지. 질문에만 집중하라.
참고 자료는 답변을 뒷받침하는 경우에만 간결하게 인용하라.

참고 자료:
{{search_results}}

문제: {{question}}"""

RUBRIC_PROMPT = f"""문제와 모범답안을 보고 채점 기준을 작성하세요.
{_NO_MARKDOWN}
문제가 요구하는 답의 유형을 먼저 파악해 아래 형식 중 하나만 출력하세요. 합계 10점. 다른 텍스트 없이.

단어/용어형:
정답(10점): [정답]
오답(0점): 그 외

나열형 (N가지):
총 N항목. 항목당 [10/N]점. 순서 무관.
- [항목1]([N점])
- [항목2]([N점])

순서/단계형 (N단계):
총 N단계. 단계당 [10/N]점. 순서 오류 시 해당 단계 0점.
1단계([N점]): [내용]
2단계([N점]): [내용]

서술형:
[포인트 1]: 내용 (N점)
[포인트 2]: 내용 (N점)
[포인트 3]: 내용 (N점)

문제: {{question}}
모범답안: {{answer}}"""

KEYWORD_PROMPT = """다음 문제에서 arXiv 검색에 적합한 영어 키워드 3~5개를 추출하세요.
반드시 영어 단어만, 공백으로 구분하여 한 줄로만 출력하세요. 다른 텍스트 없이.

문제: {question}"""


class AnswerGeneratorAgent(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Answer Generator", task_id="Task 4")
        self._client = get_client()

    def _extract_english_keywords(self, question: str) -> str:
        prompt = KEYWORD_PROMPT.format(question=question)
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=prompt))
        return response.text.strip()

    def _generate_rubric(self, question: str, answer: str) -> str:
        prompt = RUBRIC_PROMPT.format(question=question, answer=answer)
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=prompt))
        return response.text.strip()

    def _generate_short_answer(self, question: dict) -> dict:
        prompt = SHORT_ANSWER_PROMPT.format(question=question["question"])
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=prompt))
        answer = response.text.strip()
        rubric = self._generate_rubric(question["question"], answer)
        return {"answer": answer, "rubric": rubric}

    def _generate_essay_answer(self, question: dict) -> dict:
        prompt = ESSAY_PROMPT.format(question=question["question"])
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=prompt))
        answer = response.text.strip()
        rubric = self._generate_rubric(question["question"], answer)
        return {"answer": answer, "rubric": rubric}

    def _generate_application_answer(self, question: dict) -> dict:
        en_keywords = self._extract_english_keywords(question["question"])

        arxiv_query = en_keywords
        arxiv_results = get_cached(arxiv_query)
        if arxiv_results is None:
            try:
                arxiv_results = search_arxiv(en_keywords, max_results=2)
            except Exception:
                arxiv_results = "(arXiv 검색 결과 없음)"
            set_cached(arxiv_query, arxiv_results)

        google_query = f"{question['question'][:80]} 해결 방법 사례"
        google_results = get_cached(google_query)
        if google_results is None:
            google_results = search_with_google(google_query)
            set_cached(google_query, google_results)

        search_results = f"[arXiv]\n{arxiv_results}\n\n[Google]\n{google_results}"

        prompt = APPLICATION_PROMPT.format(
            question=question["question"],
            search_results=search_results,
        )
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH, contents=prompt))
        answer = response.text.strip()
        rubric = self._generate_rubric(question["question"], answer)
        return {"answer": answer, "rubric": rubric}

    def _generate_answer(self, question: dict) -> dict:
        """단답형/에세이형 라우터 (병렬 실행용)."""
        if question.get("type") == "short":
            return self._generate_short_answer(question)
        return self._generate_essay_answer(question)

    def run(self, input_text: str) -> str:
        questions = json.loads(input_text)

        short_essay = [q for q in questions if q.get("type") != "application"]
        application = [q for q in questions if q.get("type") == "application"]

        results_map: dict = {}

        # 1. 단답형 + 에세이형: flash-lite, 도구 없음 → 병렬
        with ThreadPoolExecutor(max_workers=max(1, len(short_essay))) as executor:
            future_to_q = {executor.submit(self._generate_answer, q): q for q in short_essay}
            for future in as_completed(future_to_q):
                q = future_to_q[future]
                result = future.result()
                results_map[q["id"]] = {
                    "id": q["id"], "type": q["type"],
                    "question": q["question"], **result,
                }

        # 2. 응용형: Google Search 플러그인 포함 → 순차
        for q in application:
            result = self._generate_application_answer(q)
            results_map[q["id"]] = {
                "id": q["id"], "type": q["type"],
                "question": q["question"], **result,
            }

        # 3. 원래 순서 유지
        ordered = [results_map[q["id"]] for q in questions]
        return json.dumps(ordered, ensure_ascii=False, indent=2)
