import json
from agents.base import BaseAgentWorker
from tools.claude_client import claude_generate_text

_IMPORTANCE_NEW = {"core", "supporting", "detail"}
_IMPORTANCE_LEGACY = {"high": "core", "medium": "supporting", "low": "detail"}
_KNOWLEDGE_TYPE_VALUES = {"term", "number", "procedure", "comparison", "causal", "framework", "case"}
_CONCEPT_TYPE_VALUES = {"definition", "term", "number", "abbreviation", "formula", "principle"}
_DIFFICULTY_VALUES = {"easy", "medium", "hard"}
_TF_TRAP_TYPES = {"misconception", "concept_swap", "counterintuitive", "precision", "fatigue"}

PROMPT_TEMPLATE = """다음 강의자료 텍스트를 분석하여 시험 출제에 필요한 최소 구조의 JSON을 작성하세요.

중요: JSON 문자열 값 안에 큰따옴표(")를 사용하지 마시오. 필요하면 작은따옴표(')나 다른 표현으로 대체하세요.
반드시 아래 JSON 형식으로만 응답하세요 (마크다운 코드블록 없이, 다른 텍스트 없이):
{{
  "topics": [
    {{
      "name": "토픽명",
      "importance": "core",
      "difficulty": "medium",
      "knowledge_type": "term",
      "exam_use": ["short", "tf"],
      "source_file": "파일명 또는 unknown",
      "concept_group": "같은 개념군을 묶는 짧은 이름",
      "reason": "출제 가치 한 문장"
    }}
  ],
  "key_concepts": [
    {{
      "term": "개념명",
      "type": "definition",
      "importance": "high",
      "difficulty": "easy",
      "source_topic": "가장 가까운 토픽명 또는 unknown",
      "source_file": "파일명 또는 unknown",
      "concept_group": "같은 개념군을 묶는 짧은 이름 또는 unknown"
    }}
  ],
  "tf_traps": [
    {{
      "type": "misconception",
      "source_topic": "토픽명",
      "statement_seed": "명제로 바꿀 핵심 함정",
      "answer": "F",
      "reason": "왜 F인지"
    }}
  ]
}}

규칙:
- topics: 강의자료 전체를 빠짐없이 슬라이싱하여 최소 15개 이상 작성하라.
  각 토픽은 반드시 단일 개념·단일 방법론·단일 절차·단일 프레임워크 하나에 해당해야 한다.
  여러 개념을 하나의 토픽으로 묶지 말 것 (예: '생산 시스템의 분류와 특성'은 '생산 시스템 분류'와 '각 시스템의 특성' 두 개 토픽으로 나눔).
  섹션 제목이 토픽이 아니라, 섹션 안의 개별 개념, 방법, 특성, 단계가 각각 별도 토픽이다.
  importance 허용값: core (강의 핵심) / supporting (보조) / detail (세부)
  knowledge_type 허용값: term (정의·약어) / number (수식·계산 구조) / procedure (절차·단계) / comparison (비교·대비) / causal (인과) / framework (이론·체계) / case (사례·적용)
  exam_use: 실제로 출제 가능한 문제 유형 선택. 허용값: "short", "tf", "essay", "application"
  difficulty 허용값: easy / medium / hard
  source_file: 강의자료 내 "=== 파일명 ===" 구분자로 식별한 원본 파일명. 구분자가 없거나 알 수 없으면 "unknown".
  concept_group: 같은 개념군·출제 범주를 묶는 짧은 이름. 알 수 없으면 "unknown".
- key_concepts: 단답형 출제용 핵심 약어·용어·정확한 명칭. 지엽적인 수치값 암기는 넣지 말 것.
  type 허용값: definition / term / number / abbreviation / formula / principle
  importance 허용값: high / medium / low
  source_topic/source_file/concept_group은 가능한 한 채우고, 알 수 없으면 "unknown".
- tf_traps: 진위형 함정. 없으면 빈 배열.
  type 허용값: misconception (오해) / concept_swap (개념 바꾸기) / counterintuitive (반직관) / precision (정밀도) / fatigue (피로)
  answer: T 또는 F

강의자료:
{text}"""

_COMPACT_PROMPT = """다음 강의자료를 분석하여 JSON을 출력하세요.
topics는 핵심 토픽 최대 10개만 포함하고, reason은 한 단어 또는 10자 이내로 작성하세요.
JSON 문자열 값 안에 큰따옴표(")를 절대 사용하지 마시오.
마크다운 코드블록 없이 JSON만 출력하세요.

{{"topics":[{{"name":"","importance":"core","difficulty":"medium","knowledge_type":"term","exam_use":["short"],"source_file":"unknown","concept_group":"unknown","reason":""}}],"key_concepts":[{{"term":"","type":"term","importance":"high","difficulty":"medium","source_topic":"unknown","source_file":"unknown","concept_group":"unknown"}}],"tf_traps":[]}}

강의자료:
{text}"""


def _convert_old_tf_fields(tf_misconceptions: list, concept_pairs: list) -> list:
    traps = []
    for m in tf_misconceptions:
        if isinstance(m, str):
            traps.append({"type": "misconception", "source_topic": "",
                          "statement_seed": m, "answer": "F", "reason": ""})
    for cp in concept_pairs:
        if isinstance(cp, dict):
            seed = f"{cp.get('a', '')} vs {cp.get('b', '')}: {cp.get('relation', '')}"
            traps.append({"type": "concept_swap", "source_topic": cp.get("a", ""),
                          "statement_seed": seed, "answer": "F", "reason": ""})
    return traps


def _normalize_topic(topic: dict) -> dict:
    # importance: map old high/medium/low → new core/supporting/detail
    imp = topic.get("importance", "")
    if imp in _IMPORTANCE_LEGACY:
        topic["importance"] = _IMPORTANCE_LEGACY[imp]
    elif imp not in _IMPORTANCE_NEW:
        topic["importance"] = "supporting"

    # difficulty
    if topic.get("difficulty") not in _DIFFICULTY_VALUES:
        topic["difficulty"] = "medium"

    # knowledge_type: use existing if valid, else derive from old specificity/cognitive_type
    kt = topic.get("knowledge_type", "")
    if kt not in _KNOWLEDGE_TYPE_VALUES:
        spec = topic.get("specificity", "")
        cog = topic.get("cognitive_type", "")
        if spec == "numerical" or cog == "quantitative":
            topic["knowledge_type"] = "number"
        elif spec == "procedural" or cog == "procedural":
            topic["knowledge_type"] = "procedure"
        elif cog == "comparative":
            topic["knowledge_type"] = "comparison"
        elif cog == "causal":
            topic["knowledge_type"] = "causal"
        elif spec == "concrete":
            topic["knowledge_type"] = "term"
        else:
            topic["knowledge_type"] = "term"

    # exam_use: use existing if valid list, else derive from old exam_suitability
    eu = topic.get("exam_use")
    if not isinstance(eu, list):
        es = topic.get("exam_suitability", {})
        eu = []
        if isinstance(es, dict):
            if es.get("short_answer", 0) >= 0.5:
                eu.append("short")
            if es.get("essay", 0) >= 0.5:
                eu.append("essay")
            if es.get("application", 0) >= 0.5:
                eu.append("application")
        if topic.get("sequence_dependency") is True:
            if "essay" not in eu:
                eu.append("essay")
            if "application" not in eu:
                eu.append("application")
        topic["exam_use"] = eu

    if "reason" not in topic:
        topic["reason"] = ""
    topic.setdefault("source_file", "unknown")
    topic.setdefault("concept_group", "unknown")
    return topic


def _normalize_concept(concept: dict) -> dict:
    if concept.get("type") not in _CONCEPT_TYPE_VALUES:
        concept["type"] = "term"
    if concept.get("importance") not in {"high", "medium", "low"}:
        concept["importance"] = "medium"
    if concept.get("difficulty") not in _DIFFICULTY_VALUES:
        concept["difficulty"] = "medium"
    concept.setdefault("source_topic", "unknown")
    concept.setdefault("source_file", "unknown")
    concept.setdefault("concept_group", "unknown")
    return concept


def _validate_and_normalize(data: dict) -> dict:
    if not isinstance(data.get("topics"), list) or not isinstance(data.get("key_concepts"), list):
        raise ValueError("Invalid topic extraction JSON: missing topics or key_concepts array")

    # tf_traps: normalize, with backward compat from tf_misconceptions + concept_pairs
    if not isinstance(data.get("tf_traps"), list):
        data["tf_traps"] = _convert_old_tf_fields(
            data.get("tf_misconceptions", []) if isinstance(data.get("tf_misconceptions"), list) else [],
            data.get("concept_pairs", []) if isinstance(data.get("concept_pairs"), list) else [],
        )
    for trap in data["tf_traps"]:
        if not isinstance(trap, dict):
            continue
        if trap.get("type") not in _TF_TRAP_TYPES:
            trap["type"] = "misconception"
        if trap.get("answer") not in ("T", "F"):
            trap["answer"] = "F"
        trap.setdefault("source_topic", "")
        trap.setdefault("statement_seed", "")
        trap.setdefault("reason", "")

    for i, topic in enumerate(data["topics"]):
        if not isinstance(topic, dict) or "name" not in topic:
            raise ValueError(f"Invalid topic extraction JSON: topics[{i}] is not a valid object")
        data["topics"][i] = _normalize_topic(topic)
    for i, concept in enumerate(data["key_concepts"]):
        if not isinstance(concept, dict) or "term" not in concept:
            raise ValueError(f"Invalid topic extraction JSON: key_concepts[{i}] is not a valid object")
        data["key_concepts"][i] = _normalize_concept(concept)
    return data


def _strip_code_fence(raw: str) -> str:
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return raw


def _repair_truncated_json(raw: str) -> str | None:
    """Close unclosed JSON structures caused by output truncation.

    Scans forward tracking bracket/brace/string state. If open structures
    remain at the end, appends the required closing characters. Returns
    the repaired string, or None if the input looks unrecoverable (e.g.
    truncated mid-string with no salvageable content).
    """
    stack: list[str] = []
    in_string = False
    escape = False

    for ch in raw:
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ("{", "["):
            stack.append(ch)
        elif ch in ("}", "]"):
            if stack:
                stack.pop()

    if in_string:
        # Truncated mid-string: close the string then close open structures
        raw = raw + '"'

    if not stack:
        return raw

    closing = "".join("}" if ch == "{" else "]" for ch in reversed(stack))
    return raw + closing


class TopicExtractorAgent(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Topic Extractor", task_id="Task 1")

    def _parse_raw(self, raw: str) -> dict:
        raw = _strip_code_fence(raw)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            repaired = _repair_truncated_json(raw)
            if repaired and repaired != raw:
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass
            raise

    def run(self, input_text: str) -> str:
        prompt = PROMPT_TEMPLATE.format(text=input_text)
        raw = claude_generate_text(prompt, max_tokens=16000)
        try:
            data = self._parse_raw(raw)
        except json.JSONDecodeError:
            # Retry with compact instruction — fewer topics, shorter reasons
            compact_prompt = _COMPACT_PROMPT.format(text=input_text)
            try:
                raw2 = claude_generate_text(compact_prompt, max_tokens=16000)
                data = self._parse_raw(raw2)
            except (json.JSONDecodeError, Exception) as e2:
                raise ValueError(f"Invalid topic extraction JSON: {e2}") from e2

        try:
            data = _validate_and_normalize(data)
        except (ValueError, KeyError) as e:
            raise ValueError(f"Invalid topic extraction JSON: {e}") from e
        return json.dumps(data, ensure_ascii=False)
