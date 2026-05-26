import json
from agents.base import BaseAgentWorker
from tools.client import get_client, retry_call
from tools.search_tools import search_arxiv, search_with_google
from tools.search_cache import get_cached, set_cached
from google.genai import types

FLASH_LITE = "gemini-2.5-flash-lite"
FLASH = "gemini-2.5-flash"

# ── 구형 프롬프트 (topics 문자열 배열 기반, fallback용) ───────────────────────

SHORT_PROMPT = """다음 토픽과 조건으로 단답형 문제 {count}개를 생성하세요.
토픽: {topics}
난이도: {difficulty}
{scope_line}
출제 유형: 용어/개념형만 출제할 것.
답이 반드시 단어 또는 짧은 용어 하나여야 하는 문제만 생성하세요.

출제 원칙:
- 단순 암기가 아닌, 핵심 개념을 응축한 수치·약어·용어를 묻는 문제를 우선할 것
  (예: 특정 수치는 단순 숫자가 아니라 "측정과 표준화"라는 철학을 응축한 것임을 고려)
- {count}개 중 1~2개는 "알 것 같지만 정확히는 헷갈리는" 변별 문제로 구성할 것
  (예: 약어에서 특정 알파벳 하나, 유사 용어 구별 등)
- 같은 개념을 두 문제에서 반복 출제하지 말 것
- 친숙한 메인 개념보다 놓치기 쉬운 지엽적·세부적 사항을 묻는 문제를 포함할 것
  (예: 구성 요소의 정확한 명칭, 단계 수, 특정 조건에서의 예외 등 간과하기 쉬운 정보)
- 절차·순서가 있는 개념은 "몇 번째 단계" 또는 "직전/직후 단계"를 직접 묻는 문제를 출제할 것
  (예: "A 프로세스에서 분석 단계 직후에 오는 단계는?", "B 방법론의 세 번째 단계는?")

예: "훈련 데이터에 과도하게 적합되어 새로운 데이터에 성능이 떨어지는 현상을 무엇이라 하는가?"
예: "Work System Framework에서 업무를 실제로 수행하는 사람을 가리키는 용어는?"

규칙:
- 답이 단어/용어 하나인 문제만 생성. 나열을 요구하는 문제 절대 금지.
- 마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오

나쁜 예시 (절대 금지):
- "~을 3가지 쓰시오." (나열 요구)
- "Work system의 정의를 설명하시오." (서술 요구)
- "~의 장단점을 논하시오." (에세이형)
- 같은 개념을 다른 표현으로 반복 출제

반드시 아래 JSON 배열 형식으로만 응답하세요:
[{{"id": "Q1", "type": "short", "question": "..."}}]"""

ESSAY_PROMPT = """다음 토픽과 조건으로 에세이형 문제 {count}개를 생성하세요.
토픽: {topics}
난이도: {difficulty}
{scope_line}
출제 원칙:
- 한 문제에는 질문을 하나만 할 것. 여러 가지를 나열식으로 묻는 문제는 절대 금지
- 두 질문을 함께 다뤄야 할 때는 반드시 소문항 (1)(2)로 분리할 것
- 소문항 3개 이상 또는 (1)(2)(3) 나열 구조는 금지
- 하나의 개념만 묻지 말고, 두 개념의 연결·대비·인과관계를 서술하게 만들 것
  (예: A만 묻지 않고 A와 B를 대비하여 설명하도록 요구)
- "왜 중요한가" 또는 "어떤 의의가 있는가"를 묻는 꼬리 질문을 포함할 것
- 같은 개념을 두 문제에서 반복 출제하지 말 것

출제 유형 (아래 네 유형을 골고루 섞을 것):
1. 개념 비교/대비형 — 두 개념의 차이와 각각의 의의 서술
2. 계산/수치 도출형 — 수식 적용 후 그 결과의 관리적 의미까지 서술
3. 단계/절차 서술형 — 프로세스 순서와 각 단계가 그 순서여야 하는 이유까지 설명
4. 인과/분석형 — 개념 간 원인·결과 관계 또는 한계와 의의 분석

규칙:
- 질문은 2~3줄 이내로 간결하게 작성할 것
- 마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오

나쁜 예시 (금지):
- 단일 개념 설명만 요구하는 질문 ("A를 설명하시오.")
- 같은 개념을 다른 표현으로 반복 출제
- "(1) A를 설명하시오. (2) B를 설명하시오. (3) C를 설명하시오." 처럼 여러 개념을 단순 나열하는 구조

반드시 아래 JSON 배열 형식으로만 응답하세요:
[{{"id": "Q1", "type": "essay", "question": "..."}}]"""

APPLICATION_PROMPT = """다음 토픽과 조건으로 응용형 문제 {count}개를 생성하세요.
토픽: {topics}
난이도: {difficulty}
{scope_line}참고 자료:
{search_results}

출제 원칙:
- 강의 자료에 등장한 예시와 다른 새로운 맥락을 시나리오로 사용할 것
  (예: 강의에서 공장 예시를 들었다면 응급실·편의점·대학 행정 등 다른 맥락 사용)
- 강의 자료에서 등장한 예시에 다른 토픽을 적용하는 방법을 물어볼 것
- 시나리오 안에 기술·인간·조직 간의 갈등 구조를 심을 것
- 정해진 단일 정답이 없되, 강의에서 배운 개념·프레임워크를 근거로 사용해야 점수를 받는 구조로 설계할 것
- 같은 개념을 두 문제에서 반복 출제하지 말 것

문제 상황 제시 형식: 시나리오를 포함한 짧은 서술 3~4줄 + 질문 1가지


나쁜 예시 (금지):
- 단일 정답을 요구하는 질문

반드시 아래 JSON 배열 형식으로만 응답하세요:
[{{"id": "Q1", "type": "application", "question": "..."}}]"""


SHORT_PROMPT_PLAN = """다음 출제 계획에 따라 단답형 문제 {count}개를 생성하세요.
각 항목 순서대로 정확히 한 문제씩 출제하세요.

출제 계획:
{plan_items_text}

메타데이터 반영 지침:
- specificity=numerical: 수치·공식·정확한 값을 직접 묻는 문제
- specificity=concrete: 구체적 사례나 명칭을 확인하는 문제
- specificity=abstract: 개념 정의나 의미를 묻는 문제
- cognitive_type=quantitative: 계산·수치 결과를 묻는 문제
- cognitive_type=procedural: 단계·순서를 묻는 문제
- difficulty=easy: 기본 개념 직접 확인
- difficulty=hard: 유사 용어 구별, 약어 세부, 정확한 수치 등 변별 포인트
- importance=high: 강의의 핵심 개념으로 반드시 제대로 된 문제를 출제할 것

출제 원칙:
- 답이 반드시 단어 또는 짧은 용어 하나인 문제만 생성하세요.
- 나열을 요구하는 문제 절대 금지.
- 같은 개념을 두 문제에서 반복 출제하지 말 것.
- 마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오.

반드시 아래 JSON 배열 형식으로만 응답하세요:
[{{"id": "Q1", "type": "short", "question": "..."}}]"""

ESSAY_PROMPT_PLAN = """다음 출제 계획에 따라 에세이형 문제 {count}개를 생성하세요.
각 항목 순서대로 정확히 한 문제씩 출제하세요.

출제 계획:
{plan_items_text}

메타데이터 반영 지침:
- cognitive_type=causal: 원인·결과 관계 서술을 요구하는 문제
- cognitive_type=comparative: 두 개념 비교·대비를 요구하는 문제
- cognitive_type=qualitative: 의미·의의·한계 서술을 요구하는 문제
- specificity=abstract: 개념 간 관계나 원리 설명을 요구하는 문제
- sequence_dependency=true: 전제 개념과의 연관성을 설명하게 하는 문제
- difficulty=hard: 비판적 분석이나 종합적 이해가 필요한 심층 질문
- importance=high, scope=core: 반드시 포함해야 할 핵심 개념

출제 원칙:
- 두 개념의 연결·대비·인과관계를 서술하게 만들 것.
- "왜 중요한가" 또는 "어떤 의의가 있는가"를 묻는 꼬리 질문을 포함할 것.
- 같은 개념을 두 문제에서 반복 출제하지 말 것.
- 마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오.

반드시 아래 JSON 배열 형식으로만 응답하세요:
[{{"id": "Q1", "type": "essay", "question": "..."}}]"""

APPLICATION_PROMPT_PLAN = """다음 출제 계획에 따라 응용형 문제 {count}개를 생성하세요.
각 항목 순서대로 정확히 한 문제씩 출제하세요.

출제 계획:
{plan_items_text}

참고 자료:
{search_results}

메타데이터 반영 지침:
- cognitive_type=procedural: 프로세스를 새로운 상황에 적용하는 문제
- cognitive_type=causal: 원인·결과 구조가 있는 시나리오 문제
- cognitive_type=comparative: 두 접근법을 비교하는 시나리오 문제
- sequence_dependency=true: 전제 개념을 알아야 풀 수 있는 심화 적용 문제
- difficulty=hard: 기술·인간·조직 간 갈등이 있는 복잡한 시나리오
- importance=high: 강의 핵심 개념이 반드시 답안의 근거가 되어야 함

출제 원칙:
- 분량은 과도하게 하지 말 것.
- 정해진 단일 정답이 없되, 강의 개념·프레임워크를 근거로 사용해야 점수를 받는 구조로 설계.
- 마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오.

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


def _format_plan_items_text(plan_items: list) -> str:
    """plan_item 리스트를 LLM에 전달할 텍스트로 변환."""
    lines = []
    for i, item in enumerate(plan_items, 1):
        meta = item.get("topic_meta", {})
        lines.append(
            f"{i}. 토픽: {item.get('topic_name', '')} | "
            f"핵심 개념: {item.get('target_concept', '')} | "
            f"난이도: {item.get('difficulty', '-')} | "
            f"중요도: {meta.get('importance', '-')} | "
            f"범위: {meta.get('scope', '-')} | "
            f"구체성: {meta.get('specificity', '-')} | "
            f"인지유형: {meta.get('cognitive_type', '-')} | "
            f"출제이유: {item.get('reason', '-')}"
        )
    return "\n".join(lines)


class ShortAnswerGenerator(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Short Answer Generator", task_id="Task 3a")
        self._client = get_client()

    def run(self, input_text: str) -> str:
        data = json.loads(input_text)
        plan_items = data.get("plan_items")

        if plan_items is not None:
            expected = len(plan_items)
            result = None
            for attempt in range(2):
                prompt = SHORT_PROMPT_PLAN.format(
                    count=expected,
                    plan_items_text=_format_plan_items_text(plan_items),
                )
                response = retry_call(lambda: self._client.models.generate_content(
                    model=FLASH_LITE, contents=prompt))
                raw = _extract_json(response.text.strip())
                result = json.loads(raw)
                if len(result) == expected:
                    return raw
                if attempt == 0:
                    print(f"[{self.name}] 개수 불일치 ({len(result)}/{expected}), 재시도")
            result = _adjust_count(result, expected, self.name)
            return json.dumps(result, ensure_ascii=False)

        # Fallback: 구형 topics 배열 형식
        expected = data["count"]
        result = None
        for attempt in range(2):
            prompt = SHORT_PROMPT.format(
                topics=", ".join(data["topics"]),
                count=expected,
                difficulty=data.get("difficulty", "mixed"),
                scope_line=_scope_line(data),
            )
            response = retry_call(lambda: self._client.models.generate_content(
                model=FLASH_LITE, contents=prompt))
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
        plan_items = data.get("plan_items")

        if plan_items is not None:
            expected = len(plan_items)
            result = None
            for attempt in range(2):
                prompt = ESSAY_PROMPT_PLAN.format(
                    count=expected,
                    plan_items_text=_format_plan_items_text(plan_items),
                )
                response = retry_call(lambda: self._client.models.generate_content(
                    model=FLASH_LITE, contents=prompt))
                raw = _extract_json(response.text.strip())
                result = json.loads(raw)
                if len(result) == expected:
                    return raw
                if attempt == 0:
                    print(f"[{self.name}] 개수 불일치 ({len(result)}/{expected}), 재시도")
            result = _adjust_count(result, expected, self.name)
            return json.dumps(result, ensure_ascii=False)

        # Fallback
        expected = data["count"]
        result = None
        for attempt in range(2):
            prompt = ESSAY_PROMPT.format(
                topics=", ".join(data["topics"]),
                count=expected,
                difficulty=data.get("difficulty", "mixed"),
                scope_line=_scope_line(data),
            )
            response = retry_call(lambda: self._client.models.generate_content(
                model=FLASH_LITE, contents=prompt))
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

    def _fetch_search_results(self, topic_names: list) -> str:
        en_keywords = self._extract_english_keywords(topic_names)

        arxiv_query = en_keywords
        arxiv_results = get_cached(arxiv_query)
        if arxiv_results is None:
            try:
                arxiv_results = search_arxiv(en_keywords, max_results=3)
            except Exception:
                arxiv_results = "(arXiv 검색 결과 없음)"
            set_cached(arxiv_query, arxiv_results)

        google_query = f"{' '.join(topic_names[:3])} 최신 연구 동향 응용 사례"
        google_results = get_cached(google_query)
        if google_results is None:
            google_results = search_with_google(google_query)
            set_cached(google_query, google_results)

        return f"[arXiv]\n{arxiv_results}\n\n[Google]\n{google_results}"

    def run(self, input_text: str) -> str:
        data = json.loads(input_text)
        plan_items = data.get("plan_items")

        if plan_items is not None:
            topic_names = [item.get("topic_name", "") for item in plan_items]
            search_results = self._fetch_search_results(topic_names)

            expected = len(plan_items)
            result = None
            for attempt in range(2):
                prompt = APPLICATION_PROMPT_PLAN.format(
                    count=expected,
                    plan_items_text=_format_plan_items_text(plan_items),
                    search_results=search_results,
                )
                response = retry_call(lambda: self._client.models.generate_content(
                    model=FLASH, contents=prompt))
                raw = _extract_json(response.text.strip())
                result = json.loads(raw)
                if len(result) == expected:
                    return raw
                if attempt == 0:
                    print(f"[{self.name}] 개수 불일치 ({len(result)}/{expected}), 재시도")
            result = _adjust_count(result, expected, self.name)
            return json.dumps(result, ensure_ascii=False)

        # Fallback: 구형 topics 배열 형식
        topics = data["topics"]
        search_results = self._fetch_search_results(topics)

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
            response = retry_call(lambda: self._client.models.generate_content(
                model=FLASH, contents=prompt))
            raw = _extract_json(response.text.strip())
            result = json.loads(raw)
            if len(result) == expected:
                return raw
            if attempt == 0:
                print(f"[{self.name}] 개수 불일치 ({len(result)}/{expected}), 재시도")
        result = _adjust_count(result, expected, self.name)
        return json.dumps(result, ensure_ascii=False)
