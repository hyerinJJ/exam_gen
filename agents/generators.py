import json
from agents.base import BaseAgentWorker
from tools.client import get_client, retry_call
from tools.search_tools import search_arxiv, search_with_google
from tools.search_cache import get_cached, set_cached
from google.genai import types

FLASH_LITE = "gemini-2.5-flash-lite"
FLASH = "gemini-2.5-flash"

SHORT_PROMPT = """다음 토픽과 조건으로 단답형 문제 {count}개를 생성하세요.
토픽: {topics}
난이도: {difficulty}
{scope_line}
출제 유형 (아래 세 유형을 골고루 섞을 것):
1. 용어/개념형 — 답이 단어나 짧은 용어 하나
   예: "훈련 데이터에 과도하게 적합되어 새로운 데이터에 성능이 떨어지는 현상을 무엇이라 하는가?"
2. 순서/단계형 — 답이 순서 있는 단계 나열 (각 항목은 단어나 짧은 구)
   예: "KJ Method의 단계를 순서대로 쓰시오."
   예: "Engineering Problem-Solving Process의 5단계를 순서대로 쓰시오."
3. 항목 나열형 — 답이 순서 없는 짧은 항목들
   예: "Work System Framework의 구성 요소 3가지를 쓰시오."

규칙:
- 답은 반드시 용어, 짧은 구, 또는 짧은 항목들의 나열이어야 함. 문장 서술 답변 금지.
- 큰 개념과 구체적인 세부 내용, 순서나 단계를 묻는 문제를 균형 있게 출제할 것
- 마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오

나쁜 예시 (금지):
- "Work system의 정의를 설명하시오." (문장 서술 요구)
- "~의 장단점을 논하시오." (에세이형)

반드시 아래 JSON 배열 형식으로만 응답하세요:
[{{"id": "Q1", "type": "short", "question": "..."}}]"""

ESSAY_PROMPT = """다음 토픽과 조건으로 에세이형 문제 {count}개를 생성하세요.
토픽: {topics}
난이도: {difficulty}
{scope_line}
출제 유형 (아래 네 유형을 골고루 섞을 것):
1. 개념 비교/설명형 — 두 개념의 차이, 원리, 의미 서술
   예: "지도학습과 비지도학습의 차이를 설명하고 각각의 사례를 제시하시오."
2. 계산/수치 도출형 — 주어진 값을 이용해 수식을 적용하거나 결과를 계산
   예: "표준 시간이 120분, 실제 작업 시간이 100분일 때 효율을 계산하시오."
3. 단계/절차 서술형 — 특정 프로세스나 방법론의 순서와 각 단계의 역할 설명
   예: "KJ Method의 각 단계를 순서대로 설명하시오."
4. 적용/분석형 — 개념을 특정 상황에 적용하거나 원인·결과 분석
   예: "Work System Framework의 각 구성 요소가 조직 성과에 어떤 영향을 미치는지 설명하시오."

규칙:
- 질문은 2~3줄 이내로 간결하게 작성할 것
- 핵심 질문 하나에만 집중할 것
- 여러 개념을 동시에 묻거나 소문항(1), 2), 3))이 있는 질문 금지
- 큰 개념과 구체적인 세부 내용, 순서나 단계가 있는 내용을 묻는 문제를 균형 있게 출제할 것
- 마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오

나쁜 예시 (금지):
- 여러 개념을 동시에 묻거나 3~4개 소문항이 있는 질문

반드시 아래 JSON 배열 형식으로만 응답하세요:
[{{"id": "Q1", "type": "essay", "question": "..."}}]"""

APPLICATION_PROMPT = """다음 토픽과 조건으로 응용형 문제 {count}개를 생성하세요.
토픽: {topics}
난이도: {difficulty}
{scope_line}참고 자료:
{search_results}

규칙:
- 실제 시나리오를 3~4줄 이내로 짧고 명확하게 제시한 뒤 질문할 것
- 질문은 한 가지에만 집중할 것
- 소문항이 여러 개인 질문 금지
- 큰 개념과 구체적인 세부 내용, 순서나 단계가 있는 내용을 묻는 문제를 균형 있게 출제할 것
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


def _adjust_count(result: list, expected: int, name: str) -> list:
    """개수 불일치 최종 보정: 초과 시 자르기, 부족 시 경고 후 그대로."""
    if len(result) > expected:
        return result[:expected]
    if len(result) < expected:
        print(f"[{name}] 경고: {len(result)}/{expected}개 생성됨 (부족)")
    return result


def _renumber(questions: list, prefix: str, start: int) -> list:
    for i, q in enumerate(questions):
        q["id"] = f"{prefix}{start + i}"
    return questions


def _scope_line(data: dict) -> str:
    scope = data.get("scope", "")
    return f"출제 맥락: {scope}\n" if scope else ""


class ShortAnswerGenerator(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Short Answer Generator", task_id="Task 3a")
        self._client = get_client()

    def run(self, input_text: str) -> str:
        data = json.loads(input_text)
        expected = data["count"]
        result = None
        for attempt in range(2):
            prompt = SHORT_PROMPT.format(
                topics=", ".join(data["topics"]),
                count=expected,
                difficulty=data.get("difficulty", "mixed"),
                scope_line=_scope_line(data),
            )
            response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=prompt))
            raw = _extract_json(response.text.strip())
            result = json.loads(raw)
            if len(result) == expected:
                return raw
            if attempt == 0:
                print(f"[{self.name}] 개수 불일치 ({len(result)}/{expected}), 재시도")
        result = _adjust_count(result, expected, self.name)
        return json.dumps(result, ensure_ascii=False)


class EssayGenerator(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Essay Generator", task_id="Task 3b")
        self._client = get_client()

    def run(self, input_text: str) -> str:
        data = json.loads(input_text)
        expected = data["count"]
        result = None
        for attempt in range(2):
            prompt = ESSAY_PROMPT.format(
                topics=", ".join(data["topics"]),
                count=expected,
                difficulty=data.get("difficulty", "mixed"),
                scope_line=_scope_line(data),
            )
            response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=prompt))
            raw = _extract_json(response.text.strip())
            result = json.loads(raw)
            if len(result) == expected:
                return raw
            if attempt == 0:
                print(f"[{self.name}] 개수 불일치 ({len(result)}/{expected}), 재시도")
        result = _adjust_count(result, expected, self.name)
        return json.dumps(result, ensure_ascii=False)


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

        arxiv_query = en_keywords
        arxiv_results = get_cached(arxiv_query)
        if arxiv_results is None:
            try:
                arxiv_results = search_arxiv(en_keywords, max_results=3)
            except Exception:
                arxiv_results = "(arXiv 검색 결과 없음)"
            set_cached(arxiv_query, arxiv_results)

        google_query = f"{' '.join(topics[:3])} 최신 연구 동향 응용 사례"
        google_results = get_cached(google_query)
        if google_results is None:
            google_results = search_with_google(google_query)
            set_cached(google_query, google_results)

        search_results = f"[arXiv]\n{arxiv_results}\n\n[Google]\n{google_results}"

        # 검색은 한 번만, LLM 생성만 재시도
        expected = data["count"]
        result = None
        for attempt in range(2):
            prompt = APPLICATION_PROMPT.format(
                topics=", ".join(topics),
                count=expected,
                difficulty=data.get("difficulty", "mixed"),
                scope_line=_scope_line(data),
                search_results=search_results,
            )
            response = retry_call(lambda: self._client.models.generate_content(model=FLASH, contents=prompt))
            raw = _extract_json(response.text.strip())
            result = json.loads(raw)
            if len(result) == expected:
                return raw
            if attempt == 0:
                print(f"[{self.name}] 개수 불일치 ({len(result)}/{expected}), 재시도")
        result = _adjust_count(result, expected, self.name)
        return json.dumps(result, ensure_ascii=False)
