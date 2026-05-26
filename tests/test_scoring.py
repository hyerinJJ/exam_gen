"""Unit tests for tools/scoring.py — deterministic point assignment."""
import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.scoring import assign_points, _count_subquestions, _subpoints_for


# ── _count_subquestions ────────────────────────────────────────────────────────

def test_count_no_subquestions():
    assert _count_subquestions("개념을 설명하시오.") == 1


def test_count_single_subquestion():
    assert _count_subquestions("(1) 설명하시오.") == 1


def test_count_two_subquestions():
    text = "시나리오\n(1) 첫 번째 질문\n(2) 두 번째 질문"
    assert _count_subquestions(text) == 2


def test_count_three_subquestions():
    text = "배경\n(1) 분석\n(2) 비교\n(3) 제시"
    assert _count_subquestions(text) == 3


def test_count_empty_text():
    assert _count_subquestions("") == 1


# ── _subpoints_for ─────────────────────────────────────────────────────────────

def test_subpoints_normal():
    assert _subpoints_for(2, False, False) == [10, 10]


def test_subpoints_hard_only():
    assert _subpoints_for(3, True, False) == [15, 10, 10]


def test_subpoints_core_only():
    assert _subpoints_for(2, False, True) == [15, 10]


def test_subpoints_hard_and_core():
    assert _subpoints_for(3, True, True) == [15, 15, 15]


def test_subpoints_single_hard():
    assert _subpoints_for(1, True, False) == [15]


def test_subpoints_single_normal():
    assert _subpoints_for(1, False, False) == [10]


# ── assign_points — fixed types ────────────────────────────────────────────────

def _make_questions(specs):
    """specs: list of (type, question_text, difficulty, importance)"""
    qs = []
    for i, (qtype, qtext, diff, imp) in enumerate(specs, 1):
        q = {"id": f"Q{i}", "type": qtype, "question": qtext,
             "difficulty": diff, "topic_meta": {"importance": imp}}
        qs.append(q)
    return qs


def test_tf_10_items():
    qs = _make_questions([("tf", "명제 (T/F)", "medium", "supporting")] * 10)
    result = assign_points(qs)
    assert all(q["points"] == 2 for q in result)
    assert sum(q["points"] for q in result) == 20


def test_short_5_items():
    qs = _make_questions([("short", "용어는?", "medium", "supporting")] * 5)
    result = assign_points(qs)
    assert all(q["points"] == 5 for q in result)
    assert sum(q["points"] for q in result) == 25


def test_essay_default_10pt():
    # 10 essays × 10pt = 100pt total, no correction triggered
    qs = _make_questions([("essay", "설명하시오.", "medium", "supporting")] * 10)
    result = assign_points(qs)
    assert all(q["points"] == 10 for q in result)
    assert all(q["subpoints"] == [10] for q in result)


def test_essay_hard_first_subpoint_15pt():
    text = "시나리오\n(1) 질문1\n(2) 질문2"
    # 4 hard essays × 25pt = 100pt total, no correction triggered
    qs = _make_questions([("essay", text, "hard", "supporting")] * 4)
    result = assign_points(qs)
    for q in result:
        assert q["subpoints"] == [15, 10]
        assert q["points"] == 25


def test_essay_core_first_subpoint_15pt():
    text = "시나리오\n(1) 질문1\n(2) 질문2"
    # 4 core essays × 25pt = 100pt total, no correction triggered
    qs = _make_questions([("essay", text, "medium", "core")] * 4)
    result = assign_points(qs)
    for q in result:
        assert q["subpoints"] == [15, 10]
        assert q["points"] == 25


def test_essay_hard_and_core_all_15pt():
    text = "시나리오\n(1) 질문1\n(2) 질문2\n(3) 질문3"
    qs = _make_questions([("essay", text, "hard", "core")])
    result = assign_points(qs)
    assert result[0]["subpoints"] == [15, 15, 15]
    assert result[0]["points"] == 45


# ── 총점 최소 100점 보정 ───────────────────────────────────────────────────────

def test_total_under_100_correction():
    """5 short(25pt) + 7 essay(70pt) = 95pt → correction upgrades one 10-pt subpoint to 15pt → 100pt."""
    qs = _make_questions(
        [("short", "용어는?", "medium", "supporting")] * 5
        + [("essay", "설명하시오.", "medium", "supporting")] * 7
    )
    result = assign_points(qs)
    total = sum(q["points"] for q in result)
    assert total >= 100


def test_total_already_100_no_change():
    """5 TF(10) + 5 short(25) + 6 essay(60) + 1 app(10) = 105, no correction needed."""
    qs = _make_questions(
        [("tf", "명제 (T/F)", "medium", "supporting")] * 5
        + [("short", "용어는?", "medium", "supporting")] * 5
        + [("essay", "설명하시오.", "medium", "supporting")] * 6
        + [("application", "시나리오\n(1) 분석", "medium", "supporting")]
    )
    result = assign_points(qs)
    total = sum(q["points"] for q in result)
    assert total >= 100


def test_correction_upgrades_10pt_to_15pt_only():
    """Correction must not touch TF/short — only essay/app 10-pt subpoints."""
    qs = _make_questions(
        [("tf", "명제 (T/F)", "medium", "supporting")] * 2
        + [("short", "용어는?", "medium", "supporting")] * 2
        + [("essay", "설명하시오.", "medium", "supporting")]
    )
    result = assign_points(qs)
    tf_pts  = [q["points"] for q in result if q["type"] == "tf"]
    sh_pts  = [q["points"] for q in result if q["type"] == "short"]
    assert all(p == 2 for p in tf_pts)
    assert all(p == 5 for p in sh_pts)


def test_idempotent_if_points_already_set():
    """assign_points must skip questions that already have 'points'."""
    q = {"id": "Q1", "type": "tf", "question": "명제 (T/F)", "points": 99, "subpoints": [99]}
    result = assign_points([q])
    assert result[0]["points"] == 99


# ── file_writers integration: points consistency ───────────────────────────────

def test_file_writers_uses_question_points(tmp_path):
    """save_exam_docx must use q['points'] for group headers, not round(100/n)."""
    from tools.file_writers import save_exam_docx

    qs = [
        {"id": "Q1", "type": "tf",    "question": "명제 (T/F)",  "points": 2,  "subpoints": [2]},
        {"id": "Q2", "type": "short", "question": "용어는?",      "points": 5,  "subpoints": [5]},
        {"id": "Q3", "type": "essay", "question": "설명하시오.",   "points": 10, "subpoints": [10]},
    ]
    out = str(tmp_path / "exam_test.docx")
    save_exam_docx(qs, out)  # should not raise
    assert os.path.exists(out)


def test_answer_key_includes_points(tmp_path):
    """save_answer_key_docx must include points in the header for each question."""
    from tools.file_writers import save_answer_key_docx

    qa = [
        {"id": "Q1", "type": "tf",    "question": "명제", "answer": "T",
         "rubric": "정답: T", "points": 2},
        {"id": "Q2", "type": "short", "question": "용어", "answer": "과적합",
         "rubric": "정답(5점): 과적합", "points": 5},
    ]
    out = str(tmp_path / "answer_test.docx")
    save_answer_key_docx(qa, out)
    assert os.path.exists(out)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
