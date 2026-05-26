# tests/test_agents.py
import json
import pytest
from unittest.mock import MagicMock, patch


# ── TopicExtractor 샘플 데이터 ────────────────────────────────────────────────

SAMPLE_OUTPUT = {
    "topics": [
        {
            "name": "머신러닝 개요",
            "importance": "high",
            "scope": "core",
            "specificity": "abstract",
            "cognitive_type": "qualitative",
            "difficulty": "easy",
            "sequence_dependency": False,
            "exam_suitability": {"short_answer": 0.7, "essay": 0.9, "application": 0.5},
            "reason": "강의 전반에 걸쳐 기반이 되는 개념",
        },
        {
            "name": "지도학습",
            "importance": "high",
            "scope": "core",
            "specificity": "concrete",
            "cognitive_type": "procedural",
            "difficulty": "medium",
            "sequence_dependency": True,
            "exam_suitability": {"short_answer": 0.8, "essay": 0.7, "application": 0.9},
            "reason": "실습과 연결되는 핵심 방법론",
        },
        {
            "name": "비지도학습",
            "importance": "medium",
            "scope": "core",
            "specificity": "abstract",
            "cognitive_type": "comparative",
            "difficulty": "medium",
            "sequence_dependency": True,
            "exam_suitability": {"short_answer": 0.6, "essay": 0.8, "application": 0.7},
            "reason": "지도학습과 대비되는 개념",
        },
    ],
    "key_concepts": [
        {"term": "과적합", "type": "definition", "importance": "high", "difficulty": "medium"},
        {"term": "학습률", "type": "number", "importance": "medium", "difficulty": "hard"},
    ],
}


def _run_extractor(output_dict, raw_text=None):
    text = raw_text if raw_text is not None else json.dumps(output_dict, ensure_ascii=False)
    with patch("agents.topic_extractor.claude_generate_text", return_value=text):
        from agents.topic_extractor import TopicExtractorAgent
        agent = TopicExtractorAgent()
        return json.loads(agent.run("샘플 강의 텍스트"))


# ── TopicExtractor 테스트 ─────────────────────────────────────────────────────

def test_topics_are_object_array():
    result = _run_extractor(SAMPLE_OUTPUT)
    assert isinstance(result["topics"], list)
    assert len(result["topics"]) > 0
    assert all(isinstance(t, dict) for t in result["topics"])
    assert all("name" in t for t in result["topics"])


def test_topic_allowed_values():
    result = _run_extractor(SAMPLE_OUTPUT)
    importance_values = {"high", "medium", "low"}
    scope_values = {"core", "detail", "example", "background"}
    difficulty_values = {"easy", "medium", "hard"}
    for topic in result["topics"]:
        assert topic["importance"] in importance_values, f"importance={topic['importance']!r} not allowed"
        assert topic["scope"] in scope_values, f"scope={topic['scope']!r} not allowed"
        assert topic["difficulty"] in difficulty_values, f"difficulty={topic['difficulty']!r} not allowed"


def test_key_concepts_are_object_array():
    result = _run_extractor(SAMPLE_OUTPUT)
    concept_type_values = {"definition", "term", "number", "abbreviation", "formula", "principle"}
    assert isinstance(result["key_concepts"], list)
    assert len(result["key_concepts"]) > 0
    for concept in result["key_concepts"]:
        assert isinstance(concept, dict)
        assert "term" in concept
        assert concept["type"] in concept_type_values, f"type={concept['type']!r} not allowed"


def test_markdown_codeblock_parsing():
    json_str = json.dumps(SAMPLE_OUTPUT, ensure_ascii=False)
    wrapped = f"```json\n{json_str}\n```"
    result = _run_extractor(SAMPLE_OUTPUT, raw_text=wrapped)
    assert isinstance(result["topics"], list)
    assert isinstance(result["key_concepts"], list)


def test_invalid_enum_values_normalized():
    bad_output = {
        "topics": [
            {
                "name": "정규화 테스트",
                "importance": "INVALID",
                "scope": "INVALID",
                "specificity": "INVALID",
                "cognitive_type": "INVALID",
                "difficulty": "INVALID",
                "sequence_dependency": "yes",
                "exam_suitability": "not_a_dict",
                "reason": "보정 테스트",
            }
        ],
        "key_concepts": [
            {"term": "테스트 개념", "type": "INVALID", "importance": "INVALID", "difficulty": "INVALID"}
        ],
    }
    result = _run_extractor(bad_output)
    topic = result["topics"][0]
    assert topic["importance"] == "medium"
    assert topic["scope"] == "core"
    assert topic["difficulty"] == "medium"
    assert topic["sequence_dependency"] is False
    assert isinstance(topic["exam_suitability"], dict)
    concept = result["key_concepts"][0]
    assert concept["type"] == "term"
    assert concept["importance"] == "medium"


# ── Planner 라우팅 테스트 ─────────────────────────────────────────────────────

# 라우팅 테스트용 토픽 fixtures
_NUMERICAL_TOPIC = {
    "name": "수치 개념",
    "importance": "medium", "scope": "core",
    "specificity": "numerical", "cognitive_type": "quantitative",
    "difficulty": "medium", "sequence_dependency": False,
    "exam_suitability": {"short_answer": 0.7, "essay": 0.2, "application": 0.3},
    "reason": "수치 암기",
}
_CAUSAL_TOPIC = {
    "name": "인과 개념",
    "importance": "high", "scope": "core",
    "specificity": "abstract", "cognitive_type": "causal",
    "difficulty": "hard", "sequence_dependency": False,
    "exam_suitability": {"short_answer": 0.2, "essay": 0.9, "application": 0.8},
    "reason": "인과 관계 분석",
}
_SEQ_DEP_TOPIC = {
    "name": "절차 개념",
    "importance": "medium", "scope": "core",
    "specificity": "procedural", "cognitive_type": "procedural",
    "difficulty": "medium", "sequence_dependency": True,
    "exam_suitability": {"short_answer": 0.3, "essay": 0.5, "application": 0.5},
    "reason": "절차 이해",
}
_CORE_HIGH_TOPIC = {
    "name": "핵심 개념 A",
    "importance": "high", "scope": "core",
    "specificity": "abstract", "cognitive_type": "qualitative",
    "difficulty": "medium", "sequence_dependency": False,
    "exam_suitability": {"short_answer": 0.5, "essay": 0.9, "application": 0.5},
    "reason": "강의 핵심",
}
_LOW_IMPORTANCE_TOPIC = {
    "name": "세부 개념 B",
    "importance": "low", "scope": "detail",
    "specificity": "concrete", "cognitive_type": "quantitative",
    "difficulty": "easy", "sequence_dependency": False,
    "exam_suitability": {"short_answer": 0.9, "essay": 0.3, "application": 0.2},
    "reason": "세부 사항",
}


def test_score_numerical_higher_for_short_answer():
    """numerical/quantitative 토픽은 short_answer 점수가 causal보다 높아야 함."""
    from agents.planner import _score_topic
    assert _score_topic(_NUMERICAL_TOPIC, "short_answer") > _score_topic(_CAUSAL_TOPIC, "short_answer")


def test_score_causal_higher_for_essay():
    """causal 토픽은 essay 점수가 numerical보다 높아야 함."""
    from agents.planner import _score_topic
    assert _score_topic(_CAUSAL_TOPIC, "essay") > _score_topic(_NUMERICAL_TOPIC, "essay")


def test_score_seq_dep_boosts_essay_and_application():
    """sequence_dependency=true이면 essay, application 점수가 올라야 함."""
    from agents.planner import _score_topic
    no_dep = {**_SEQ_DEP_TOPIC, "sequence_dependency": False}
    assert _score_topic(_SEQ_DEP_TOPIC, "essay") > _score_topic(no_dep, "essay")
    assert _score_topic(_SEQ_DEP_TOPIC, "application") > _score_topic(no_dep, "application")


def test_plan_includes_core_high_topic():
    """high importance core 토픽이 question_plan에 반드시 포함되어야 함."""
    from agents.planner import _build_plan_items
    topics = [_CORE_HIGH_TOPIC, _LOW_IMPORTANCE_TOPIC]
    counts = {"단답형": 1, "에세이형": 1, "응용형": 0, "난이도": "mixed"}
    plan = _build_plan_items(topics, [], counts)
    topic_names = [item["topic_name"] for item in plan]
    assert "핵심 개념 A" in topic_names


def test_plan_picks_numerical_for_short_answer():
    """short_answer 슬롯은 numerical/quantitative 토픽이 우선 선택되어야 함 (같은 중요도 티어 내)."""
    from agents.planner import _build_plan_items
    # 두 토픽 모두 medium importance로 같은 티어에 놓아 점수 기반 선택을 테스트
    numerical = {**_NUMERICAL_TOPIC, "importance": "medium"}
    causal = {**_CAUSAL_TOPIC, "importance": "medium"}
    topics = [causal, numerical]  # causal을 앞에 넣어 순서 의존성 제거
    counts = {"단답형": 1, "에세이형": 0, "응용형": 0, "난이도": "mixed"}
    plan = _build_plan_items(topics, [], counts)
    assert len(plan) == 1
    assert plan[0]["question_type"] == "short_answer"
    assert plan[0]["topic_name"] == "수치 개념"


def test_plan_picks_causal_for_essay():
    """essay 슬롯은 causal 토픽이 numerical보다 우선 선택되어야 함."""
    from agents.planner import _build_plan_items
    topics = [_NUMERICAL_TOPIC, _CAUSAL_TOPIC]
    counts = {"단답형": 0, "에세이형": 1, "응용형": 0, "난이도": "mixed"}
    plan = _build_plan_items(topics, [], counts)
    assert len(plan) == 1
    assert plan[0]["question_type"] == "essay"
    assert plan[0]["topic_name"] == "인과 개념"


def test_plan_seq_dep_goes_to_application():
    """sequence_dependency=true 토픽은 application 슬롯으로 우선 배치되어야 함."""
    from agents.planner import _build_plan_items
    # seq_dep_topic vs numerical (낮은 application score)
    topics = [_NUMERICAL_TOPIC, _SEQ_DEP_TOPIC]
    counts = {"단답형": 0, "에세이형": 0, "응용형": 1, "난이도": "mixed"}
    plan = _build_plan_items(topics, [], counts)
    assert len(plan) == 1
    assert plan[0]["question_type"] == "application"
    assert plan[0]["topic_name"] == "절차 개념"


def test_plan_uses_key_concepts_for_short_target():
    """단답형 plan_item의 target_concept은 key_concept에서 가져와야 함."""
    from agents.planner import _build_plan_items
    topics = [_NUMERICAL_TOPIC]
    key_concepts = [{"term": "특정 수치", "type": "number", "importance": "high", "difficulty": "medium"}]
    counts = {"단답형": 1, "에세이형": 0, "응용형": 0, "난이도": "mixed"}
    plan = _build_plan_items(topics, key_concepts, counts)
    assert plan[0]["target_concept"] == "특정 수치"


# ── Generator 메타데이터 프롬프트 테스트 ──────────────────────────────────────

_SAMPLE_PLAN_ITEMS = [
    {
        "question_type": "short_answer",
        "topic_name": "경사하강법",
        "target_concept": "학습률",
        "difficulty": "medium",
        "reason": "핵심 수치 이해",
        "topic_meta": {
            "importance": "high",
            "scope": "core",
            "specificity": "numerical",
            "cognitive_type": "quantitative",
            "difficulty": "medium",
            "sequence_dependency": False,
            "exam_suitability": {"short_answer": 0.9, "essay": 0.5, "application": 0.4},
        },
    }
]


def _captured_prompt(generator_cls, plan_items, module_path):
    """mock으로 generator를 실행하고 LLM에 전달된 프롬프트를 반환."""
    mock_text = json.dumps([{"id": "Q1", "type": "short", "question": "테스트 문제?"}])
    with patch(f"{module_path}.claude_generate_text", return_value=mock_text) as mock_claude:
        agent = generator_cls()
        agent.run(json.dumps({"plan_items": plan_items}))
    return " ".join(str(call.args[0]) for call in mock_claude.call_args_list)


def test_short_generator_prompt_contains_metadata():
    """ShortAnswerGenerator가 plan_items 형식일 때 프롬프트에 메타데이터가 포함되어야 함."""
    from agents.generators import ShortAnswerGenerator
    prompt_text = _captured_prompt(ShortAnswerGenerator, _SAMPLE_PLAN_ITEMS, "agents.generators")
    assert "경사하강법" in prompt_text
    assert "학습률" in prompt_text
    # specificity 또는 cognitive_type 정보가 프롬프트에 포함되어야 함
    assert "numerical" in prompt_text or "quantitative" in prompt_text


def test_essay_generator_prompt_contains_metadata():
    """EssayGenerator가 plan_items 형식일 때 프롬프트에 메타데이터가 포함되어야 함."""
    essay_plan = [
        {
            **_SAMPLE_PLAN_ITEMS[0],
            "question_type": "essay",
            "topic_meta": {
                **_SAMPLE_PLAN_ITEMS[0]["topic_meta"],
                "cognitive_type": "causal",
                "specificity": "abstract",
            },
        }
    ]
    mock_text = json.dumps([{"id": "Q1", "type": "essay", "question": "테스트?"}])
    with patch("agents.generators.claude_generate_text", return_value=mock_text) as mock_claude:
        from agents.generators import EssayGenerator
        agent = EssayGenerator()
        agent.run(json.dumps({"plan_items": essay_plan}))

    all_prompts = " ".join(str(call.args[0]) for call in mock_claude.call_args_list)
    assert "경사하강법" in all_prompts
    assert "causal" in all_prompts or "abstract" in all_prompts


# ── TF 관련 테스트 ────────────────────────────────────────────────────────────

_SAMPLE_OUTPUT_WITH_TF = {
    **SAMPLE_OUTPUT,
    "tf_misconceptions": ["머신러닝은 항상 지도학습을 기반으로 한다"],
    "concept_pairs": [{"a": "지도학습", "b": "비지도학습", "relation": "대비"}],
}

_CONCRETE_TOPIC = {
    "name": "구체 개념",
    "importance": "high", "scope": "core",
    "specificity": "concrete", "cognitive_type": "comparative",
    "difficulty": "medium", "sequence_dependency": False,
    "exam_suitability": {"short_answer": 0.5, "essay": 0.4, "application": 0.5},
    "reason": "구체 사실 확인",
}


def test_extractor_tf_fields():
    """topic_extractor 출력에 tf_misconceptions과 concept_pairs가 리스트로 포함되어야 함."""
    result = _run_extractor(_SAMPLE_OUTPUT_WITH_TF)
    assert isinstance(result["tf_misconceptions"], list)
    assert isinstance(result["concept_pairs"], list)
    assert len(result["tf_misconceptions"]) > 0
    assert len(result["concept_pairs"]) > 0


def test_extractor_tf_fields_default_empty():
    """tf_misconceptions/concept_pairs가 없으면 빈 리스트로 정규화되어야 함."""
    result = _run_extractor(SAMPLE_OUTPUT)
    assert isinstance(result["tf_misconceptions"], list)
    assert isinstance(result["concept_pairs"], list)


def test_planner_tf_plan():
    """진위형 count가 있으면 question_type='tf' 항목이 생성되어야 함."""
    from agents.planner import _build_plan_items
    topics = [_CONCRETE_TOPIC, _NUMERICAL_TOPIC]
    counts = {"단답형": 0, "에세이형": 0, "응용형": 0, "진위형": 3, "난이도": "mixed"}
    plan = _build_plan_items(topics, [], counts)
    tf_items = [item for item in plan if item["question_type"] == "tf"]
    assert len(tf_items) == 3
    for item in tf_items:
        assert "intended_answer" in item
        assert item["intended_answer"] in ("T", "F")
        assert "tf_type" in item


def test_planner_tf_tf_ratio():
    """T:F 비율이 대략 35:65를 따라야 함 (10개 기준)."""
    from agents.planner import _build_plan_items
    topics = [_CONCRETE_TOPIC, _NUMERICAL_TOPIC]
    counts = {"단답형": 0, "에세이형": 0, "응용형": 0, "진위형": 10, "난이도": "mixed"}
    plan = _build_plan_items(topics, [], counts)
    tf_items = [item for item in plan if item["question_type"] == "tf"]
    t_count = sum(1 for i in tf_items if i["intended_answer"] == "T")
    f_count = sum(1 for i in tf_items if i["intended_answer"] == "F")
    assert t_count <= 4 and f_count >= 6


def test_tf_generator_type():
    """TFGenerator 출력의 모든 항목이 type='tf'여야 함."""
    mock_text = json.dumps([
        {"id": "Q1", "type": "tf", "question": "머신러닝은 데이터에서 패턴을 학습한다. (T/F)"},
        {"id": "Q2", "type": "tf", "question": "비지도학습은 레이블이 필요하다. (T/F)"},
    ])
    with patch("agents.generators.claude_generate_text", return_value=mock_text):
        from agents.generators import TFGenerator
        agent = TFGenerator()
        result = json.loads(agent.run(json.dumps({"topics": ["머신러닝"], "count": 2, "difficulty": "medium"})))
    assert all(q["type"] == "tf" for q in result)


def test_tf_question_format():
    """TFGenerator 출력의 문제는 '(T/F)'로 끝나야 함."""
    mock_text = json.dumps([
        {"id": "Q1", "type": "tf", "question": "머신러닝은 데이터에서 패턴을 학습한다. (T/F)"},
    ])
    with patch("agents.generators.claude_generate_text", return_value=mock_text):
        from agents.generators import TFGenerator
        agent = TFGenerator()
        result = json.loads(agent.run(json.dumps({"topics": ["머신러닝"], "count": 1, "difficulty": "medium"})))
    assert result[0]["question"].strip().endswith("(T/F)")


def test_tf_answer_normalize():
    """_normalize_tf_answer가 다양한 입력을 T 또는 F로 정규화해야 함."""
    from agents.answer_generator import _normalize_tf_answer
    assert _normalize_tf_answer("T") == "T"
    assert _normalize_tf_answer("TRUE") == "T"
    assert _normalize_tf_answer("참") == "T"
    assert _normalize_tf_answer("O") == "T"
    assert _normalize_tf_answer("F") == "F"
    assert _normalize_tf_answer("FALSE") == "F"
    assert _normalize_tf_answer("거짓") == "F"
    assert _normalize_tf_answer("X") == "F"
    assert _normalize_tf_answer("  t  ") == "T"
    assert _normalize_tf_answer("True (참)") == "T"


def test_quality_reviewer_tf_criteria():
    """REVIEW_PROMPT에 진위형 검토 기준이 포함되어야 함."""
    from agents.quality_reviewer import REVIEW_PROMPT
    assert "진위형" in REVIEW_PROMPT
    assert "(T/F)" in REVIEW_PROMPT
    assert "단일 명제" in REVIEW_PROMPT


def test_file_writers_tf_type():
    """TYPE_KO에 'tf' 키가 '진위형'으로 등록되어야 함."""
    from tools.file_writers import TYPE_KO
    assert "tf" in TYPE_KO
    assert TYPE_KO["tf"] == "진위형"
