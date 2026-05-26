import json
from agents.base import BaseAgentWorker
from tools.client import get_client, retry_call

FLASH = "gemini-2.5-flash"

SYSTEM_PROMPT = """당신은 대학 시험 출제 계획 전문가입니다.
교수자의 요구사항을 분석하여 모든 정보를 JSON으로 정리합니다.
다른 텍스트 없이 JSON만 출력하세요.

규칙:
- 아래 4개 고정 키는 반드시 정확한 이름으로 포함. 명시되지 않은 유형은 0.
  "단답형": <정수>    (키 이름 절대 변경 금지. "단답형 5개" 같은 형태 금지)
  "에세이형": <정수>  (키 이름 절대 변경 금지. "에세이 3개" 같은 형태 금지)
  "응용형": <정수>    (키 이름 절대 변경 금지)
  "난이도": "easy|medium|hard|mixed"
- 시험지 표지/포맷 관련 정보는 아래 정해진 키 이름을 사용:
  "시험제목": "시험지 제목"  (명시된 경우에만 포함)
  "시험종류": "중간고사|기말고사|퀴즈|과제|기타"  (명시된 경우에만 포함)
  "담당교수": "교수 이름"  (명시된 경우에만 포함)
  "레이아웃": "페이지당 문제 1개" 또는 "여러 문제"  (명시된 경우에만 포함)
- 토픽 목록은 절대 JSON에 포함하지 않음 (입력으로 받지만 출력에는 제외)
- 그 외 파악되는 추가 요구사항은 직관적인 한국어 키로 추가. 없으면 포함하지 않음.

예시 입력: "단답형 5개, 에세이형 3개. 시험 제목 Scientific Management, 중간고사, 담당교수 박우진, 페이지당 문제 1개"
예시 출력: {{"단답형": 5, "에세이형": 3, "응용형": 0, "난이도": "medium", "시험제목": "Scientific Management", "시험종류": "중간고사", "담당교수": "박우진", "레이아웃": "페이지당 문제 1개"}}"""

# LLM이 고정 키를 변형해 출력해도 복구하는 정규화
_KEY_FRAGMENTS = {"단답": "단답형", "에세이": "에세이형", "응용": "응용형"}


def _normalize_plan(plan: dict) -> dict:
    result = {}
    for k, v in plan.items():
        canonical = next((c for frag, c in _KEY_FRAGMENTS.items() if frag in k and k != c), None)
        result[canonical if canonical else k] = v
    for key in ("단답형", "에세이형", "응용형"):
        result.setdefault(key, 0)
    result.setdefault("난이도", "mixed")
    return result


def _score_topic(topic: dict, qtype: str) -> float:
    """토픽 메타데이터를 기반으로 문제 유형별 적합도 점수를 계산."""
    suitability = topic.get("exam_suitability", {})
    spec = topic.get("specificity", "")
    cog = topic.get("cognitive_type", "")
    seq_dep = topic.get("sequence_dependency", False)
    imp = topic.get("importance", "medium")
    scope = topic.get("scope", "core")
    diff = topic.get("difficulty", "medium")

    base = suitability.get(qtype, 0.5)
    boost = 0.0

    if qtype == "short_answer":
        if spec == "numerical" or cog == "quantitative":
            boost += 0.3
        if spec == "concrete":
            boost += 0.1
    elif qtype == "essay":
        if cog in ("causal", "comparative", "qualitative") or spec == "abstract":
            boost += 0.2
        if imp == "high" and scope == "core":
            boost += 0.1
        if seq_dep:
            boost += 0.1
    elif qtype == "application":
        if cog in ("procedural", "causal", "comparative"):
            boost += 0.2
        if seq_dep:
            boost += 0.2
        if diff == "hard":
            boost += 0.1

    return base + boost


def _build_plan_items(topics: list, key_concepts: list, counts: dict) -> list:
    """메타데이터 기반 라우팅으로 question_plan 항목 리스트를 생성."""
    if not topics:
        return []

    n_short = counts.get("단답형", 0)
    n_essay = counts.get("에세이형", 0)
    n_app = counts.get("응용형", 0)

    def sorted_pool(qtype: str) -> list:
        scored = sorted(topics, key=lambda t: _score_topic(t, qtype), reverse=True)
        # high importance core 토픽을 앞에 배치해 반드시 포함되게 함
        core_high = [t for t in scored if t.get("importance") == "high" and t.get("scope") == "core"]
        rest = [t for t in scored if not (t.get("importance") == "high" and t.get("scope") == "core")]
        return core_high + rest

    def make_item(qtype: str, topic: dict, target: str) -> dict:
        return {
            "question_type": qtype,
            "topic_name": topic.get("name", ""),
            "target_concept": target,
            "difficulty": topic.get("difficulty", "medium"),
            "reason": topic.get("reason", ""),
            "topic_meta": {k: v for k, v in topic.items() if k != "name"},
        }

    plan = []

    # 단답형: key_concept을 target으로, topic을 맥락으로 사용
    short_pool = sorted_pool("short_answer")
    kc_sorted = sorted(key_concepts, key=lambda kc: 0 if kc.get("importance") == "high" else 1)
    for i in range(n_short):
        t = short_pool[i % len(short_pool)]
        target = kc_sorted[i % len(kc_sorted)]["term"] if kc_sorted else t.get("name", "")
        plan.append(make_item("short_answer", t, target))

    # 서술형: 점수 높은 토픽 순으로 배치
    essay_pool = sorted_pool("essay")
    for i in range(n_essay):
        t = essay_pool[i % len(essay_pool)]
        plan.append(make_item("essay", t, t.get("reason", t.get("name", ""))))

    # 응용형: 점수 높은 토픽 순으로 배치
    app_pool = sorted_pool("application")
    for i in range(n_app):
        t = app_pool[i % len(app_pool)]
        plan.append(make_item("application", t, t.get("reason", t.get("name", ""))))

    return plan


def _parse_input(input_text: str):
    """입력을 파싱해 (requirements_str, topics, key_concepts)를 반환.
    새 형식: {"topic_extraction": {...}, "requirements": "..."}
    구형 fallback: 평문 문자열."""
    try:
        data = json.loads(input_text)
        if isinstance(data, dict) and "topic_extraction" in data:
            extraction = data["topic_extraction"]
            topics = extraction.get("topics", [])
            key_concepts = extraction.get("key_concepts", [])
            # 구형 문자열 배열 topics/key_concepts → 객체 배열로 변환 (하위 호환)
            if topics and isinstance(topics[0], str):
                topics = [
                    {"name": t, "importance": "medium", "scope": "core",
                     "specificity": "abstract", "cognitive_type": "qualitative",
                     "difficulty": "medium", "sequence_dependency": False,
                     "exam_suitability": {"short_answer": 0.5, "essay": 0.5, "application": 0.5},
                     "reason": ""}
                    for t in topics
                ]
            if key_concepts and isinstance(key_concepts[0], str):
                key_concepts = [
                    {"term": kc, "type": "term", "importance": "medium", "difficulty": "medium"}
                    for kc in key_concepts
                ]
            return data.get("requirements", ""), topics, key_concepts
    except (json.JSONDecodeError, TypeError):
        pass
    return input_text, [], []


class PlannerAgent(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Question Planner", task_id="Task 2")
        self._client = get_client()
        self._chat = self._client.chats.create(
            model=FLASH,
            config={"system_instruction": SYSTEM_PROMPT},
        )

    def run(self, input_text: str) -> str:
        requirements, topics, key_concepts = _parse_input(input_text)

        response = retry_call(lambda: self._chat.send_message(requirements))
        raw = response.text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        plan = _normalize_plan(json.loads(raw))

        # 메타데이터가 있으면 question_plan을 생성해 plan에 포함
        if topics:
            plan["question_plan"] = _build_plan_items(topics, key_concepts, plan)

        return json.dumps(plan, ensure_ascii=False)
