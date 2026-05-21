import json
from agents.base import BaseAgentWorker
from tools.client import get_client, retry_call
from tools.search_tools import search_arxiv, search_with_google
from google.genai import types

FLASH_LITE = "gemini-2.5-flash-lite"
FLASH = "gemini-2.5-flash"

SHORT_PROMPT = """다음 토픽과 조건으로 단답형 문제 {count}개를 생성하세요.
토픽: {topics}
난이도: {difficulty}

규칙:
- 답이 반드시 단어 또는 짧은 용어(1~5단어)로 나올 수 있는 질문만 만들 것
- "~은 무엇인가?", "~를 무엇이라 하는가?" 형식으로 질문할 것
- 서술, 설명, 나열을 요구하는 질문 금지
- 마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오

좋은 예시:
- "훈련 데이터에 과도하게 적합되어 새로운 데이터에 성능이 떨어지는 현상을 무엇이라 하는가?"
- "Work system을 구성하는 9가지 요소 프레임워크를 무엇이라 하는가?"

나쁜 예시 (금지):
- "Work system의 정의를 설명하시오."
- "3가지를 나열하시오."

반드시 아래 JSON 배열 형식으로만 응답하세요:
[{{"id": "Q1", "type": "short", "question": "..."}}]"""

ESSAY_PROMPT = """다음 토픽과 조건으로 에세이형 문제 {count}개를 생성하세요.
토픽: {topics}
난이도: {difficulty}

규칙:
- 질문은 2~3줄 이내로 간결하게 작성할 것
- 핵심 질문 하나에만 집중할 것
- 여러 개념을 동시에 묻거나 소문항(1), 2), 3))이 있는 질문 금지
- 마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오

좋은 예시:
- "지도학습과 비지도학습의 차이를 설명하고 각각의 사례를 제시하시오."

나쁜 예시 (금지):
- 여러 개념을 동시에 묻거나 3~4개 소문항이 있는 질문

반드시 아래 JSON 배열 형식으로만 응답하세요:
[{{"id": "Q1", "type": "essay", "question": "..."}}]"""

APPLICATION_PROMPT = """다음 토픽과 조건으로 응용형 문제 {count}개를 생성하세요.
토픽: {topics}
난이도: {difficulty}
참고 자료:
{search_results}

규칙:
- 실제 시나리오를 3~4줄 이내로 짧고 명확하게 제시한 뒤 질문할 것
- 질문은 한 가지에만 집중할 것
- 소문항이 여러 개인 질문 금지
- 마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오

좋은 예시:
- "A기업이 물류 자동화를 도입했다. Work System Framework 관점에서 어떤 요소가 변화하는지 설명하시오."

나쁜 예시 (금지):
- 시나리오가 길고 소문항이 여러 개인 질문

반드시 아래 JSON 배열 형식으로만 응답하세요:
[{{"id": "Q1", "type": "application", "question": "..."}}]"""


def _extract_json(raw: str) -> str:
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return raw


def _renumber(questions: list, prefix: str, start: int) -> list:
    for i, q in enumerate(questions):
        q["id"] = f"{prefix}{start + i}"
    return questions


class ShortAnswerGenerator(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Short Answer Generator", task_id="Task 3a")
        self._client = get_client()

    def run(self, input_text: str) -> str:
        data = json.loads(input_text)
        prompt = SHORT_PROMPT.format(
            topics=", ".join(data["topics"]),
            count=data["count"],
            difficulty=data.get("difficulty", "mixed"),
        )
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=prompt))
        raw = _extract_json(response.text.strip())
        json.loads(raw)
        return raw


class EssayGenerator(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Essay Generator", task_id="Task 3b")
        self._client = get_client()

    def run(self, input_text: str) -> str:
        data = json.loads(input_text)
        prompt = ESSAY_PROMPT.format(
            topics=", ".join(data["topics"]),
            count=data["count"],
            difficulty=data.get("difficulty", "mixed"),
        )
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=prompt))
        raw = _extract_json(response.text.strip())
        json.loads(raw)
        return raw


class ApplicationGenerator(BaseAgentWorker):
    """ReAct 패턴: arXiv + Google Search로 최신 자료 검색 후 응용 문제 생성."""

    def __init__(self):
        super().__init__(name="Application Generator", task_id="Task 3c")
        self._client = get_client()

    def _extract_english_keywords(self, topics: list) -> str:
        prompt = (
            "다음 토픽들에서 arXiv 검색에 적합한 영어 키워드 3~5개를 추출하세요.\n"
            "반드시 영어 단어만, 공백으로 구분하여 한 줄로만 출력하세요. 다른 텍스트 없이.\n\n"
            f"토픽: {', '.join(topics)}"
        )
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=prompt))
        return response.text.strip()

    def run(self, input_text: str) -> str:
        data = json.loads(input_text)
        topics = data["topics"]

        # arXiv는 영어 쿼리만 지원하므로 LLM으로 키워드 추출
        en_keywords = self._extract_english_keywords(topics)
        try:
            arxiv_results = search_arxiv(en_keywords, max_results=3)
        except Exception:
            arxiv_results = "(arXiv 검색 결과 없음)"
        google_results = search_with_google(f"{' '.join(topics[:3])} 최신 연구 동향 응용 사례")

        search_results = f"[arXiv]\n{arxiv_results}\n\n[Google]\n{google_results}"

        prompt = APPLICATION_PROMPT.format(
            topics=", ".join(topics),
            count=data["count"],
            difficulty=data.get("difficulty", "mixed"),
            search_results=search_results,
        )
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH, contents=prompt))
        raw = _extract_json(response.text.strip())
        json.loads(raw)
        return raw
