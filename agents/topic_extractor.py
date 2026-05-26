import json
from agents.base import BaseAgentWorker
from tools.claude_client import claude_generate_text

_IMPORTANCE_VALUES = {"high", "medium", "low"}
_SCOPE_VALUES = {"core", "detail", "example", "background"}
_SPECIFICITY_VALUES = {"abstract", "concrete", "procedural", "numerical"}
_COGNITIVE_TYPE_VALUES = {"qualitative", "quantitative", "procedural", "comparative", "causal"}
_DIFFICULTY_VALUES = {"easy", "medium", "hard"}
_CONCEPT_TYPE_VALUES = {"definition", "term", "number", "abbreviation", "formula", "principle"}

PROMPT_TEMPLATE = """다음 강의자료 텍스트를 분석하여 시험 출제를 위한 심층 분석을 수행하세요.

아래 4단계를 내부적으로 수행한 후, 그 결과를 바탕으로 JSON을 작성하세요.
(4단계 분석 내용 자체는 JSON 출력에 포함하지 않음)

[STEP 1] 강조 신호 추출
색상 강조·단독 슬라이드 한 문장·3회 이상 반복 개념·"핵심은/중요한 것은/반드시" 표현이 붙은 내용을 식별할 것.

[STEP 2] 강의 구조 파악
핵심 메시지 1문장, 강의 흐름(예: 개념 정의→역사→방법론→적용), 개념 간 관계(인과·대비)를 파악할 것.

[STEP 3] 출제 후보 도출
- 단답형 후보: 핵심 수치·약어·용어 중 의미를 응축한 것 7개 이상
- 서술형 후보: 두 개념 이상이 연결되는 지점
- 응용형 후보: 프레임워크를 새로운 맥락에 적용할 수 있는 상황
- 진위형 후보: 강의에서 명시적으로 경계한 오해, 혼동되기 쉬운 개념쌍

[STEP 4] 토픽 분석 관점 적용
각 토픽에 대해 아래 7가지 관점을 평가할 것:
- importance: 강의에서 중요하게 다루어지는가 (high/medium/low)
- scope: 핵심인가·세부사항인가·예시인가·배경인가 (core/detail/example/background)
- specificity: 추상적·구체적·절차적·수치적 중 무엇인가 (abstract/concrete/procedural/numerical)
- cognitive_type: 정성적·정량적·절차적·비교적·인과적 중 무엇인가 (qualitative/quantitative/procedural/comparative/causal)
- difficulty: 기본 개념·중간·상위 변별 (easy/medium/hard)
- sequence_dependency: 앞선 개념을 알아야만 이해 가능한가 (true/false)
- exam_suitability: 단답형/서술형/응용형 문제 적합도 (각 0.0~1.0)

반드시 아래 JSON 형식으로만 응답하세요 (마크다운 코드블록 없이, 다른 텍스트 없이):
{{
  "topics": [
    {{
      "name": "토픽명",
      "importance": "high",
      "scope": "core",
      "specificity": "abstract",
      "cognitive_type": "qualitative",
      "difficulty": "medium",
      "sequence_dependency": false,
      "exam_suitability": {{
        "short_answer": 0.8,
        "essay": 0.9,
        "application": 0.6
      }},
      "reason": "강의에서 반복 강조되며 다른 개념의 기반이 됨"
    }}
  ],
  "key_concepts": [
    {{
      "term": "개념명",
      "type": "definition",
      "importance": "high",
      "difficulty": "easy"
    }}
  ],
  "tf_misconceptions": [
    "강의에서 경계한 오해 예시"
  ],
  "concept_pairs": [
    {{"a": "개념A", "b": "개념B", "relation": "대비"}}
  ]
}}

규칙:
- topics: 강의자료의 각 섹션·개념·방법론·프레임워크를 개별 토픽으로 최소 7개 이상.
  STEP 1~2에서 강조된 내용을 우선 반영. STEP 4 관점으로 각 토픽을 분석.
  importance 허용값: high / medium / low
  scope 허용값: core / detail / example / background
  specificity 허용값: abstract / concrete / procedural / numerical
  cognitive_type 허용값: qualitative / quantitative / procedural / comparative / causal
  difficulty 허용값: easy / medium / hard
- key_concepts: STEP 3 단답형 후보에서 선별한 핵심 수치·약어·용어.
  type 허용값: definition / term / number / abbreviation / formula / principle
  importance 허용값: high / medium / low
  difficulty 허용값: easy / medium / hard
- tf_misconceptions: STEP 3 진위형 후보 중 강의에서 명시적으로 경계한 오해 목록. 문자열 배열. 없으면 빈 배열.
- concept_pairs: 대비되거나 혼동되기 쉬운 개념쌍. 각 항목은 {{"a", "b", "relation"}} 객체. 없으면 빈 배열.

강의자료:
{text}"""


def _normalize_topic(topic: dict) -> dict:
    if topic.get("importance") not in _IMPORTANCE_VALUES:
        topic["importance"] = "medium"
    if topic.get("scope") not in _SCOPE_VALUES:
        topic["scope"] = "core"
    if topic.get("specificity") not in _SPECIFICITY_VALUES:
        topic["specificity"] = "abstract"
    if topic.get("cognitive_type") not in _COGNITIVE_TYPE_VALUES:
        topic["cognitive_type"] = "qualitative"
    if topic.get("difficulty") not in _DIFFICULTY_VALUES:
        topic["difficulty"] = "medium"
    if not isinstance(topic.get("sequence_dependency"), bool):
        topic["sequence_dependency"] = False
    if not isinstance(topic.get("exam_suitability"), dict):
        topic["exam_suitability"] = {"short_answer": 0.5, "essay": 0.5, "application": 0.5}
    if "reason" not in topic:
        topic["reason"] = ""
    return topic


def _normalize_concept(concept: dict) -> dict:
    if concept.get("type") not in _CONCEPT_TYPE_VALUES:
        concept["type"] = "term"
    if concept.get("importance") not in _IMPORTANCE_VALUES:
        concept["importance"] = "medium"
    if concept.get("difficulty") not in _DIFFICULTY_VALUES:
        concept["difficulty"] = "medium"
    return concept


def _validate_and_normalize(data: dict) -> dict:
    if not isinstance(data.get("topics"), list) or not isinstance(data.get("key_concepts"), list):
        raise ValueError("Invalid topic extraction JSON: missing topics or key_concepts array")
    if not isinstance(data.get("tf_misconceptions"), list):
        data["tf_misconceptions"] = []
    if not isinstance(data.get("concept_pairs"), list):
        data["concept_pairs"] = []
    for i, topic in enumerate(data["topics"]):
        if not isinstance(topic, dict) or "name" not in topic:
            raise ValueError(f"Invalid topic extraction JSON: topics[{i}] is not a valid object")
        data["topics"][i] = _normalize_topic(topic)
    for i, concept in enumerate(data["key_concepts"]):
        if not isinstance(concept, dict) or "term" not in concept:
            raise ValueError(f"Invalid topic extraction JSON: key_concepts[{i}] is not a valid object")
        data["key_concepts"][i] = _normalize_concept(concept)
    return data


class TopicExtractorAgent(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Topic Extractor", task_id="Task 1")

    def run(self, input_text: str) -> str:
        prompt = PROMPT_TEMPLATE.format(text=input_text)
        raw = claude_generate_text(prompt)
        # JSON 블록 추출
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid topic extraction JSON: {e}") from e
        data = _validate_and_normalize(data)
        return json.dumps(data, ensure_ascii=False)
