# tests/test_agents.py
import json
import pytest
from unittest.mock import MagicMock, patch


# ── TopicExtractor 샘플 데이터 ────────────────────────────────────────────────

SAMPLE_OUTPUT = {
    "topics": [
        {
            "name": "머신러닝 개요",
            "importance": "core",
            "difficulty": "easy",
            "knowledge_type": "framework",
            "exam_use": ["short", "essay"],
            "reason": "강의 전반에 걸쳐 기반이 되는 개념",
        },
        {
            "name": "지도학습",
            "importance": "core",
            "difficulty": "medium",
            "knowledge_type": "procedure",
            "exam_use": ["short", "essay", "application"],
            "reason": "실습과 연결되는 핵심 방법론",
        },
        {
            "name": "비지도학습",
            "importance": "supporting",
            "difficulty": "medium",
            "knowledge_type": "comparison",
            "exam_use": ["essay", "tf"],
            "reason": "지도학습과 대비되는 개념",
        },
    ],
    "key_concepts": [
        {"term": "과적합", "type": "definition", "importance": "high", "difficulty": "medium"},
        {"term": "학습률", "type": "number", "importance": "medium", "difficulty": "hard"},
    ],
    "tf_traps": [],
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
    importance_values = {"core", "supporting", "detail"}
    knowledge_type_values = {"term", "number", "procedure", "comparison", "causal", "framework", "case"}
    difficulty_values = {"easy", "medium", "hard"}
    for topic in result["topics"]:
        assert topic["importance"] in importance_values, f"importance={topic['importance']!r} not allowed"
        assert topic["knowledge_type"] in knowledge_type_values, f"knowledge_type={topic['knowledge_type']!r} not allowed"
        assert topic["difficulty"] in difficulty_values, f"difficulty={topic['difficulty']!r} not allowed"
        assert isinstance(topic.get("exam_use"), list), "exam_use must be a list"


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
                "difficulty": "INVALID",
                "knowledge_type": "INVALID",
                "exam_use": "not_a_list",
                "reason": "보정 테스트",
            }
        ],
        "key_concepts": [
            {"term": "테스트 개념", "type": "INVALID", "importance": "INVALID", "difficulty": "INVALID"}
        ],
        "tf_traps": [],
    }
    result = _run_extractor(bad_output)
    topic = result["topics"][0]
    assert topic["importance"] == "supporting"
    assert topic["difficulty"] == "medium"
    assert topic["knowledge_type"] == "term"
    assert isinstance(topic["exam_use"], list)
    concept = result["key_concepts"][0]
    assert concept["type"] == "term"
    assert concept["importance"] == "medium"


# ── source_file 정규화 테스트 ────────────────────────────────────────────────

def test_topic_source_file_defaults_to_unknown():
    """topics에 source_file이 없으면 'unknown'으로 채워져야 함."""
    output = {
        "topics": [{"name": "테스트", "importance": "core", "difficulty": "medium",
                    "knowledge_type": "term", "exam_use": [], "reason": ""}],
        "key_concepts": [],
        "tf_traps": [],
    }
    result = _run_extractor(output)
    assert result["topics"][0]["source_file"] == "unknown"


def test_topic_source_file_preserved():
    """topics에 source_file이 있으면 그대로 유지되어야 함."""
    output = {
        "topics": [{"name": "테스트", "importance": "core", "difficulty": "medium",
                    "knowledge_type": "term", "exam_use": [], "reason": "",
                    "source_file": "lecture1.pdf"}],
        "key_concepts": [],
        "tf_traps": [],
    }
    result = _run_extractor(output)
    assert result["topics"][0]["source_file"] == "lecture1.pdf"


def test_topic_concept_group_defaults_to_unknown():
    """topics에 concept_group이 없으면 'unknown'으로 채워져야 함."""
    output = {
        "topics": [{"name": "테스트", "importance": "core", "difficulty": "medium",
                    "knowledge_type": "term", "exam_use": [], "reason": ""}],
        "key_concepts": [],
        "tf_traps": [],
    }
    result = _run_extractor(output)
    assert result["topics"][0]["concept_group"] == "unknown"


def test_topic_slicer_attaches_relevant_evidence():
    """raw_text를 파일/페이지 단위로 나누고 topic에 관련 근거 텍스트를 붙인다."""
    from agents.topic_slicer import attach_topic_evidence
    raw = (
        "=== lecture1.pdf ===\n"
        "[페이지 1]\nWork System Framework는 participants, information, technologies를 포함한다.\n\n"
        "[페이지 2]\n전혀 다른 내용\n\n"
        "=== lecture2.pdf ===\n"
        "[페이지 1]\nScientific Management 내용"
    )
    topics = [{
        "name": "Work System Framework",
        "source_file": "lecture1.pdf",
        "concept_group": "work system",
        "importance": "core",
        "difficulty": "medium",
        "knowledge_type": "framework",
        "exam_use": ["essay", "application"],
        "reason": "프레임워크 적용",
    }]
    result = attach_topic_evidence(raw, topics)
    assert result[0]["topic_id"] == "topic_1"
    assert "participants" in result[0]["evidence_text"]
    assert any("lecture1.pdf" in ref for ref in result[0]["source_refs"])


def test_key_concept_source_metadata_defaults_to_unknown():
    """key_concepts에 source metadata가 없으면 기본값을 채워야 함."""
    output = {
        "topics": [{"name": "테스트", "importance": "core", "difficulty": "medium",
                    "knowledge_type": "term", "exam_use": [], "reason": ""}],
        "key_concepts": [{"term": "핵심 용어", "type": "term",
                          "importance": "high", "difficulty": "medium"}],
        "tf_traps": [],
    }
    result = _run_extractor(output)
    concept = result["key_concepts"][0]
    assert concept["source_topic"] == "unknown"
    assert concept["source_file"] == "unknown"
    assert concept["concept_group"] == "unknown"


def test_plan_source_file_balanced_equal_score():
    """동일 점수 topic 사이에서 pick_balanced가 source_file을 분산시켜야 함."""
    from agents.planner import _build_plan_items
    base = {"importance": "supporting", "difficulty": "medium",
            "knowledge_type": "comparison", "exam_use": ["essay"], "reason": ""}
    topics = [
        {**base, "name": "A1", "source_file": "file_a.pdf"},
        {**base, "name": "A2", "source_file": "file_a.pdf"},
        {**base, "name": "A3", "source_file": "file_a.pdf"},
        {**base, "name": "B1", "source_file": "file_b.pdf"},
    ]
    counts = {"단답형": 0, "에세이형": 2, "응용형": 0, "난이도": "mixed"}
    plan = _build_plan_items(topics, [], counts)
    # 1st pick: A1 (all tied, stable order). file_a counter=1.
    # 2nd pick: B1 wins (file_b penalty=0 vs file_a penalty=0.05).
    topic_names = [item["topic_name"] for item in plan]
    assert "B1" in topic_names


def test_plan_concept_group_balanced_equal_score():
    """동일 점수 topic 사이에서 concept_group 반복이 감점되어야 함."""
    from agents.planner import _build_plan_items
    base = {"importance": "supporting", "difficulty": "medium",
            "knowledge_type": "comparison", "exam_use": ["essay"], "reason": "",
            "source_file": "same.pdf"}
    topics = [
        {**base, "name": "A1", "concept_group": "group_a"},
        {**base, "name": "A2", "concept_group": "group_a"},
        {**base, "name": "B1", "concept_group": "group_b"},
    ]
    counts = {"단답형": 0, "에세이형": 2, "응용형": 0, "난이도": "mixed"}
    plan = _build_plan_items(topics, [], counts)
    topic_names = [item["topic_name"] for item in plan]
    assert "B1" in topic_names


def test_plan_keeps_source_evidence_in_topic_meta():
    """plan_item의 topic_meta에는 답안 근거 검색용 source/evidence가 보존되어야 함."""
    from agents.planner import _build_plan_items
    topic = {"name": "테스트", "importance": "core", "difficulty": "medium",
             "knowledge_type": "framework", "exam_use": ["essay"], "reason": "",
             "source_file": "secret.pdf", "evidence_text": "강의 근거"}
    plan = _build_plan_items([topic], [], {"단답형": 0, "에세이형": 1, "응용형": 0})
    assert plan[0]["topic_meta"]["source_file"] == "secret.pdf"
    assert plan[0]["topic_meta"]["evidence_text"] == "강의 근거"


# ── 하위 호환 정규화 테스트 ────────────────────────────────────────────────────

def test_backward_compat_importance_old_to_new():
    """구형 importance(high/medium/low)가 새 값(core/supporting/detail)으로 정규화되어야 함."""
    old_output = {
        "topics": [
            {"name": "핵심", "importance": "high", "difficulty": "medium",
             "knowledge_type": "term", "exam_use": [], "reason": ""},
            {"name": "보조", "importance": "medium", "difficulty": "easy",
             "knowledge_type": "term", "exam_use": [], "reason": ""},
            {"name": "세부", "importance": "low", "difficulty": "hard",
             "knowledge_type": "term", "exam_use": [], "reason": ""},
        ],
        "key_concepts": [],
        "tf_traps": [],
    }
    result = _run_extractor(old_output)
    importances = [t["importance"] for t in result["topics"]]
    assert importances == ["core", "supporting", "detail"]


def test_backward_compat_old_fields_to_knowledge_type():
    """구형 specificity/cognitive_type/exam_suitability 필드가 knowledge_type/exam_use로 변환되어야 함."""
    old_output = {
        "topics": [
            {
                "name": "수식 개념",
                "importance": "medium",
                "scope": "core",
                "specificity": "numerical",
                "cognitive_type": "quantitative",
                "difficulty": "medium",
                "sequence_dependency": False,
                "exam_suitability": {"short_answer": 0.9, "essay": 0.3, "application": 0.2},
                "reason": "",
            }
        ],
        "key_concepts": [],
        "tf_traps": [],
    }
    result = _run_extractor(old_output)
    t = result["topics"][0]
    assert t["knowledge_type"] == "number"
    assert "short" in t["exam_use"]
    assert "essay" not in t["exam_use"]
    assert t["importance"] == "supporting"


def test_backward_compat_old_tf_fields_to_tf_traps():
    """구형 tf_misconceptions/concept_pairs가 있으면 tf_traps로 변환되어야 함."""
    old_output = {
        "topics": [{"name": "테스트", "importance": "core", "difficulty": "medium",
                    "knowledge_type": "term", "exam_use": [], "reason": ""}],
        "key_concepts": [],
        "tf_misconceptions": ["머신러닝은 항상 지도학습이다"],
        "concept_pairs": [{"a": "지도학습", "b": "비지도학습", "relation": "대비"}],
    }
    result = _run_extractor(old_output)
    assert isinstance(result["tf_traps"], list)
    assert len(result["tf_traps"]) == 2
    types = {t["type"] for t in result["tf_traps"]}
    assert "misconception" in types
    assert "concept_swap" in types


# ── Planner 라우팅 테스트 ─────────────────────────────────────────────────────

_NUMERICAL_TOPIC = {
    "name": "수식 개념",
    "importance": "supporting", "difficulty": "medium",
    "knowledge_type": "number",
    "exam_use": ["essay"],
    "reason": "수식 구조 이해",
}
_CAUSAL_TOPIC = {
    "name": "인과 개념",
    "importance": "core", "difficulty": "hard",
    "knowledge_type": "causal",
    "exam_use": ["essay", "application"],
    "reason": "인과 관계 분석",
}
_PROCEDURE_TOPIC = {
    "name": "절차 개념",
    "importance": "supporting", "difficulty": "medium",
    "knowledge_type": "procedure",
    "exam_use": ["essay", "application"],
    "reason": "절차 이해",
}
_CORE_HIGH_TOPIC = {
    "name": "핵심 개념 A",
    "importance": "core", "difficulty": "medium",
    "knowledge_type": "framework",
    "exam_use": ["essay", "application"],
    "reason": "강의 핵심",
}
_LOW_IMPORTANCE_TOPIC = {
    "name": "세부 개념 B",
    "importance": "detail", "difficulty": "easy",
    "knowledge_type": "term",
    "exam_use": ["short"],
    "reason": "세부 사항",
}


def test_score_number_not_prioritized_for_short_answer():
    """number 지식유형은 수치 암기 단답형으로 우선 배치하지 않아야 함."""
    from agents.planner import _score_topic
    term_topic = {**_LOW_IMPORTANCE_TOPIC, "importance": "supporting", "exam_use": ["short"]}
    assert _score_topic(term_topic, "short_answer") > _score_topic(_NUMERICAL_TOPIC, "short_answer")


def test_score_number_higher_for_essay():
    """number 지식유형은 수식·계산 구조를 다루는 서술형에 더 적합해야 함."""
    from agents.planner import _score_topic
    term_topic = {**_LOW_IMPORTANCE_TOPIC, "importance": "supporting", "exam_use": ["short"]}
    assert _score_topic(_NUMERICAL_TOPIC, "essay") > _score_topic(term_topic, "essay")


def test_score_causal_higher_for_essay():
    """causal 지식유형 토픽은 essay 점수가 numerical보다 높아야 함."""
    from agents.planner import _score_topic
    assert _score_topic(_CAUSAL_TOPIC, "essay") > _score_topic(_NUMERICAL_TOPIC, "essay")


def test_score_procedure_boosts_application():
    """knowledge_type=procedure인 토픽은 application 점수가 exam_use 없는 term보다 높아야 함."""
    from agents.planner import _score_topic
    term_only = {**_PROCEDURE_TOPIC, "knowledge_type": "term", "exam_use": []}
    assert _score_topic(_PROCEDURE_TOPIC, "application") > _score_topic(term_only, "application")


def test_plan_includes_core_high_topic():
    """core importance 토픽이 question_plan에 반드시 포함되어야 함."""
    from agents.planner import _build_plan_items
    topics = [_CORE_HIGH_TOPIC, _LOW_IMPORTANCE_TOPIC]
    counts = {"단답형": 1, "에세이형": 1, "응용형": 0, "난이도": "mixed"}
    plan = _build_plan_items(topics, [], counts)
    topic_names = [item["topic_name"] for item in plan]
    assert "핵심 개념 A" in topic_names


def test_plan_picks_term_for_short_answer_over_number():
    """short_answer 슬롯은 수식/계산형 number보다 용어형 term을 우선해야 함."""
    from agents.planner import _build_plan_items
    numerical = {**_NUMERICAL_TOPIC, "importance": "supporting", "exam_use": ["essay"]}
    causal = {**_CAUSAL_TOPIC, "importance": "supporting"}
    term_topic = {**_LOW_IMPORTANCE_TOPIC, "importance": "supporting", "exam_use": ["short"]}
    topics = [causal, numerical, term_topic]  # 비단답형을 앞에 넣어 순서 의존성 제거
    counts = {"단답형": 1, "에세이형": 0, "응용형": 0, "난이도": "mixed"}
    plan = _build_plan_items(topics, [], counts)
    assert len(plan) == 1
    assert plan[0]["question_type"] == "short_answer"
    assert plan[0]["topic_name"] == "세부 개념 B"


def test_plan_picks_causal_for_essay():
    """essay 슬롯은 causal 토픽이 numerical보다 우선 선택되어야 함."""
    from agents.planner import _build_plan_items
    topics = [_NUMERICAL_TOPIC, _CAUSAL_TOPIC]
    counts = {"단답형": 0, "에세이형": 1, "응용형": 0, "난이도": "mixed"}
    plan = _build_plan_items(topics, [], counts)
    assert len(plan) == 1
    assert plan[0]["question_type"] == "essay"
    assert plan[0]["topic_name"] == "인과 개념"


def test_plan_procedure_goes_to_application():
    """knowledge_type=procedure 토픽은 application 슬롯으로 우선 배치되어야 함."""
    from agents.planner import _build_plan_items
    topics = [_NUMERICAL_TOPIC, _PROCEDURE_TOPIC]
    counts = {"단답형": 0, "에세이형": 0, "응용형": 1, "난이도": "mixed"}
    plan = _build_plan_items(topics, [], counts)
    assert len(plan) == 1
    assert plan[0]["question_type"] == "application"
    assert plan[0]["topic_name"] == "절차 개념"


def test_plan_uses_topic_for_short_target():
    """단답형 target_concept은 정답 seed가 아니라 문제 생성용 topic 힌트여야 함."""
    from agents.planner import _build_plan_items
    topics = [_NUMERICAL_TOPIC]
    key_concepts = [{"term": "핵심 용어", "type": "term", "importance": "high", "difficulty": "medium"}]
    counts = {"단답형": 1, "에세이형": 0, "응용형": 0, "난이도": "mixed"}
    plan = _build_plan_items(topics, key_concepts, counts)
    assert plan[0]["target_concept"] == "수식 개념"


def test_short_targets_do_not_pull_unrelated_key_concepts():
    """단답형 정답은 generator가 만들므로 planner가 key_concepts를 정답처럼 끌어오지 않는다."""
    from agents.planner import _build_plan_items
    topics = [{**_NUMERICAL_TOPIC, "concept_group": "topic_group", "source_file": "file.pdf"}]
    key_concepts = [
        {"term": "A1", "type": "term", "importance": "high", "difficulty": "medium",
         "source_topic": "T1", "source_file": "f1.pdf", "concept_group": "group_a"},
        {"term": "A2", "type": "term", "importance": "high", "difficulty": "medium",
         "source_topic": "T1", "source_file": "f1.pdf", "concept_group": "group_a"},
        {"term": "B1", "type": "number", "importance": "high", "difficulty": "medium",
         "source_topic": "T2", "source_file": "f2.pdf", "concept_group": "group_b"},
    ]
    counts = {"단답형": 2, "에세이형": 0, "응용형": 0, "난이도": "mixed"}
    plan = _build_plan_items(topics, key_concepts, counts)
    targets = [item["target_concept"] for item in plan]
    assert targets == ["수식 개념", "수식 개념"]


def test_core_topic_survives_diversity_penalty():
    """diversity penalty가 core topic을 완전히 배제하면 안 됨."""
    from agents.planner import _build_plan_items
    core = {**_CORE_HIGH_TOPIC, "concept_group": "core_group", "source_file": "a.pdf"}
    detail = {**_LOW_IMPORTANCE_TOPIC, "concept_group": "detail_group", "source_file": "b.pdf"}
    counts = {"단답형": 0, "에세이형": 1, "응용형": 0, "난이도": "mixed"}
    plan = _build_plan_items([detail, core], [], counts)
    assert plan[0]["topic_name"] == "핵심 개념 A"


# ── Generator 메타데이터 프롬프트 테스트 ──────────────────────────────────────

_SAMPLE_PLAN_ITEMS = [
    {
        "question_type": "short_answer",
        "topic_name": "경사하강법",
        "target_concept": "학습률",
        "difficulty": "medium",
        "reason": "핵심 용어 이해",
        "topic_meta": {
            "importance": "core",
            "difficulty": "medium",
            "knowledge_type": "term",
            "exam_use": ["short", "tf"],
            "evidence_text": "학습률은 경사하강법의 업데이트 폭을 조절한다.",
            "source_refs": ["lecture.pdf [페이지 3]"],
        },
    }
]


def _captured_prompt(generator_cls, plan_items, module_path):
    """mock으로 generator를 실행하고 LLM에 전달된 프롬프트를 반환."""
    mock_text = json.dumps([{"id": "Q1", "type": "short", "question": "테스트 문제?", "answer": "테스트 답"}])
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
    # knowledge_type 정보와 단답형 수치 암기 금지 기준이 프롬프트에 포함되어야 함
    assert "term" in prompt_text
    assert "수치값 암기 문제는 단답형으로 출제하지 마세요" in prompt_text
    assert '"answer": "..."' in prompt_text
    assert "문제 문장에 정확히 대응해야 합니다" in prompt_text
    assert "강의 근거 텍스트" in prompt_text
    assert "업데이트 폭" in prompt_text
    assert "같은 개념군" in prompt_text


def test_essay_generator_prompt_contains_metadata():
    """EssayGenerator가 plan_items 형식일 때 프롬프트에 메타데이터가 포함되어야 함."""
    essay_plan = [
        {
            **_SAMPLE_PLAN_ITEMS[0],
            "question_type": "essay",
            "topic_meta": {
                **_SAMPLE_PLAN_ITEMS[0]["topic_meta"],
                "knowledge_type": "causal",
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
    assert "causal" in all_prompts


# ── TF 관련 테스트 ────────────────────────────────────────────────────────────

_SAMPLE_OUTPUT_WITH_TF = {
    **SAMPLE_OUTPUT,
    "tf_traps": [
        {
            "type": "misconception",
            "source_topic": "머신러닝",
            "statement_seed": "머신러닝은 항상 지도학습을 기반으로 한다",
            "answer": "F",
            "reason": "비지도학습·강화학습도 존재",
        },
        {
            "type": "concept_swap",
            "source_topic": "지도학습",
            "statement_seed": "지도학습 vs 비지도학습: 레이블 유무",
            "answer": "T",
            "reason": "레이블 유무가 핵심 구분점",
        },
    ],
}

_CONCRETE_TOPIC = {
    "name": "구체 개념",
    "importance": "core", "difficulty": "medium",
    "knowledge_type": "comparison",
    "exam_use": ["short", "tf"],
    "reason": "구체 사실 확인",
}


def test_extractor_tf_fields():
    """topic_extractor 출력에 tf_traps가 리스트로 포함되어야 함."""
    result = _run_extractor(_SAMPLE_OUTPUT_WITH_TF)
    assert isinstance(result["tf_traps"], list)
    assert len(result["tf_traps"]) > 0
    for trap in result["tf_traps"]:
        assert "type" in trap
        assert "statement_seed" in trap
        assert "answer" in trap


def test_extractor_tf_fields_default_empty():
    """tf_traps가 없으면 빈 리스트로 정규화되어야 함."""
    result = _run_extractor(SAMPLE_OUTPUT)
    assert isinstance(result["tf_traps"], list)


def test_tf_traps_in_plan_items():
    """tf_traps가 있으면 TF plan_item에 힌트가 주입되어야 함."""
    from agents.planner import _build_plan_items
    tf_traps = [
        {"type": "misconception", "source_topic": "구체 개념",
         "statement_seed": "이 개념은 항상 옳다", "answer": "F", "reason": "예외 있음"},
    ]
    topics = [_CONCRETE_TOPIC]
    counts = {"단답형": 0, "에세이형": 0, "응용형": 0, "진위형": 1}
    plan = _build_plan_items(topics, [], counts, tf_traps=tf_traps)
    tf_items = [i for i in plan if i["question_type"] == "tf"]
    assert len(tf_items) == 1
    item = tf_items[0]
    assert item.get("tf_type") == "오해 직격"
    assert item.get("intended_answer") == "F"
    assert item.get("misconception_hint") == "이 개념은 항상 옳다"


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
    """T:F 비율이 대략 35:65를 따라야 함 (10개 기준, tf_traps 없을 때)."""
    from agents.planner import _build_plan_items
    topics = [_CONCRETE_TOPIC, _NUMERICAL_TOPIC]
    counts = {"단답형": 0, "에세이형": 0, "응용형": 0, "진위형": 10, "난이도": "mixed"}
    plan = _build_plan_items(topics, [], counts)
    tf_items = [item for item in plan if item["question_type"] == "tf"]
    t_count = sum(1 for i in tf_items if i["intended_answer"] == "T")
    f_count = sum(1 for i in tf_items if i["intended_answer"] == "F")
    assert t_count <= 4 and f_count >= 6


def test_planner_tf_sequence_is_pre_mixed():
    """planner가 TF 정답방향을 생성 전에 섞인 슬롯으로 만든다."""
    from agents.planner import _tf_answer_sequence
    sequence = _tf_answer_sequence(10)
    assert sequence.count("T") == 4
    assert sequence.count("F") == 6
    assert sequence != ["T"] * 4 + ["F"] * 6
    assert sequence != ["F"] * 6 + ["T"] * 4


def test_planner_tf_false_traps_stay_false_slots():
    """F용 tf_traps를 T 슬롯으로 뒤집지 않는다."""
    from agents.planner import _build_plan_items
    topics = [_CONCRETE_TOPIC, _NUMERICAL_TOPIC]
    tf_traps = [
        {"type": "misconception", "source_topic": "구체 개념",
         "statement_seed": f"오해 {i}", "answer": "F", "reason": "오해"}
        for i in range(10)
    ]
    counts = {"단답형": 0, "에세이형": 0, "응용형": 0, "진위형": 10, "난이도": "mixed"}
    plan = _build_plan_items(topics, [], counts, tf_traps=tf_traps)
    tf_items = [item for item in plan if item["question_type"] == "tf"]
    t_items = [item for item in tf_items if item["intended_answer"] == "T"]
    f_items = [item for item in tf_items if item["intended_answer"] == "F"]

    assert len(t_items) == 4
    assert len(f_items) == 6
    assert all("misconception_hint" not in item for item in t_items)
    assert any(item.get("misconception_hint") for item in f_items)


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
    assert "별개 개념" in REVIEW_PROMPT


def test_file_writers_tf_type():
    """TYPE_KO에 'tf' 키가 '진위형'으로 등록되어야 함."""
    from tools.file_writers import TYPE_KO
    assert "tf" in TYPE_KO
    assert TYPE_KO["tf"] == "진위형"


# ── grading_seed 관련 테스트 ──────────────────────────────────────────────────

_TF_PLAN_ITEMS = [
    {
        "question_type": "tf",
        "topic_name": "지도학습",
        "target_concept": "레이블",
        "difficulty": "medium",
        "reason": "핵심 구분",
        "intended_answer": "F",
        "tf_type": "오해 직격",
        "misconception_hint": "비지도학습도 레이블이 필요하다는 오해",
        "topic_meta": {"importance": "core", "difficulty": "medium",
                       "knowledge_type": "comparison",
                       "exam_use": ["short", "tf", "essay"]},
    }
]

_APP_PLAN_ITEMS = [
    {
        "question_type": "application",
        "topic_name": "Work System Framework",
        "target_concept": "Work System Framework",
        "difficulty": "hard",
        "reason": "새로운 맥락 적용",
        "topic_meta": {"importance": "core", "difficulty": "hard",
                       "knowledge_type": "framework",
                       "exam_use": ["essay", "application"]},
    }
]


def test_tf_generator_preserves_grading_seed():
    """TFGenerator가 생성 결과의 answer를 grading_seed.expected_answer로 보존해야 함."""
    mock_text = json.dumps([{"id": "Q1", "type": "tf",
                             "question": "비지도학습은 레이블이 필요하다. (T/F)",
                             "answer": "F"}])
    with patch("agents.generators.claude_generate_text", return_value=mock_text):
        from agents.generators import TFGenerator
        agent = TFGenerator()
        result = json.loads(agent.run(json.dumps({"plan_items": _TF_PLAN_ITEMS})))
    assert len(result) == 1
    seed = result[0].get("grading_seed", {})
    assert seed.get("expected_answer") == "F"
    assert seed.get("trap") == "오해 직격"
    assert "reason" in seed


def test_short_generator_uses_generated_answer_for_grading_seed():
    """ShortAnswerGenerator는 key_concept가 아니라 생성된 answer를 grading_seed에 넣어야 함."""
    mock_text = json.dumps([{"id": "Q1", "type": "short",
                             "question": "학습률을 뜻하는 영어 용어는?",
                             "answer": "learning rate"}])
    with patch("agents.generators.claude_generate_text", return_value=mock_text):
        from agents.generators import ShortAnswerGenerator
        agent = ShortAnswerGenerator()
        result = json.loads(agent.run(json.dumps({"plan_items": _SAMPLE_PLAN_ITEMS})))

    seed = result[0].get("grading_seed", {})
    assert result[0]["answer"] == "learning rate"
    assert seed.get("expected_answer") == "learning rate"


def test_essay_generator_passes_evidence_to_grading_seed():
    """EssayGenerator는 topic evidence를 답안생성용 grading_seed에 보존해야 함."""
    essay_plan = [{
        **_SAMPLE_PLAN_ITEMS[0],
        "question_type": "essay",
        "topic_meta": {
            **_SAMPLE_PLAN_ITEMS[0]["topic_meta"],
            "knowledge_type": "framework",
        },
    }]
    mock_text = json.dumps([{"id": "Q1", "type": "essay", "question": "설명하시오."}])
    with patch("agents.generators.claude_generate_text", return_value=mock_text):
        from agents.generators import EssayGenerator
        agent = EssayGenerator()
        result = json.loads(agent.run(json.dumps({"plan_items": essay_plan})))

    seed = result[0].get("grading_seed", {})
    assert "업데이트 폭" in seed.get("evidence_text", "")
    assert seed.get("source_refs") == ["lecture.pdf [페이지 3]"]


def test_tf_answer_generator_uses_seed_skips_model():
    """TF AnswerGenerator가 grading_seed.expected_answer 있으면 모델 재판별을 하지 않아야 함."""
    from agents.answer_generator import AnswerGeneratorAgent
    q = {"id": "Q1", "type": "tf",
         "question": "비지도학습은 레이블이 필요하다. (T/F)",
         "grading_seed": {"expected_answer": "F", "reason": "비지도학습은 레이블 불필요", "trap": "오해 직격"}}
    with patch("agents.answer_generator.retry_call") as mock_retry:
        agent = AnswerGeneratorAgent.__new__(AnswerGeneratorAgent)
        agent._client = MagicMock()
        result = agent._generate_tf_answer(q)
    mock_retry.assert_not_called()
    assert result["answer"] == "F"
    assert "비지도학습은 레이블 불필요" in result["rubric"]


def test_application_answer_generator_injects_seed_context():
    """Application AnswerGenerator 프롬프트에 grading_seed 내용이 포함되어야 함."""
    from agents.answer_generator import AnswerGeneratorAgent, _seed_context
    q = {"id": "Q1", "type": "application",
         "question": "Work System Framework를 적용하여 분석하시오.",
         "grading_seed": {"target_framework": "Work System Framework",
                          "expected_reasoning": "기술·인간·조직 세 축으로 분석",
                          "evidence_text": "participants, information, technologies를 사례에 대응",
                          "source_refs": ["M1.3.pdf [페이지 2]"]}}

    seed_ctx = _seed_context(q["grading_seed"])
    assert "Work System Framework" in seed_ctx
    assert "기술·인간·조직" in seed_ctx
    assert "강의 근거 텍스트" in seed_ctx
    assert "participants" in seed_ctx
    assert "M1.3.pdf" in seed_ctx


def test_short_answer_generator_uses_seed():
    """ShortAnswer AnswerGenerator가 grading_seed.expected_answer를 answer로 사용하고 Gemini 호출이 0회여야 함."""
    from agents.answer_generator import AnswerGeneratorAgent
    q = {"id": "Q1", "type": "short",
         "question": "경사하강법에서 업데이트 속도를 조절하는 하이퍼파라미터는?",
         "grading_seed": {"expected_answer": "학습률", "accepted_variants": ["learning rate"]}}
    with patch("agents.answer_generator.retry_call") as mock_retry:
        agent = AnswerGeneratorAgent.__new__(AnswerGeneratorAgent)
        agent._client = MagicMock()
        result = agent._generate_short_answer(q)
    assert result["answer"] == "학습률"
    mock_retry.assert_not_called()


def test_grading_seed_not_in_answer_generator_output():
    """AnswerGeneratorAgent 출력 JSON에 grading_seed가 포함되지 않아야 함."""
    from agents.answer_generator import AnswerGeneratorAgent
    questions = [{"id": "Q1", "type": "short",
                  "question": "테스트 문제?",
                  "grading_seed": {"expected_answer": "테스트답", "accepted_variants": []}}]
    with patch("agents.answer_generator.retry_call") as mock_retry:
        mock_retry.return_value = MagicMock(text="채점기준")
        agent = AnswerGeneratorAgent.__new__(AnswerGeneratorAgent)
        agent._client = MagicMock()
        output = json.loads(agent.run(json.dumps(questions, ensure_ascii=False)))
    assert "grading_seed" not in output[0]
    assert output[0]["answer"] == "테스트답"


def test_grading_seed_absent_fallback():
    """grading_seed 없는 기존 입력도 정상 동작해야 함."""
    from agents.answer_generator import AnswerGeneratorAgent
    q = {"id": "Q1", "type": "short", "question": "테스트 문제?"}
    with patch("agents.answer_generator.retry_call") as mock_retry:
        mock_retry.return_value = MagicMock(text="답변")
        agent = AnswerGeneratorAgent.__new__(AnswerGeneratorAgent)
        agent._client = MagicMock()
        result = agent._generate_short_answer(q)
    # grading_seed 없으면 모델 호출 2회 (답안 + 루브릭)
    assert mock_retry.call_count == 2
    assert result["answer"] == "답변"


# ── short answer seed 기반 rubric 생성 테스트 ─────────────────────────────────

def test_short_answer_seed_rubric_includes_variants():
    """accepted_variants가 있으면 rubric에 '허용 답안' 줄이 포함되어야 함."""
    from agents.answer_generator import AnswerGeneratorAgent
    q = {"id": "Q1", "type": "short",
         "question": "과학적 관리법을 제창한 인물은?",
         "grading_seed": {"expected_answer": "테일러", "accepted_variants": ["Taylor", "F.W. Taylor"]}}
    with patch("agents.answer_generator.retry_call") as mock_retry:
        agent = AnswerGeneratorAgent.__new__(AnswerGeneratorAgent)
        agent._client = MagicMock()
        result = agent._generate_short_answer(q)
    mock_retry.assert_not_called()
    assert result["answer"] == "테일러"
    assert "정답(5점): 테일러" in result["rubric"]
    assert "허용 답안" in result["rubric"]
    assert "Taylor" in result["rubric"]
    assert "오답(0점): 그 외" in result["rubric"]


def test_short_answer_seed_rubric_no_variants():
    """accepted_variants가 없으면 rubric에 '허용 답안' 줄이 없어야 함."""
    from agents.answer_generator import AnswerGeneratorAgent
    q = {"id": "Q1", "type": "short",
         "question": "테스트 문제?",
         "grading_seed": {"expected_answer": "정답값", "accepted_variants": []}}
    with patch("agents.answer_generator.retry_call") as mock_retry:
        agent = AnswerGeneratorAgent.__new__(AnswerGeneratorAgent)
        agent._client = MagicMock()
        result = agent._generate_short_answer(q)
    mock_retry.assert_not_called()
    assert result["answer"] == "정답값"
    assert "정답(5점): 정답값" in result["rubric"]
    assert "허용 답안" not in result["rubric"]
    assert "오답(0점): 그 외" in result["rubric"]


def test_short_answer_no_seed_calls_gemini():
    """grading_seed 없는 short 문제는 Gemini를 호출해야 함 (답안 + 루브릭 2회)."""
    from agents.answer_generator import AnswerGeneratorAgent
    q = {"id": "Q1", "type": "short", "question": "프로그래밍 언어 중 인터프리터 방식은?"}
    with patch("agents.answer_generator.retry_call") as mock_retry:
        mock_retry.return_value = MagicMock(text="Python")
        agent = AnswerGeneratorAgent.__new__(AnswerGeneratorAgent)
        agent._client = MagicMock()
        result = agent._generate_short_answer(q)
    assert mock_retry.call_count == 2
    assert result["answer"] == "Python"


def test_essay_answer_generates_grading_notes():
    """Essay AnswerGenerator가 모범답안/채점기준 외에 채점 코멘트를 생성해야 함."""
    from agents.answer_generator import AnswerGeneratorAgent
    q = {"id": "Q1", "type": "essay", "question": "과학적 관리법을 설명하시오."}
    with patch("agents.answer_generator.retry_call") as mock_retry:
        mock_retry.side_effect = [
            MagicMock(text="모범답안"),
            MagicMock(text="채점기준"),
            MagicMock(text="* 동의어 표현은 인정"),
        ]
        agent = AnswerGeneratorAgent.__new__(AnswerGeneratorAgent)
        agent._client = MagicMock()
        result = agent._generate_essay_answer(q)

    assert mock_retry.call_count == 3
    assert result["answer"] == "모범답안"
    assert result["rubric"] == "채점기준"
    assert result["grading_notes"] == "* 동의어 표현은 인정"


def test_essay_rubric_prompt_uses_subpoints():
    """소문항 배점이 있으면 rubric 프롬프트가 총점 임의배분 대신 소문항별 배점을 따라야 함."""
    from agents.answer_generator import AnswerGeneratorAgent
    q = {
        "id": "Q1",
        "type": "essay",
        "question": "(1) 설명하시오.\n(2) 비교하시오.",
        "points": 25,
        "subpoints": [15, 10],
    }
    captured = {}

    def fake_retry(fn):
        fn()
        captured["prompt"] = agent._client.models.generate_content.call_args.kwargs["contents"]
        return MagicMock(text="채점기준")

    with patch("agents.answer_generator.retry_call", side_effect=fake_retry):
        agent = AnswerGeneratorAgent.__new__(AnswerGeneratorAgent)
        agent._client = MagicMock()
        agent._generate_rubric(q, "모범답안")

    assert "총점 25점. 각 소문항을 아래 형식 그대로 출력하세요" in captured["prompt"]
    assert "(1) (15점):" in captured["prompt"]
    assert "(2) (10점):" in captured["prompt"]
    assert "각 소문항은 반드시 채점 포인트 2개 이상" in captured["prompt"]
    assert "각 소문항 내 포인트 점수 합 = 소문항 배점" in captured["prompt"]
    assert "소수점 절대 금지" in captured["prompt"]


# ── application answer generator 검색 재호출 방지 테스트 ──────────────────────

def test_application_answer_skips_search_when_seed_exists():
    """grading_seed(target_framework/expected_reasoning)가 있으면 검색 호출 없이 답안을 생성해야 함."""
    from agents.answer_generator import AnswerGeneratorAgent

    q = {
        "id": "Q1", "type": "application",
        "question": "Work System Framework를 적용하여 분석하시오.",
        "grading_seed": {
            "target_framework": "Work System Framework",
            "expected_reasoning": "기술·인간·조직 세 축으로 분석",
            "scenario_mapping": [],
        },
    }
    with patch("agents.answer_generator.retry_call") as mock_retry, \
         patch("agents.answer_generator.search_with_google") as mock_google, \
         patch("agents.answer_generator.search_arxiv") as mock_arxiv:
        mock_retry.return_value = MagicMock(text="모범답안")
        agent = AnswerGeneratorAgent.__new__(AnswerGeneratorAgent)
        agent._client = MagicMock()
        agent._generate_application_answer(q)

    mock_google.assert_not_called()
    mock_arxiv.assert_not_called()


def test_application_answer_uses_search_when_no_seed():
    """grading_seed가 없으면 기존 fallback 검색 경로(arXiv + Google)를 사용해야 함."""
    from agents.answer_generator import AnswerGeneratorAgent

    q = {"id": "Q1", "type": "application",
         "question": "Work System Framework를 적용하여 분석하시오."}

    with patch("agents.answer_generator.retry_call") as mock_retry, \
         patch("agents.answer_generator.get_cached", return_value=None), \
         patch("agents.answer_generator.set_cached"), \
         patch("agents.answer_generator.search_arxiv", return_value="arXiv 결과") as mock_arxiv, \
         patch("agents.answer_generator.search_with_google", return_value="Google 결과") as mock_google:
        mock_retry.return_value = MagicMock(text="모범답안")
        agent = AnswerGeneratorAgent.__new__(AnswerGeneratorAgent)
        agent._client = MagicMock()
        agent._generate_application_answer(q)

    mock_arxiv.assert_called_once()
    mock_google.assert_called_once()


def test_application_answer_skips_search_with_only_scenario_mapping():
    """scenario_mapping만 있고 target_framework/expected_reasoning 없으면 검색을 수행해야 함."""
    from agents.answer_generator import AnswerGeneratorAgent

    q = {
        "id": "Q1", "type": "application",
        "question": "분석하시오.",
        "grading_seed": {"scenario_mapping": []},  # 빈 리스트 — 의미 있는 seed 없음
    }
    with patch("agents.answer_generator.retry_call") as mock_retry, \
         patch("agents.answer_generator.get_cached", return_value=None), \
         patch("agents.answer_generator.set_cached"), \
         patch("agents.answer_generator.search_arxiv", return_value="결과") as mock_arxiv, \
         patch("agents.answer_generator.search_with_google", return_value="결과") as mock_google:
        mock_retry.return_value = MagicMock(text="모범답안")
        agent = AnswerGeneratorAgent.__new__(AnswerGeneratorAgent)
        agent._client = MagicMock()
        agent._generate_application_answer(q)

    mock_arxiv.assert_called_once()
    mock_google.assert_called_once()
