import re

_VALID_TYPES = {"short", "essay", "application", "tf"}
_TYPE_PLAN_KEY = {"short": "단답형", "essay": "에세이형", "application": "응용형", "tf": "진위형"}
_MARKDOWN_RE = re.compile(r"\*\*|##|(?<!\w)\*(?!\w)|(?<!\w)#(?!\w)|__")
_ENGLISH_DIRECTIVE_RE = re.compile(
    r"^\s*(Explain|Discuss|Analyze|Compare|Describe|Evaluate|Identify)\b",
    re.IGNORECASE,
)
# 에세이/응용형: 한 줄 안에서 여러 사고 작업 동사가 연속되는 패턴 탐지
_MULTI_TASK_VERB_RE = re.compile(
    r"(?:분석|설명|평가|비교|제시|서술|기술|논의|비판)하(?:고|며|시오|세요|라)",
    re.UNICODE,
)
_SUBQUESTION_LINE_RE = re.compile(r"^\s*(?:\([0-9]+\)|[①②③④⑤])")
# 진위형: 두 사실을 동시에 판단해야 하는 복합 명제 패턴 탐지
_TF_COMPOUND_RE = re.compile(
    r"(?:이고|이며|하고|하며)[^。\n]{0,30}(?:은|는|이|가)\s"  # X이고/하고 ... Y는/이/은
    r"|지만"                                                  # 대조 접속사
    r"|[가-힣]+(?:와|과)\s+[가-힣]+(?:은|는)\s+모두",          # X와/과 Y는 모두
    re.UNICODE,
)


def run_quality_rules(qa_pairs: list, plan: dict) -> dict:
    """LLM 없이 코드로 검사하는 rule-based quality check.

    반환 형식은 QualityReviewerAgent와 동일:
    {"pass": bool, "issues": [{"id", "type", "reason"}, ...]}
    """
    issues = []

    # ─ 전체 개수 ─────────────────────────────────────────────────────────────
    expected_total = sum(plan.get(k, 0) for k in _TYPE_PLAN_KEY.values())
    if expected_total > 0 and len(qa_pairs) != expected_total:
        issues.append({
            "id": "Q0", "type": "",
            "reason": f"문제 총 개수 불일치: 계획 {expected_total}개, 실제 {len(qa_pairs)}개",
        })

    # ─ 유형별 개수 ────────────────────────────────────────────────────────────
    type_counts: dict = {}
    for q in qa_pairs:
        t = q.get("type", "")
        type_counts[t] = type_counts.get(t, 0) + 1
    for qtype, plan_key in _TYPE_PLAN_KEY.items():
        expected = plan.get(plan_key, 0)
        actual = type_counts.get(qtype, 0)
        if expected > 0 and actual != expected:
            issues.append({
                "id": "Q0", "type": qtype,
                "reason": f"{plan_key} 개수 불일치: 계획 {expected}개, 실제 {actual}개",
            })

    seen_questions: dict = {}

    for q in qa_pairs:
        qid = q.get("id", "?")
        qtype = q.get("type", "")
        question = q.get("question", "")
        answer = q.get("answer", "")
        rubric = q.get("rubric", "")

        # type 유효성
        if qtype not in _VALID_TYPES:
            issues.append({"id": qid, "type": qtype, "reason": f"유효하지 않은 문제 유형: {qtype!r}"})

        # question 비어 있음
        if not question.strip():
            issues.append({"id": qid, "type": qtype, "reason": "question이 비어 있음"})
            continue

        # 마크다운 기호
        if _MARKDOWN_RE.search(question):
            issues.append({"id": qid, "type": qtype, "reason": "문제 본문에 마크다운 기호 포함"})

        # TF 형식
        if qtype == "tf":
            if not question.strip().endswith("(T/F)"):
                issues.append({"id": qid, "type": qtype, "reason": "진위형 문항이 (T/F)로 끝나지 않음"})
            if answer and answer.upper() not in ("T", "F"):
                issues.append({"id": qid, "type": qtype, "reason": f"진위형 answer가 T/F가 아님: {answer!r}"})

        # answer / rubric 누락
        if not answer.strip():
            issues.append({"id": qid, "type": qtype, "reason": "answer 누락"})
        if not rubric.strip():
            issues.append({"id": qid, "type": qtype, "reason": "rubric 누락"})

        # 중복 question
        if question in seen_questions:
            issues.append({"id": qid, "type": qtype, "reason": f"question이 {seen_questions[question]}와 중복"})
        else:
            seen_questions[question] = qid

        # essay/application 지나치게 긴 문제
        if qtype in ("essay", "application"):
            sub_q = len(re.findall(r"\([0-9]+\)|[①②③④⑤]", question))
            lines = [ln for ln in question.split("\n") if ln.strip()]
            if sub_q >= 4 or len(lines) >= 5:
                issues.append({"id": qid, "type": qtype, "reason": "문제가 지나치게 김 (소문항 4개 이상 또는 지시문 5줄 이상)"})

        # essay/application: 한 문장 안에 여러 사고 작업 동사를 이어 묻는 패턴
        if qtype in ("essay", "application"):
            for line in question.split("\n"):
                if _SUBQUESTION_LINE_RE.match(line):
                    continue
                if len(_MULTI_TASK_VERB_RE.findall(line)) >= 2:
                    issues.append({"id": qid, "type": qtype,
                                   "reason": "한 문장 안에 여러 사고 작업을 이어 묻고 있음 (소문항으로 분리 필요)"})
                    break

        # TF: 두 사실을 동시에 판단해야 하는 복합 명제
        if qtype == "tf":
            tf_text = re.sub(r"\s*\(T/F\)\s*$", "", question.strip())
            if _TF_COMPOUND_RE.search(tf_text):
                issues.append({"id": qid, "type": qtype,
                               "reason": "진위형 복합 명제: 두 사실을 동시에 판단해야 하는 구조"})

        # 영어 지시문으로 시작
        if _ENGLISH_DIRECTIVE_RE.match(question):
            issues.append({"id": qid, "type": qtype, "reason": "문제 지시문이 영어로 시작 (Explain/Discuss 등)"})

        # short 답안이 지나치게 긴 서술형
        if qtype == "short" and answer and len(answer.split()) > 20:
            issues.append({"id": qid, "type": qtype, "reason": "단답형 answer가 지나치게 길음"})

    return {"pass": len(issues) == 0, "issues": issues}
