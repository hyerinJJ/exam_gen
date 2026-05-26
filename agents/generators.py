import json
from agents.base import BaseAgentWorker
from tools.client import get_client, retry_call
from tools.claude_client import claude_generate_text
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
출제 유형: 용어/개념형만 출제할 것. 답이 반드시 단어 또는 짧은 용어 하나여야 하는 문제만 생성하세요.

출제 원칙:
- 핵심 개념을 응축한 수치·약어·용어를 묻는 문제를 우선할 것
- {count}개 중 1~2개는 유사 용어 구별, 약어 세부 등 변별 문제로 구성할 것
- 절차·순서가 있는 개념은 "몇 번째 단계" 또는 "직전/직후 단계"를 직접 묻는 문제를 출제할 것
- 같은 개념을 두 문제에서 반복 출제하지 말 것
- 문제 지시문은 한국어로 작성할 것. 영어 전문용어·약어·프레임워크명 원어 병기는 허용한다.
- 마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오.

나쁜 예시 (절대 금지): 나열 요구("~을 3가지 쓰시오"), 서술 요구("정의를 설명하시오"), 같은 개념 반복

반드시 아래 JSON 배열 형식으로만 응답하세요:
[{{"id": "Q1", "type": "short", "question": "..."}}]"""

ESSAY_PROMPT = """다음 토픽과 조건으로 서술(에세이)형 문제 {count}개를 생성하세요.
토픽: {topics}
난이도: {difficulty}
{scope_line}
출제 원칙:
- 한 문항에 하나의 사고 작업만 요구할 것. 관계·차이·인과·의의 중 하나의 초점만 묻는다.
- 세 가지 유형을 골고루 출제할 것.
유형 1: 절차·순서를 묻는 문제
유형 2: 두 개념의 관계·차이·인과·의의를 대비하는 문제 (소문항 3개까지 가능)
유형 3: 계산 및 수식을 이용하는 문제 (소문항 3개까지 가능)
- 같은 개념을 두 문제에서 반복 출제하지 말 것.
- 문제 지시문은 한국어로 작성할 것. 영어 전문용어·약어·프레임워크명 원어 병기는 허용한다.
- 마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오.

반드시 아래 JSON 배열 형식으로만 응답하세요:
[{{"id": "Q1", "type": "essay", "question": "..."}}]"""

APPLICATION_PROMPT = """다음 토픽과 조건으로 응용형 문제 {count}개를 생성하세요.
토픽: {topics}
난이도: {difficulty}
{scope_line}참고 자료:
{search_results}

출제 원칙:
- 구조: 시나리오 3~4줄 + 질문 1개. 질문이 2개 이상이면 안 됨.
- 학생이 적용해야 할 수업 개념·프레임워크를 문제 본문 안에 명시할 것.
  (예: "수업에서 배운 Work System Framework를 적용하여 분석하시오.")
- 강의 자료와 다른 새로운 맥락(응급실·편의점·대학 행정 등)을 시나리오로 사용할 것.
- 기술·인간·조직 간의 갈등 구조를 시나리오에 심을 것.
- 같은 개념을 두 문제에서 반복 출제하지 말 것.
- 문제 지시문은 한국어로 작성할 것. 영어 전문용어·약어·프레임워크명 원어 병기는 허용한다.
- 마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오.

반드시 아래 JSON 배열 형식으로만 응답하세요:
[{{"id": "Q1", "type": "application", "question": "..."}}]"""


SHORT_PROMPT_PLAN = """다음 출제 계획에 따라 단답형 문제 {count}개를 생성하세요.
각 항목 순서대로 정확히 한 문제씩 출제하세요.

출제 계획:
{plan_items_text}

메타데이터 반영 지침:
- specificity=numerical: 수치·공식·정확한 값을 직접 묻는 문제
- specificity=concrete: 구체적 사례나 명칭을 확인하는 문제
- cognitive_type=quantitative: 계산·수치 결과를 묻는 문제
- cognitive_type=procedural: 단계·순서를 묻는 문제
- difficulty=hard: 유사 용어 구별, 약어 세부, 정확한 수치 등 변별 포인트
- importance=high: 강의 핵심 개념, 반드시 제대로 된 문제를 출제할 것

출제 유형: 용어/개념형만 출제할 것. 답이 반드시 단어 또는 짧은 용어 하나여야 하는 문제만 생성하세요.

출제 원칙:
- 핵심 개념을 응축한 수치·약어·용어를 묻는 문제를 우선할 것
- {count}개 중 1~2개는 유사 용어 구별, 약어 세부 등 변별 문제로 구성할 것
- 절차·순서가 있는 개념은 "몇 번째 단계" 또는 "직전/직후 단계"를 직접 묻는 문제를 출제할 것
- 같은 개념을 두 문제에서 반복 출제하지 말 것
- 문제 지시문은 한국어로 작성할 것. 영어 전문용어·약어·프레임워크명 원어 병기는 허용한다.
- 마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오.

나쁜 예시 (절대 금지): 나열 요구("~을 3가지 쓰시오"), 서술 요구("정의를 설명하시오"), 같은 개념 반복

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
- sequence_dependency=true: 전제 개념과의 연관성을 설명하게 하는 문제
- difficulty=hard: 비판적 분석이나 종합적 이해가 필요한 심층 질문
- importance=high, scope=core: 반드시 포함해야 할 핵심 개념

출제 원칙:
- 세 가지 유형을 골고루 출제할 것.
유형 1: 절차·순서를 묻는 문제
유형 2: 두 개념의 관계·차이·인과·의의를 대비하는 문제 (소문항 3개까지 가능)
유형 3: 계산 및 수식을 이용하는 문제 (소문항 3개까지 가능)
- 같은 개념을 두 문제에서 반복 출제하지 말 것.
- 문제 지시문은 한국어로 작성할 것. 영어 전문용어·약어·프레임워크명 원어 병기는 허용한다.
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
- difficulty=hard: 기술·인간·조직 간 갈등이 있는 복잡한 시나리오
- importance=high: 강의 핵심 개념이 반드시 답안의 근거가 되어야 함

출제 원칙:
- 구조: 시나리오 3~4줄 + 질문 1개. 질문이 2개 이상이면 안 됨.
- 학생이 적용해야 할 수업 개념·프레임워크를 문제 본문 안에 명시할 것.
  (예: "수업에서 배운 Work System Framework를 적용하여 분석하시오.")
- 강의 자료와 다른 새로운 맥락(응급실·편의점·대학 행정 등)을 시나리오로 사용할 것.
- 기술·인간·조직 간의 갈등 구조를 시나리오에 심을 것.
- 같은 개념을 두 문제에서 반복 출제하지 말 것.
- 문제 지시문은 한국어로 작성할 것. 영어 전문용어·약어·프레임워크명 원어 병기는 허용한다.
- 마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오.

반드시 아래 JSON 배열 형식으로만 응답하세요:
[{{"id": "Q1", "type": "application", "question": "..."}}]"""


TF_PROMPT = """다음 토픽과 조건으로 진위형 문제 {count}개를 생성하세요.
토픽: {topics}
난이도: {difficulty}
{scope_line}
T/F 배분: T {n_t}개, F {n_f}개.

출제 원칙:
- 한 문장, 한 가지 사실만 담는다. 끝은 "(T/F)"로 통일한다.
- 모든 문항은 "그럴듯한 오답(F)" 또는 "의심스럽지만 맞는 정답(T)"으로 구성한다.
- 강의에서 실제 사용된 용어를 유지하고 지시문은 한국어로 작성할 것.
- "~할 수 있다", "~경우도 있다" 같은 지나치게 약한 표현은 피한다.
- 한 문항에 두 사실을 넣지 않는다. 황당한 F와 동일 개념 반복 금지.
- 강의 흐름 순서대로 배치하고 마지막 1~2개는 강의 전체 메시지를 부정하는 F로 둔다.
- 마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오.

반드시 아래 JSON 배열 형식으로만 응답하세요:
[{{"id": "Q1", "type": "tf", "question": "..."}}]"""

TF_PROMPT_PLAN = """다음 출제 계획에 따라 진위형 문제 {count}개를 생성하세요.
각 항목 순서대로 정확히 한 문제씩 출제하세요.

출제 계획:
{plan_items_text}

메타데이터 반영 지침:
- tf_type=오해 직격: 강의에서 경계한 오해를 명제로 만든 F. misconception_hint가 있으면 활용할 것.
- tf_type=개념쌍 바꿔치기: A/B 개념 설명을 서로 바꿔 붙인 F. concept_pair_hint가 있으면 활용할 것.
- tf_type=반직관 정답: 의심스럽지만 강의 기준으로 맞는 T
- tf_type=정의 정밀도 확인: 정확히 알아야 판단 가능한 T/F
- tf_type=피로 함정: 강의 전체 메시지를 부정하는 F (마지막에 배치)
- intended_answer=T/F: 이 문항의 정답 방향

출제 원칙:
- 한 문장, 한 가지 사실만 담는다. 끝은 "(T/F)"로 통일한다.
- 모든 문항은 "그럴듯한 오답(F)" 또는 "의심스럽지만 맞는 정답(T)"으로 구성한다.
- 강의에서 실제 사용된 용어를 유지하고 지시문은 한국어로 작성할 것.
- "~할 수 있다", "~경우도 있다" 같은 지나치게 약한 표현은 피한다.
- 한 문항에 두 사실을 넣지 않는다. 황당한 F와 동일 개념 반복 금지.
- 마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오.

반드시 아래 JSON 배열 형식으로만 응답하세요:
[{{"id": "Q1", "type": "tf", "question": "..."}}]"""


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
        line = (
            f"{i}. 토픽: {item.get('topic_name', '')} | "
            f"핵심 개념: {item.get('target_concept', '')} | "
            f"난이도: {item.get('difficulty', '-')} | "
            f"중요도: {meta.get('importance', '-')} | "
            f"범위: {meta.get('scope', '-')} | "
            f"구체성: {meta.get('specificity', '-')} | "
            f"인지유형: {meta.get('cognitive_type', '-')} | "
            f"출제이유: {item.get('reason', '-')}"
        )
        if item.get("tf_type"):
            line += f" | TF유형: {item['tf_type']}"
        if item.get("intended_answer"):
            line += f" | 정답방향: {item['intended_answer']}"
        if item.get("misconception_hint"):
            line += f" | 오해힌트: {item['misconception_hint']}"
        if item.get("concept_pair_hint"):
            line += f" | 개념쌍: {item['concept_pair_hint']}"
        lines.append(line)
    return "\n".join(lines)


def _inject_grading_seed(results: list, plan_items: list) -> None:
    """plan_items 메타데이터로 grading_seed를 생성해 results에 in-place 주입."""
    for q, item in zip(results, plan_items):
        q_type = item.get("question_type", "")
        if q_type == "short_answer":
            q["grading_seed"] = {
                "expected_answer": item.get("target_concept", ""),
                "accepted_variants": [],
            }
        elif q_type == "essay":
            tc = item.get("target_concept", "")
            q["grading_seed"] = {
                "answer_direction": item.get("reason", ""),
                "must_include": [tc] if tc else [],
                "rubric_focus": [],
            }
        elif q_type == "application":
            q["grading_seed"] = {
                "target_framework": item.get("target_concept", ""),
                "scenario_mapping": [],
                "expected_reasoning": item.get("reason", ""),
                "rubric_focus": [],
            }
        elif q_type == "tf":
            seed: dict = {
                "expected_answer": item.get("intended_answer", ""),
                "trap": item.get("tf_type", ""),
            }
            reason = item.get("misconception_hint") or item.get("concept_pair_hint") or ""
            if reason:
                seed["reason"] = reason
            q["grading_seed"] = seed


class ShortAnswerGenerator(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Short Answer Generator", task_id="Task 3a")

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
                raw = _extract_json(claude_generate_text(prompt))
                result = json.loads(raw)
                if len(result) == expected:
                    break
                if attempt == 0:
                    print(f"[{self.name}] 개수 불일치 ({len(result)}/{expected}), 재시도")
            result = _adjust_count(result, expected, self.name)
            _inject_grading_seed(result, plan_items)
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
            raw = _extract_json(claude_generate_text(prompt))
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
                raw = _extract_json(claude_generate_text(prompt))
                result = json.loads(raw)
                if len(result) == expected:
                    break
                if attempt == 0:
                    print(f"[{self.name}] 개수 불일치 ({len(result)}/{expected}), 재시도")
            result = _adjust_count(result, expected, self.name)
            _inject_grading_seed(result, plan_items)
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
            raw = _extract_json(claude_generate_text(prompt))
            result = json.loads(raw)
            if len(result) == expected:
                return raw
            if attempt == 0:
                print(f"[{self.name}] 개수 불일치 ({len(result)}/{expected}), 재시도")
        result = _adjust_count(result, expected, self.name)
        return json.dumps(result, ensure_ascii=False)


class TFGenerator(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="TF Generator", task_id="Task 3d")

    def run(self, input_text: str) -> str:
        data = json.loads(input_text)
        plan_items = data.get("plan_items")

        if plan_items is not None:
            expected = len(plan_items)
            result = None
            for attempt in range(2):
                prompt = TF_PROMPT_PLAN.format(
                    count=expected,
                    plan_items_text=_format_plan_items_text(plan_items),
                )
                raw = _extract_json(claude_generate_text(prompt))
                result = json.loads(raw)
                if len(result) == expected:
                    break
                if attempt == 0:
                    print(f"[{self.name}] 개수 불일치 ({len(result)}/{expected}), 재시도")
            result = _adjust_count(result, expected, self.name)
            _inject_grading_seed(result, plan_items)
            return json.dumps(result, ensure_ascii=False)

        # Fallback
        expected = data["count"]
        n_t = max(1, round(expected * 0.35)) if expected >= 2 else 1
        n_f = expected - n_t
        result = None
        for attempt in range(2):
            prompt = TF_PROMPT.format(
                topics=", ".join(data["topics"]),
                count=expected,
                difficulty=data.get("difficulty", "mixed"),
                scope_line=_scope_line(data),
                n_t=n_t,
                n_f=n_f,
            )
            raw = _extract_json(claude_generate_text(prompt))
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
                    break
                if attempt == 0:
                    print(f"[{self.name}] 개수 불일치 ({len(result)}/{expected}), 재시도")
            result = _adjust_count(result, expected, self.name)
            _inject_grading_seed(result, plan_items)
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
