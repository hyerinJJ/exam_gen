import json
from agents.base import BaseAgentWorker
from tools.client import get_client, retry_call

FLASH = "gemini-2.5-flash"

SYSTEM_PROMPT = """당신은 대학 시험 출제 계획 전문가입니다.
교수자의 요구사항을 분석하여 모든 정보를 JSON으로 정리합니다.
다른 텍스트 없이 JSON만 출력하세요.

규칙:
- 아래 5개 고정 키는 반드시 정확한 이름으로 포함. 명시되지 않은 유형은 0.
  "단답형": <정수>    (키 이름 절대 변경 금지. "단답형 5개" 같은 형태 금지)
  "에세이형": <정수>  (키 이름 절대 변경 금지. "에세이 3개" 같은 형태 금지)
  "응용형": <정수>    (키 이름 절대 변경 금지)
  "진위형": <정수>    (키 이름 절대 변경 금지. "TF", "T/F", "True/False", "참거짓", "진위형"을 모두 인식할 것)
  "난이도": "easy|medium|hard|mixed"
- 시험지 표지/포맷 관련 정보는 아래 정해진 키 이름을 사용:
  "과목명": "한글 과목명"  (명시된 경우에만 포함)
  "영문명": "영문 과목명"  (명시된 경우에만 포함)
  "시험제목": "시험지 제목"  (과목명과 별도 제목이 명시된 경우에만 포함)
  "년도": "2026학년도"  (명시된 경우에만 포함)
  "학기": "1학기"  (명시된 경우에만 포함)
  "시험종류": "중간고사|기말고사|퀴즈|과제|기타"  (명시된 경우에만 포함)
  "시험일시": "시험 일시"  (명시된 경우에만 포함)
  "제한시간": "제한시간"  (명시된 경우에만 포함)
  "총점": <정수>  (명시된 경우에만 포함)
  "담당교수": "교수 이름"  (명시된 경우에만 포함)
  "레이아웃": "페이지당 문제 1개" 또는 "여러 문제"  (명시된 경우에만 포함)
- 토픽 목록은 절대 JSON에 포함하지 않음 (입력으로 받지만 출력에는 제외)
- 그 외 파악되는 추가 요구사항은 직관적인 한국어 키로 추가. 없으면 포함하지 않음.

예시 입력: "단답형 5개, 에세이형 3개. 시험 치는 과목: 한글 - 과학적 관리, 영어 - Scientific Management. 년도 / 학기: 2026학년도 1학기. 중간고사, 담당교수 박우진, 페이지당 문제 1개"
예시 출력: {{"단답형": 5, "에세이형": 3, "응용형": 0, "진위형": 0, "난이도": "medium", "과목명": "과학적 관리", "영문명": "Scientific Management", "년도": "2026학년도", "학기": "1학기", "시험종류": "중간고사", "담당교수": "박우진", "레이아웃": "페이지당 문제 1개"}}"""

_KEY_FRAGMENTS = {
    "단답": "단답형", "에세이": "에세이형", "응용": "응용형",
    "진위": "진위형", "TF": "진위형", "T/F": "진위형", "참거짓": "진위형",
}

# knowledge_type 유형별 친화도 (문제 유형 → 적합한 knowledge_type 집합)
_TYPE_AFFINITY = {
    "short_answer": {"term"},
    "tf": {"term", "comparison", "causal", "procedure"},
    "essay": {"number", "comparison", "causal", "framework"},
    "application": {"framework", "case", "procedure"},
}

_TRAP_TYPE_TO_TF_TYPE = {
    "misconception": "오해 직격",
    "concept_swap": "개념쌍 바꿔치기",
    "counterintuitive": "반직관 정답",
    "precision": "정의 정밀도 확인",
    "fatigue": "피로 함정",
}


def _desired_tf_true_count(n_tf: int) -> int:
    """진위형 전체 문항에서 의도할 T 정답 수를 계산."""
    if n_tf < 2:
        return 0
    return min(n_tf - 1, max(1, round(n_tf * 0.35)))


def _tf_answer_sequence(n_tf: int) -> list[str]:
    """T/F 정답 방향을 미리 섞은 순서로 만든다."""
    target_t = _desired_tf_true_count(n_tf)
    sequence = []
    made_t = 0
    for i in range(n_tf):
        should_have_t = round((i + 1) * target_t / n_tf) if n_tf else 0
        if made_t < should_have_t:
            sequence.append("T")
            made_t += 1
        else:
            sequence.append("F")
    return sequence


def _split_tf_traps(tf_traps: list | None) -> dict:
    queues = {"T": [], "F": []}
    for trap in tf_traps or []:
        answer = trap.get("answer", "F")
        queues["T" if answer == "T" else "F"].append(trap)
    return queues


def _normalize_plan(plan: dict) -> dict:
    result = {}
    for k, v in plan.items():
        canonical = next((c for frag, c in _KEY_FRAGMENTS.items() if frag in k and k != c), None)
        result[canonical if canonical else k] = v
    for key in ("단답형", "에세이형", "응용형", "진위형"):
        result.setdefault(key, 0)
    result.setdefault("난이도", "mixed")
    return result


def _score_topic(topic: dict, qtype: str) -> float:
    """토픽 메타데이터를 기반으로 문제 유형별 적합도 점수를 계산."""
    exam_use = topic.get("exam_use", [])
    kt = topic.get("knowledge_type", "term")
    imp = topic.get("importance", "supporting")
    diff = topic.get("difficulty", "medium")

    # exam_use 직접 일치: 해당 유형이 exam_use 리스트에 있으면 높은 기본 점수
    type_short = {"short_answer": "short", "tf": "tf", "essay": "essay", "application": "application"}
    use_key = type_short.get(qtype, qtype)
    base = 0.8 if use_key in exam_use else 0.3

    # knowledge_type 친화도 보너스
    affinity = _TYPE_AFFINITY.get(qtype, set())
    boost = 0.2 if kt in affinity else 0.0

    # importance 보너스
    if imp == "core":
        boost += 0.1

    # 응용형/에세이형에서 hard 난이도 소폭 우대
    if qtype in ("application", "essay") and diff == "hard":
        boost += 0.05

    return base + boost


def _bump(counter: dict, key: str) -> None:
    key = key or "unknown"
    counter[key] = counter.get(key, 0) + 1


def _usage(counter: dict, key: str) -> int:
    return counter.get(key or "unknown", 0)


def _build_plan_items(topics: list, key_concepts: list, counts: dict,
                      tf_traps: list = None) -> list:
    """메타데이터 기반 라우팅으로 question_plan 항목 리스트를 생성."""
    if not topics:
        return []

    n_short = counts.get("단답형", 0)
    n_essay = counts.get("에세이형", 0)
    n_app = counts.get("응용형", 0)
    n_tf = counts.get("진위형", 0)

    def sorted_pool(qtype: str) -> list:
        scored = sorted(topics, key=lambda t: _score_topic(t, qtype), reverse=True)
        # core 토픽을 앞에 배치해 반드시 포함되게 함
        core = [t for t in scored if t.get("importance") == "core"]
        rest = [t for t in scored if t.get("importance") != "core"]
        return core + rest

    def make_item(qtype: str, topic: dict, target: str) -> dict:
        return {
            "question_type": qtype,
            "topic_name": topic.get("name", ""),
            "target_concept": target,
            "difficulty": topic.get("difficulty", "medium"),
            "reason": topic.get("reason", ""),
            "topic_meta": {k: v for k, v in topic.items() if k not in ("name", "source_file")},
        }

    global_usage = {
        "topic_name": {},
        "concept_group": {},
        "source_topic": {},
        "knowledge_type": {},
        "source_file": {},
    }
    per_type_source_usage: dict = {}

    def pick_balanced(pool: list, qtype: str) -> dict:
        type_counter = per_type_source_usage.setdefault(qtype, {})
        if len(pool) == 1:
            chosen = pool[0]
        else:
            def adjusted(t: dict) -> float:
                topic_name = t.get("name", "unknown")
                concept_group = t.get("concept_group", "unknown")
                source_topic = t.get("source_topic", concept_group)
                knowledge_type = t.get("knowledge_type", "term")
                sf = t.get("source_file", "unknown")
                penalty = (
                    0.25 * _usage(global_usage["topic_name"], topic_name)
                    + 0.12 * _usage(global_usage["concept_group"], concept_group)
                    + 0.12 * _usage(global_usage["source_topic"], source_topic)
                    + 0.04 * _usage(global_usage["knowledge_type"], knowledge_type)
                    + 0.05 * _usage(global_usage["source_file"], sf)
                    + 0.03 * _usage(type_counter, sf)
                )
                return _score_topic(t, qtype) - penalty
            chosen = max(pool, key=adjusted)
        _bump(global_usage["topic_name"], chosen.get("name", "unknown"))
        _bump(global_usage["concept_group"], chosen.get("concept_group", "unknown"))
        _bump(global_usage["source_topic"], chosen.get("source_topic", chosen.get("concept_group", "unknown")))
        _bump(global_usage["knowledge_type"], chosen.get("knowledge_type", "term"))
        _bump(global_usage["source_file"], chosen.get("source_file", "unknown"))
        _bump(type_counter, chosen.get("source_file", "unknown"))
        return chosen

    concept_usage = {
        "concept_group": {},
        "source_topic": {},
        "source_file": {},
        "type": {},
    }

    def pick_key_concept(candidates: list) -> dict | None:
        if not candidates:
            return None

        def score(kc: dict) -> float:
            imp = kc.get("importance", "medium")
            base = {"high": 1.0, "medium": 0.65, "low": 0.35}.get(imp, 0.65)
            concept_group = kc.get("concept_group", "unknown")
            source_topic = kc.get("source_topic", "unknown")
            source_file = kc.get("source_file", "unknown")
            ctype = kc.get("type", "term")
            penalty = (
                0.12 * _usage(concept_usage["concept_group"], concept_group)
                + 0.10 * _usage(concept_usage["source_topic"], source_topic)
                + 0.06 * _usage(concept_usage["source_file"], source_file)
                + 0.05 * _usage(concept_usage["type"], ctype)
                + 0.08 * _usage(global_usage["concept_group"], concept_group)
            )
            return base - penalty

        chosen = max(candidates, key=score)
        _bump(concept_usage["concept_group"], chosen.get("concept_group", "unknown"))
        _bump(concept_usage["source_topic"], chosen.get("source_topic", "unknown"))
        _bump(concept_usage["source_file"], chosen.get("source_file", "unknown"))
        _bump(concept_usage["type"], chosen.get("type", "term"))
        _bump(global_usage["concept_group"], chosen.get("concept_group", "unknown"))
        _bump(global_usage["source_topic"], chosen.get("source_topic", "unknown"))
        _bump(global_usage["source_file"], chosen.get("source_file", "unknown"))
        _bump(global_usage["knowledge_type"], chosen.get("type", "term"))
        return chosen

    plan = []

    # 단답형: key_concept을 target으로, topic을 맥락으로 사용
    short_pool = sorted_pool("short_answer")
    for i in range(n_short):
        t = pick_balanced(short_pool, "short_answer")
        kc = pick_key_concept(key_concepts)
        target = kc["term"] if kc else t.get("name", "")
        plan.append(make_item("short_answer", t, target))

    # 서술형: 점수 높은 토픽 순으로 배치
    essay_pool = sorted_pool("essay")
    for i in range(n_essay):
        t = pick_balanced(essay_pool, "essay")
        plan.append(make_item("essay", t, t.get("reason", t.get("name", ""))))

    # 응용형: 점수 높은 토픽 순으로 배치
    app_pool = sorted_pool("application")
    for i in range(n_app):
        t = pick_balanced(app_pool, "application")
        plan.append(make_item("application", t, t.get("reason", t.get("name", ""))))

    # 진위형: tf_traps 우선 활용, 소진 후 위치 기반 배분으로 fallback
    if n_tf > 0:
        answer_slots = _tf_answer_sequence(n_tf)
        n_fatigue = min(2, max(1, n_tf // 5)) if n_tf >= 5 else 0
        tf_pool = sorted_pool("tf")
        _TF_F_TYPES = ["오해 직격", "개념쌍 바꿔치기", "정의 정밀도 확인"]
        trap_queues = _split_tf_traps(tf_traps)
        f_seen = 0

        for i, intended_answer in enumerate(answer_slots):
            t = pick_balanced(tf_pool, "tf")
            item = make_item("tf", t, t.get("reason", t.get("name", "")))
            trap = trap_queues[intended_answer].pop(0) if trap_queues[intended_answer] else None

            if trap:
                trap_type = trap.get("type", "")
                item["tf_type"] = _TRAP_TYPE_TO_TF_TYPE.get(trap_type, "오해 직격")
                item["intended_answer"] = intended_answer
                seed = trap.get("statement_seed", "")
                if trap_type == "misconception" and seed:
                    item["misconception_hint"] = seed
                elif trap_type == "concept_swap" and seed:
                    item["concept_pair_hint"] = seed
                elif trap_type == "counterintuitive" and seed:
                    item["misconception_hint"] = seed
            elif intended_answer == "T":
                item["tf_type"] = "반직관 정답"
                item["intended_answer"] = "T"
            else:
                remaining_f = answer_slots[i:].count("F")
                if remaining_f <= n_fatigue:
                    item["tf_type"] = "피로 함정"
                    item["intended_answer"] = "F"
                else:
                    item["tf_type"] = _TF_F_TYPES[f_seen % len(_TF_F_TYPES)]
                    item["intended_answer"] = "F"
                f_seen += 1
            plan.append(item)

    return plan


def _parse_input(input_text: str):
    """입력을 파싱해 (requirements_str, topics, key_concepts, tf_traps)를 반환."""
    try:
        data = json.loads(input_text)
        if isinstance(data, dict) and "topic_extraction" in data:
            extraction = data["topic_extraction"]
            topics = extraction.get("topics", [])
            key_concepts = extraction.get("key_concepts", [])
            # 구형 문자열 배열 → 객체 배열로 변환 (하위 호환)
            if topics and isinstance(topics[0], str):
                topics = [
                    {"name": t, "importance": "supporting", "difficulty": "medium",
                     "knowledge_type": "term", "exam_use": [], "source_file": "unknown",
                     "concept_group": "unknown", "reason": ""}
                    for t in topics
                ]
            if key_concepts and isinstance(key_concepts[0], str):
                key_concepts = [
                    {"term": kc, "type": "term", "importance": "medium", "difficulty": "medium",
                     "source_topic": "unknown", "source_file": "unknown", "concept_group": "unknown"}
                    for kc in key_concepts
                ]
            # tf_traps: new field first, then backward compat from old fields
            tf_traps = extraction.get("tf_traps")
            if tf_traps is None:
                from agents.topic_extractor import _convert_old_tf_fields
                tf_traps = _convert_old_tf_fields(
                    extraction.get("tf_misconceptions", []) if isinstance(extraction.get("tf_misconceptions"), list) else [],
                    extraction.get("concept_pairs", []) if isinstance(extraction.get("concept_pairs"), list) else [],
                )
            return data.get("requirements", ""), topics, key_concepts, tf_traps
    except (json.JSONDecodeError, TypeError):
        pass
    return input_text, [], [], []


class PlannerAgent(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Question Planner", task_id="Task 2")
        self._client = get_client()
        self._chat = self._client.chats.create(
            model=FLASH,
            config={"system_instruction": SYSTEM_PROMPT},
        )

    def run(self, input_text: str) -> str:
        requirements, topics, key_concepts, tf_traps = _parse_input(input_text)

        response = retry_call(lambda: self._chat.send_message(requirements))
        raw = response.text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        plan = _normalize_plan(json.loads(raw))

        if topics:
            plan["question_plan"] = _build_plan_items(
                topics, key_concepts, plan, tf_traps
            )

        return json.dumps(plan, ensure_ascii=False)
