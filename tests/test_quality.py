# tests/test_quality.py
import json
import pytest
from unittest.mock import MagicMock, patch


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _qa(qid="Q1", qtype="short", question="테스트 문제?", answer="답변", rubric="채점기준"):
    return {"id": qid, "type": qtype, "question": question, "answer": answer, "rubric": rubric}

def _plan(short=1, essay=0, app=0, tf=0, difficulty="medium"):
    return {"단답형": short, "에세이형": essay, "응용형": app, "진위형": tf, "난이도": difficulty}


# ── rule-based checker 테스트 ─────────────────────────────────────────────────

def test_rule_passes_clean_questions():
    from tools.quality_rules import run_quality_rules
    result = run_quality_rules([_qa()], _plan(short=1))
    assert result["pass"] is True
    assert result["issues"] == []


def test_rule_catches_markdown_bold():
    from tools.quality_rules import run_quality_rules
    result = run_quality_rules([_qa(question="**중요** 개념은?")], _plan(short=1))
    assert result["pass"] is False
    assert any("마크다운" in i["reason"] for i in result["issues"])


def test_rule_catches_markdown_hash():
    from tools.quality_rules import run_quality_rules
    result = run_quality_rules([_qa(question="## 섹션 개념은?")], _plan(short=1))
    assert result["pass"] is False
    assert any("마크다운" in i["reason"] for i in result["issues"])


def test_rule_catches_tf_missing_marker():
    from tools.quality_rules import run_quality_rules
    qa = [_qa(qid="Q1", qtype="tf", question="머신러닝은 데이터에서 패턴을 학습한다.", answer="T", rubric="기준")]
    result = run_quality_rules(qa, _plan(tf=1))
    assert result["pass"] is False
    assert any("T/F" in i["reason"] for i in result["issues"])


def test_rule_passes_valid_tf():
    from tools.quality_rules import run_quality_rules
    qa = [_qa(qid="Q1", qtype="tf", question="머신러닝은 데이터에서 패턴을 학습한다. (T/F)", answer="T", rubric="기준")]
    result = run_quality_rules(qa, _plan(tf=1))
    tf_marker_issues = [i for i in result["issues"] if "T/F" in i["reason"]]
    assert tf_marker_issues == []


def test_rule_catches_missing_answer():
    from tools.quality_rules import run_quality_rules
    qa = [{"id": "Q1", "type": "short", "question": "테스트?", "answer": "", "rubric": "기준"}]
    result = run_quality_rules(qa, _plan(short=1))
    assert result["pass"] is False
    assert any("answer" in i["reason"] for i in result["issues"])


def test_rule_catches_missing_rubric():
    from tools.quality_rules import run_quality_rules
    qa = [{"id": "Q1", "type": "short", "question": "테스트?", "answer": "답", "rubric": ""}]
    result = run_quality_rules(qa, _plan(short=1))
    assert result["pass"] is False
    assert any("rubric" in i["reason"] for i in result["issues"])


def test_rule_catches_duplicate_question():
    from tools.quality_rules import run_quality_rules
    qa = [_qa(qid="Q1"), _qa(qid="Q2")]  # 같은 question 텍스트
    result = run_quality_rules(qa, _plan(short=2))
    assert result["pass"] is False
    assert any("중복" in i["reason"] for i in result["issues"])


def test_rule_catches_english_directive():
    from tools.quality_rules import run_quality_rules
    qa = [_qa(question="Explain the concept of machine learning in detail.")]
    result = run_quality_rules(qa, _plan(short=1))
    assert result["pass"] is False
    assert any("영어" in i["reason"] for i in result["issues"])


def test_rule_allows_english_term_in_korean_question():
    from tools.quality_rules import run_quality_rules
    qa = [_qa(question="Work System Framework를 적용하여 분석하시오.")]
    result = run_quality_rules(qa, _plan(short=1))
    english_dir_issues = [i for i in result["issues"] if "영어" in i["reason"]]
    assert english_dir_issues == []


def test_rule_catches_count_mismatch():
    from tools.quality_rules import run_quality_rules
    qa = [_qa(qid="Q1"), _qa(qid="Q2", question="다른 문제?")]
    result = run_quality_rules(qa, _plan(short=3))  # 계획 3, 실제 2
    assert result["pass"] is False
    assert any("개수 불일치" in i["reason"] for i in result["issues"])


# ── 소문항 허용 / 한 문장 다중작업 탐지 / TF 복합명제 탐지 테스트 ────────────

def test_rule_essay_subquestions_allowed():
    """에세이형 (1)(2)(3) 소문항 구조는 부적합으로 잡히지 않아야 함."""
    from tools.quality_rules import run_quality_rules
    q = _qa(
        qtype="essay",
        question="지도학습과 비지도학습을 비교하시오.\n(1) 둘의 핵심 차이를 설명하시오.\n(2) 각각의 대표 알고리즘을 하나씩 쓰시오.",
    )
    result = run_quality_rules([q], _plan(essay=1))
    multi_task_issues = [i for i in result["issues"] if "여러 사고 작업" in i["reason"]]
    assert multi_task_issues == []


def test_rule_application_subquestions_allowed():
    """응용형 소문항 2개 구조는 부적합으로 잡히지 않아야 함."""
    from tools.quality_rules import run_quality_rules
    q = _qa(
        qtype="application",
        question="편의점에 새로운 POS 시스템이 도입되었다. 직원들은 익숙하지 않아 결제가 느려지고 있다.\n(1) Work System Framework를 적용하여 문제를 분석하시오.\n(2) 개선 방향을 제시하시오.",
        answer="답변",
        rubric="채점기준",
    )
    result = run_quality_rules([q], _plan(app=1))
    multi_task_issues = [i for i in result["issues"] if "여러 사고 작업" in i["reason"]]
    assert multi_task_issues == []


def test_rule_essay_multi_task_in_one_sentence_flagged():
    """에세이형에서 한 문장에 여러 작업 동사를 이어 묻는 문제는 부적합이어야 함."""
    from tools.quality_rules import run_quality_rules
    q = _qa(
        qtype="essay",
        question="지도학습의 개념을 설명하고, 비지도학습과 비교하고, 각각의 한계를 제시하시오.",
    )
    result = run_quality_rules([q], _plan(essay=1))
    assert any("여러 사고 작업" in i["reason"] for i in result["issues"])


def test_rule_application_multi_task_in_one_sentence_flagged():
    """응용형에서 한 문장에 여러 작업 동사를 이어 묻는 문제는 부적합이어야 함."""
    from tools.quality_rules import run_quality_rules
    q = _qa(
        qtype="application",
        question="위 시나리오를 분석하고 평가하시오.",
        answer="답변",
        rubric="채점기준",
    )
    result = run_quality_rules([q], _plan(app=1))
    assert any("여러 사고 작업" in i["reason"] for i in result["issues"])


def test_rule_tf_compound_igo_flagged():
    """진위형 '하고 + 새 주어' 복합 명제는 부적합이어야 함."""
    from tools.quality_rules import run_quality_rules
    q = _qa(
        qtype="tf",
        question="지도학습은 레이블이 필요하고 비지도학습은 레이블이 필요 없다. (T/F)",
        answer="T",
    )
    result = run_quality_rules([q], _plan(tf=1))
    assert any("복합 명제" in i["reason"] for i in result["issues"])


def test_rule_tf_compound_jiman_flagged():
    """진위형 '지만' 복합 명제는 부적합이어야 함."""
    from tools.quality_rules import run_quality_rules
    q = _qa(
        qtype="tf",
        question="딥러닝은 머신러닝의 하위 분야이지만 머신러닝보다 더 넓은 개념이다. (T/F)",
        answer="F",
    )
    result = run_quality_rules([q], _plan(tf=1))
    assert any("복합 명제" in i["reason"] for i in result["issues"])


def test_rule_tf_compound_moodu_flagged():
    """진위형 'X와 Y는 모두' 복합 명제는 부적합이어야 함."""
    from tools.quality_rules import run_quality_rules
    q = _qa(
        qtype="tf",
        question="지도학습과 비지도학습은 모두 레이블이 필요하다. (T/F)",
        answer="F",
    )
    result = run_quality_rules([q], _plan(tf=1))
    assert any("복합 명제" in i["reason"] for i in result["issues"])


def test_rule_tf_single_fact_not_flagged():
    """진위형 단일 명제는 복합 명제로 잡히지 않아야 함."""
    from tools.quality_rules import run_quality_rules
    q = _qa(
        qtype="tf",
        question="비지도학습은 레이블이 없는 데이터로 학습한다. (T/F)",
        answer="T",
    )
    result = run_quality_rules([q], _plan(tf=1))
    compound_issues = [i for i in result["issues"] if "복합 명제" in i["reason"]]
    assert compound_issues == []


# ── prompt 키워드 일치 테스트 ──────────────────────────────────────────────────

def test_review_prompt_subquestion_criteria():
    """REVIEW_PROMPT에 소문항 허용·한 문장 다중작업 금지 기준이 포함되어야 함."""
    from agents.quality_reviewer import REVIEW_PROMPT
    assert "소문항" in REVIEW_PROMPT
    assert "설명하고 평가하고 제시하시오" in REVIEW_PROMPT


def test_review_prompt_tf_compound_criteria():
    """REVIEW_PROMPT에 TF 복합 명제 기준이 포함되어야 함."""
    from agents.quality_reviewer import REVIEW_PROMPT
    assert "복합 명제" in REVIEW_PROMPT
    assert "A이고 B이다" in REVIEW_PROMPT


def test_essay_prompt_subquestion_rule():
    """ESSAY_PROMPT_PLAN에 소문항·부분점수 기준이 포함되어야 함."""
    from agents.generators import ESSAY_PROMPT_PLAN
    assert "소문항" in ESSAY_PROMPT_PLAN
    assert "부분점수" in ESSAY_PROMPT_PLAN
    assert "한 문장" in ESSAY_PROMPT_PLAN


def test_application_prompt_subquestion_allowed():
    """APPLICATION_PROMPT_PLAN에 소문항 1~3개 허용이 명시되어야 하고 '질문이 2개 이상이면 안 됨'은 없어야 함."""
    from agents.generators import APPLICATION_PROMPT_PLAN
    assert "소문항 1~3개" in APPLICATION_PROMPT_PLAN
    assert "질문이 2개 이상이면 안 됨" not in APPLICATION_PROMPT_PLAN


def test_tf_prompt_single_fact_rule():
    """TF_PROMPT_PLAN에 복합 명제 금지 기준이 포함되어야 함."""
    from agents.generators import TF_PROMPT_PLAN
    assert "단일 사실" in TF_PROMPT_PLAN
    assert "A이고 B이다" in TF_PROMPT_PLAN


# ── _run_quality_step 흐름 테스트 ──────────────────────────────────────────────

_SAMPLE_QA = [_qa()]
_SAMPLE_PLAN = _plan(short=1)


def test_ai_reviewer_called_after_rule_pass():
    """rule 통과 후 AI reviewer 1차가 반드시 호출되어야 함."""
    from main import _run_quality_step

    with patch("main.run_quality_rules", return_value={"pass": True, "issues": []}), \
         patch("main._apply_fixes", side_effect=lambda qa, *a, **kw: qa), \
         patch("main.QualityReviewerAgent") as MockReviewer:
        mock_rev = MockReviewer.return_value
        mock_rev.run.return_value = json.dumps({"pass": True, "issues": []})
        _run_quality_step(_SAMPLE_QA, _SAMPLE_PLAN, [])

    mock_rev.run.assert_called_once()


def test_second_ai_review_not_called_if_first_passes():
    """1차 AI reviewer pass → 2차 호출 없음."""
    from main import _run_quality_step

    with patch("main.run_quality_rules", return_value={"pass": True, "issues": []}), \
         patch("main._apply_fixes", side_effect=lambda qa, *a, **kw: qa), \
         patch("main.QualityReviewerAgent") as MockReviewer:
        mock_rev = MockReviewer.return_value
        mock_rev.run.return_value = json.dumps({"pass": True, "issues": []})
        _run_quality_step(_SAMPLE_QA, _SAMPLE_PLAN, [])

    assert mock_rev.run.call_count == 1


def test_second_ai_review_called_with_only_fixed_questions():
    """1차 issue → 수정 후 2차는 해당 문항만 검토해야 함."""
    from main import _run_quality_step

    qa = [_qa(qid="Q1"), _qa(qid="Q2", question="다른 문제?")]
    plan = _plan(short=2)

    rev_responses = [
        json.dumps({"pass": False, "issues": [{"id": "Q1", "type": "short", "reason": "마크다운 포함"}]}),
        json.dumps({"pass": True, "issues": []}),
    ]

    with patch("main.run_quality_rules", return_value={"pass": True, "issues": []}), \
         patch("main._apply_fixes", side_effect=lambda qa, *a, **kw: qa), \
         patch("main.QualityReviewerAgent") as MockReviewer:
        mock_rev = MockReviewer.return_value
        mock_rev.run.side_effect = rev_responses
        _run_quality_step(qa, plan, [])

    assert mock_rev.run.call_count == 2
    second_input = json.loads(mock_rev.run.call_args_list[1][0][0])
    assert len(second_input["questions"]) == 1
    assert second_input["questions"][0]["id"] == "Q1"


def test_ai_reviewer_called_max_twice():
    """1차 + 2차 모두 issue를 반환해도 AI reviewer는 2회를 초과하지 않아야 함."""
    from main import _run_quality_step

    qa = [_qa(qid="Q1")]
    plan = _plan(short=1)

    rev_responses = [
        json.dumps({"pass": False, "issues": [{"id": "Q1", "type": "short", "reason": "문제 있음"}]}),
        json.dumps({"pass": False, "issues": [{"id": "Q1", "type": "short", "reason": "문제 있음"}]}),
    ]

    with patch("main.run_quality_rules", return_value={"pass": True, "issues": []}), \
         patch("main._apply_fixes", side_effect=lambda qa, *a, **kw: qa), \
         patch("main.QualityReviewerAgent") as MockReviewer:
        mock_rev = MockReviewer.return_value
        mock_rev.run.side_effect = rev_responses
        _, unresolved = _run_quality_step(qa, plan, [])

    assert mock_rev.run.call_count == 2
    assert len(unresolved) > 0


def test_unresolved_reported_after_second_review():
    """2차 AI reviewer 이후 남은 issue는 unresolved에 기록되어야 함."""
    from main import _run_quality_step

    qa = [_qa(qid="Q1")]
    plan = _plan(short=1)
    remaining_issue = {"id": "Q1", "type": "short", "reason": "의미 오류"}

    rev_responses = [
        json.dumps({"pass": False, "issues": [{"id": "Q1", "type": "short", "reason": "문제"}]}),
        json.dumps({"pass": False, "issues": [remaining_issue]}),
    ]

    with patch("main.run_quality_rules", return_value={"pass": True, "issues": []}), \
         patch("main._apply_fixes", side_effect=lambda qa, *a, **kw: qa), \
         patch("main.QualityReviewerAgent") as MockReviewer:
        mock_rev = MockReviewer.return_value
        mock_rev.run.side_effect = rev_responses
        _, unresolved = _run_quality_step(qa, plan, [])

    assert any(i["reason"] == "의미 오류" for i in unresolved)


# ── escalation 테스트 (_apply_fixes) ─────────────────────────────────────────

def test_first_occurrence_calls_regenerate():
    """같은 issue 첫 발생 → _regenerate_qa 호출, _refine_qa 호출 없음."""
    from main import _apply_fixes

    qa = [_qa(qid="Q1")]
    issues = [{"id": "Q1", "type": "short", "reason": "마크다운 포함"}]
    issue_history: dict = {}
    unresolved: list = []

    with patch("main._regenerate_qa", return_value=True) as mock_regen, \
         patch("main._refine_qa", return_value=True) as mock_refine, \
         patch("main.AnswerGeneratorAgent"), \
         patch("main.RefinerAgent"):
        _apply_fixes(qa, issues, [], {}, issue_history, unresolved)

    mock_regen.assert_called_once()
    mock_refine.assert_not_called()
    assert unresolved == []


def test_second_occurrence_calls_refine():
    """같은 issue 두 번째 발생 → _refine_qa 호출, _regenerate_qa 호출 없음."""
    from main import _apply_fixes, _normalize_reason

    reason = "마크다운 포함"
    qa = [_qa(qid="Q1")]
    issues = [{"id": "Q1", "type": "short", "reason": reason}]
    issue_history = {("Q1", _normalize_reason(reason)): 1}
    unresolved: list = []

    with patch("main._regenerate_qa", return_value=True) as mock_regen, \
         patch("main._refine_qa", return_value=True) as mock_refine, \
         patch("main.AnswerGeneratorAgent"), \
         patch("main.RefinerAgent"):
        _apply_fixes(qa, issues, [], {}, issue_history, unresolved)

    mock_refine.assert_called_once()
    mock_regen.assert_not_called()
    assert unresolved == []


def test_third_occurrence_records_unresolved():
    """같은 issue 세 번째 발생 → unresolved에 기록, 자동 수정 없음."""
    from main import _apply_fixes, _normalize_reason

    reason = "마크다운 포함"
    qa = [_qa(qid="Q1")]
    issues = [{"id": "Q1", "type": "short", "reason": reason}]
    issue_history = {("Q1", _normalize_reason(reason)): 2}
    unresolved: list = []

    with patch("main._regenerate_qa", return_value=True) as mock_regen, \
         patch("main._refine_qa", return_value=True) as mock_refine, \
         patch("main.AnswerGeneratorAgent"), \
         patch("main.RefinerAgent"):
        _apply_fixes(qa, issues, [], {}, issue_history, unresolved)

    mock_regen.assert_not_called()
    mock_refine.assert_not_called()
    assert len(unresolved) == 1
    assert unresolved[0]["id"] == "Q1"


def test_q0_issues_are_skipped_in_apply_fixes():
    """Q0(전체 개수 오류)는 개별 수정 대상에서 제외되어야 함."""
    from main import _apply_fixes

    qa = [_qa(qid="Q1")]
    issues = [{"id": "Q0", "type": "", "reason": "문제 총 개수 불일치"}]
    issue_history: dict = {}
    unresolved: list = []

    with patch("main._regenerate_qa") as mock_regen, \
         patch("main._refine_qa") as mock_refine, \
         patch("main.AnswerGeneratorAgent"), \
         patch("main.RefinerAgent"):
        _apply_fixes(qa, issues, [], {}, issue_history, unresolved)

    mock_regen.assert_not_called()
    mock_refine.assert_not_called()


def test_refiner_runs_single_api_call_without_self_eval():
    """RefinerAgent는 자기평가 API 호출 없이 수정 API 1회만 수행한다."""
    from agents.refiner import RefinerAgent

    q = {"id": "Q1", "type": "short", "question": "기존 문제?"}
    refined = {"id": "Q1", "type": "short", "question": "수정 문제?"}

    def fake_retry(fn):
        return fn()

    with patch("agents.refiner.retry_call", side_effect=fake_retry):
        agent = RefinerAgent.__new__(RefinerAgent)
        agent._client = MagicMock()
        agent._client.models.generate_content.return_value = MagicMock(
            text=json.dumps(refined, ensure_ascii=False)
        )
        result = json.loads(agent.run(json.dumps({"problem": q, "feedback": "더 명확하게"})))

    assert result == refined
    assert agent._client.models.generate_content.call_count == 1


# ── _find_plan_item 테스트 ────────────────────────────────────────────────────

def test_find_plan_item_by_q1():
    from main import _find_plan_item
    item0 = {"question_type": "short_answer", "topic_name": "머신러닝"}
    item1 = {"question_type": "essay", "topic_name": "다른 개념"}
    plan = {"question_plan": [item0, item1]}
    assert _find_plan_item("Q1", plan) is item0
    assert _find_plan_item("Q2", plan) is item1


def test_find_plan_item_out_of_range():
    from main import _find_plan_item
    plan = {"question_plan": [{"question_type": "short_answer"}]}
    assert _find_plan_item("Q99", plan) is None


def test_find_plan_item_empty_plan():
    from main import _find_plan_item
    assert _find_plan_item("Q1", {}) is None
    assert _find_plan_item("Q1", {"question_plan": []}) is None


# ── _regenerate_qa plan_item 사용 테스트 ────────────────────────────────────────

def test_regenerate_uses_plan_item_when_available():
    """plan_item이 있으면 generator에 plan_items 형식으로 전달해야 함."""
    from main import _regenerate_qa

    qa = [_qa(qid="Q1")]
    iss = {"id": "Q1", "type": "short", "reason": "마크다운"}
    plan_item = {"question_type": "short_answer", "topic_name": "머신러닝", "target_concept": "학습률"}
    plan = {"question_plan": [plan_item], "단답형": 1, "에세이형": 0, "응용형": 0, "진위형": 0, "난이도": "medium"}

    mock_gen = MagicMock()
    mock_gen.run.return_value = json.dumps([{"id": "Q1", "type": "short", "question": "새 문제?"}])
    mock_answer_gen = MagicMock()
    mock_answer_gen.run.return_value = json.dumps([{
        "id": "Q1", "type": "short", "question": "새 문제?", "answer": "새 답", "rubric": "새 기준",
    }])

    with patch("main.ShortAnswerGenerator", return_value=mock_gen):
        _regenerate_qa("Q1", iss, qa, 0, [], plan, mock_answer_gen)

    call_input = json.loads(mock_gen.run.call_args[0][0])
    assert "plan_items" in call_input
    assert call_input["plan_items"][0]["topic_name"] == "머신러닝"


def test_regenerate_fallback_without_plan_item():
    """question_plan이 없으면 topics/count fallback을 사용해야 함."""
    from main import _regenerate_qa

    qa = [_qa(qid="Q1")]
    iss = {"id": "Q1", "type": "short", "reason": "마크다운"}
    plan = {"단답형": 1, "에세이형": 0, "응용형": 0, "진위형": 0, "난이도": "medium"}
    topics = [{"name": "머신러닝"}]

    mock_gen = MagicMock()
    mock_gen.run.return_value = json.dumps([{"id": "Q1", "type": "short", "question": "새 문제?"}])
    mock_answer_gen = MagicMock()
    mock_answer_gen.run.return_value = json.dumps([{
        "id": "Q1", "type": "short", "question": "새 문제?", "answer": "새 답", "rubric": "새 기준",
    }])

    with patch("main.ShortAnswerGenerator", return_value=mock_gen):
        _regenerate_qa("Q1", iss, qa, 0, topics, plan, mock_answer_gen)

    call_input = json.loads(mock_gen.run.call_args[0][0])
    assert "topics" in call_input
    assert "머신러닝" in call_input["topics"]
    assert call_input["count"] == 1
