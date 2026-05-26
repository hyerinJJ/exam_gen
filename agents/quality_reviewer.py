import json
from agents.base import BaseAgentWorker
from tools.client import get_client, retry_call

FLASH = "gemini-2.5-flash"

REVIEW_PROMPT = """다음 시험 문제들을 아래 기준으로 자동 검토하세요.

검토 기준:
1. 마크다운 기호(**,##,*,#,__)가 문제 본문에 포함되지 않았는가
2. 단답형(short)이 단어/짧은 구로 답할 수 있는 형식인가 (긴 서술이 필요하면 부적합)
3. 에세이형(essay)이 실제 서술형 답변이 필요한 열린 질문인가 (단어 하나로 답할 수 있으면 부적합)
4. 에세이형(essay)이나 응용형(application)이 여러 질문을 묻는다면 소문항으로 나누어 묻고 있는가; 문장이 붙어있다면 부적합
5. 문제 안에 정답이 이미 들어 있지 않은가; 문제 안에서 정답을 발견할 수 있다면 부적합
6. 전체 문제에서 같은 개념이 반복되고 있지 않은가
7. 문제 지시문이 한국어로 작성되어 있는가 ("Explain...", "Discuss..."처럼 지시문 전체가 영어 문장이면 부적합)
8. 문제 개수가 계획과 일치하는가
9. high importance·core 토픽이 최소 1개 이상 출제되었는가 (출제 메타데이터 기준)
10. easy/medium/hard 난이도가 출제 계획의 난이도와 적절하게 맞는가
11. 에세이형(essay)이나 응용형(application)의 문제가 과도하게 길지는 않은가; 소문항이 4개 이상이거나 지시문이 4줄 이상이면 부적합
12. 진위형(tf): 하나의 단일 명제만 담고 있는가; 질문형/나열형/복합 서술이면 부적합
13. 진위형(tf): 문장 끝에 "(T/F)"가 있는가
14. 진위형(tf): 표현이 지나치게 약해서 (예: "~할 수도 있다", "~인 경우도 있다") 내용을 몰라도 무조건 F가 되는 문제가 아닌가
15. 진위형(tf): 황당하거나 명백히 틀린 F 문제가 아닌가; 강의 맥락에서 실제로 헷갈릴 만한 명제여야 함
16. 진위형(tf): "항상", "모든", "반드시"가 포함된 문장은 자동 부적합으로 처리하지 말고, 강의 내용상 실제로 그 표현이 옳은지 판단하라


출제 계획:
{plan_info}

출제 메타데이터 요약:
{plan_summary}

문제 목록:
{problems}

참고: 응용형 문제의 채점 기준은 grading_seed로 내부 관리되므로 문제 본문에 채점 기준이 없어도 부적합으로 판단하지 마세요.

문제가 없으면 pass:true, 있으면 pass:false와 해당 항목을 반환하세요.
reason에는 기준 번호가 아닌 구체적인 문제 내용을 한 줄로 작성하세요.
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
            {k: v for k, v in plan.items() if k in {"단답형", "에세이형", "응용형", "진위형", "난이도"}},
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
