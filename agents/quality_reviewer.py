import json
from agents.base import BaseAgentWorker
from tools.client import get_client, retry_call

FLASH = "gemini-2.5-flash"

REVIEW_PROMPT = """다음 시험 문제들을 아래 기준으로 자동 검토하세요.

검토 기준:
1. 마크다운 기호(**,##,*,#,__)가 문제 본문에 포함되어 있는가
2. 단답형(short)이 단어/짧은 구/짧은 목록으로 답할 수 있는 형식인가 (긴 서술이 필요하면 부적합)
3. 에세이형(essay)이 실제 서술형 답변이 필요한 열린 질문인가 (단어 하나로 답할 수 있으면 부적합)
4. 응용형(application)에 구체적인 상황/시나리오가 3줄 이내로 제시되어 있는가
5. 문제 개수가 계획과 일치하는가
6. high importance·core 토픽이 최소 1개 이상 출제되었는가 (출제 메타데이터 기준)
7. detail/example/background 토픽만으로 문제가 구성되어 있지는 않은가
8. easy/medium/hard 난이도가 지나치게 한쪽으로 쏠리지 않는가

출제 계획:
{plan_info}

출제 메타데이터 요약:
{plan_summary}

문제 목록:
{problems}

문제가 없으면 pass:true, 있으면 pass:false와 해당 항목을 반환하세요.
반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트 없이.
{{"pass": true, "issues": []}}
또는
{{"pass": false, "issues": [{{"id": "Q2", "type": "short", "reason": "마크다운 ** 포함"}}]}}"""


def _build_plan_summary(question_plan: list) -> str:
    """question_plan에서 메타데이터 요약을 생성."""
    if not question_plan:
        return "(없음)"

    core_high = sum(
        1 for q in question_plan
        if q.get("topic_meta", {}).get("importance") == "high"
        and q.get("topic_meta", {}).get("scope") == "core"
    )
    diff_dist: dict = {}
    for q in question_plan:
        d = q.get("difficulty", "medium")
        diff_dist[d] = diff_dist.get(d, 0) + 1

    scopes = [q.get("topic_meta", {}).get("scope", "") for q in question_plan]
    non_core = sum(1 for s in scopes if s in ("detail", "example", "background"))

    lines = [
        f"core·high 토픽 출제 계획 수: {core_high}/{len(question_plan)}",
        f"난이도 분포: {json.dumps(diff_dist, ensure_ascii=False)}",
        f"detail/example/background 토픽 비율: {non_core}/{len(question_plan)}",
    ]
    return "\n".join(lines)


class QualityReviewerAgent(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Quality Reviewer", task_id="Task 5")
        self._client = get_client()

    def run(self, input_text: str) -> str:
        """Input: {"questions": [...qa_pairs...], "plan": {...}}
        Output: {"pass": bool, "issues": [{"id", "type", "reason"}]}"""
        data = json.loads(input_text)
        questions = data["questions"]
        plan = data.get("plan", {})

        plan_info = json.dumps(
            {k: v for k, v in plan.items() if k in {"단답형", "에세이형", "응용형", "난이도"}},
            ensure_ascii=False,
        )
        plan_summary = _build_plan_summary(plan.get("question_plan", []))
        problems_text = json.dumps(
            [{"id": q["id"], "type": q.get("type", ""), "question": q["question"]} for q in questions],
            ensure_ascii=False,
            indent=2,
        )

        prompt = REVIEW_PROMPT.format(
            plan_info=plan_info,
            plan_summary=plan_summary,
            problems=problems_text,
        )
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH, contents=prompt))
        raw = response.text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        json.loads(raw)  # validate
        return raw
