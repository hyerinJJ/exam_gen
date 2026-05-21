import json
from agents.base import BaseAgentWorker
from tools.client import get_client, retry_call
from tools.search_tools import search_arxiv, search_with_google

FLASH_LITE = "gemini-2.5-flash-lite"
FLASH = "gemini-2.5-flash"

_NO_MARKDOWN = "마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오."

SHORT_ANSWER_PROMPT = f"""다음 단답형 문제의 정답 용어를 한 줄로만 작성하세요.
{_NO_MARKDOWN}
단답형은 정답 용어만 한 줄로 작성, 설명 금지.
예시: 비지도 학습(Unsupervised Learning)

문제: {{question}}"""

_ANSWER_FORMAT = """반드시 아래 형식으로만 작성하세요. 다른 텍스트 없이.

핵심 포인트 1: [포인트 제목]
[2~3문장 설명]

핵심 포인트 2: [포인트 제목]
[2~3문장 설명]

핵심 포인트 3: [포인트 제목]
[2~3문장 설명]

규칙:
- 핵심 포인트는 2~4개
- 각 포인트당 2~3문장으로 간결하게 작성
- 서론, 결론, 비유, 예시 나열 금지
- 포인트 제목은 해당 내용의 핵심 개념이나 관점을 한 줄로"""

ESSAY_PROMPT = f"""다음 에세이형 문제에 대한 모범답안을 작성하세요.
{_NO_MARKDOWN}

문제: {{question}}

{_ANSWER_FORMAT}"""

APPLICATION_PROMPT = f"""다음 응용형 문제에 대한 모범답안을 작성하세요.
{_NO_MARKDOWN}

문제: {{question}}

참고 자료:
{{search_results}}

{_ANSWER_FORMAT}"""

RUBRIC_PROMPT = f"""다음 모범답안에서 핵심 채점 포인트를 3~5개 추출하고 각 포인트에 점수를 부여하세요.
{_NO_MARKDOWN}
포인트별 점수 합계는 10점입니다.
반드시 아래 형식으로만 출력하세요. 다른 텍스트 없이.

[포인트 1]: 내용 설명 (N점)
[포인트 2]: 내용 설명 (N점)
[포인트 3]: 내용 설명 (N점)

모범답안:
{{answer}}"""

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

    def _generate_rubric(self, answer: str) -> str:
        prompt = RUBRIC_PROMPT.format(answer=answer)
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=prompt))
        return response.text.strip()

    def _generate_short_answer(self, question: dict) -> dict:
        prompt = SHORT_ANSWER_PROMPT.format(question=question["question"])
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=prompt))
        answer = response.text.strip()
        rubric = f"정답(배점): {answer}\n오답(0점): 그 외"
        return {"answer": answer, "rubric": rubric}

    def _generate_essay_answer(self, question: dict) -> dict:
        prompt = ESSAY_PROMPT.format(question=question["question"])
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=prompt))
        answer = response.text.strip()
        rubric = self._generate_rubric(answer)
        return {"answer": answer, "rubric": rubric}

    def _generate_application_answer(self, question: dict) -> dict:
        en_keywords = self._extract_english_keywords(question["question"])
        try:
            arxiv_results = search_arxiv(en_keywords, max_results=2)
        except Exception:
            arxiv_results = "(arXiv 검색 결과 없음)"
        google_results = search_with_google(f"{question['question'][:80]} 해결 방법 사례")
        search_results = f"[arXiv]\n{arxiv_results}\n\n[Google]\n{google_results}"

        prompt = APPLICATION_PROMPT.format(
            question=question["question"],
            search_results=search_results,
        )
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH, contents=prompt))
        answer = response.text.strip()
        rubric = self._generate_rubric(answer)
        return {"answer": answer, "rubric": rubric}

    def run(self, input_text: str) -> str:
        questions = json.loads(input_text)
        results = []
        for q in questions:
            q_type = q.get("type")
            if q_type == "application":
                result = self._generate_application_answer(q)
            elif q_type == "short":
                result = self._generate_short_answer(q)
            else:
                result = self._generate_essay_answer(q)
            results.append({
                "id": q["id"],
                "type": q["type"],
                "question": q["question"],
                "answer": result["answer"],
                "rubric": result["rubric"],
            })
        return json.dumps(results, ensure_ascii=False, indent=2)
