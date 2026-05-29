import json
from agents.base import BaseAgentWorker
from tools.client import get_client, retry_call

FLASH = "gemini-2.5-flash"

REVIEW_PROMPT = """다음 시험 문제들을 아래 기준으로 자동 검토하세요.

검토 기준:
1. 마크다운 기호(**,##,*,#,__)가 문제 본문에 포함되지 않았는가
2. 단답형(short)이 단어/짧은 구로 답할 수 있는 형식인가 (긴 서술이 필요하면 부적합)
3. 에세이형(essay)이 실제 서술형 답변이 필요한 열린 질문인가 (단어 하나로 답할 수 있으면 부적합)
4. 에세이형(essay)·응용형(application)에서 채점 포인트가 여럿이면 (1) (2) (3) 소문항으로 분리되어 있는가; 소문항으로 나뉘어 각 소문항이 하나의 사고 작업이면 적합; 한 문장 안에서 여러 작업을 이어 묻는다면 ("설명하고 평가하고 제시하시오" 등) 부적합
5. 문제 안에 정답이 이미 들어 있지 않은가; 다음 중 하나라도 해당하면 부적합: (a) 빈칸 앞뒤 문맥만으로 정답 단어를 추론할 수 있는 경우, (b) 질문 안에 정답 용어가 그대로 포함된 경우 (예: "개념 설계란 무엇인가"에서 '개념 설계'가 정답), (c) 소문항 (2)가 소문항 (1)의 정답을 전제로 사용해 (1) 없이도 (2)에서 정답을 추론할 수 있는 경우, (d) 응용형 상황 묘사가 "X 방식이 비효율적이다"처럼 정답 방향을 직접 시사하는 경우
6. 전체 문제에서 같은 개념이 반복되고 있지 않은가
7. 문제 지시문이 한국어로 작성되어 있는가 ("Explain...", "Discuss..."처럼 지시문 전체가 영어 문장이면 부적합)
8. 문제 개수가 계획과 일치하는가
9. core 토픽이 최소 1개 이상 출제되었는가 (출제 메타데이터 기준)
10. 에세이형(essay)이나 응용형(application)의 문제가 과도하게 길지는 않은가; 소문항이 4개 이상이거나 지시문이 5줄 이상이면 부적합
11. 진위형(tf): 서로 다른 두 개념을 동시에 독립적으로 판단해야 하는 명제인가; "A는 X이고 B는 Y이다"처럼 A와 B가 완전히 별개 개념이라 하나가 틀려도 다른 하나는 별도 판단이 필요한 경우만 부적합; 인과·목적·속성 서술("A이기 때문에 B이다", "A의 목적은 B이다")은 허용; 질문형·나열형은 부적합
12. 진위형(tf): 문장 끝에 "(T/F)"가 있는가
13. 진위형(tf): 표현이 지나치게 약해서 (예: "~할 수도 있다", "~인 경우도 있다") 내용을 몰라도 무조건 F가 되는 문제가 아닌가
14. 진위형(tf): 황당하거나 명백히 틀린 F 문제가 아닌가; 강의 맥락에서 실제로 헷갈릴 만한 명제여야 함
15. 진위형(tf): "항상", "모든", "반드시"가 포함된 문장은 자동 부적합으로 처리하지 말고, 강의 내용상 실제로 그 표현이 옳은지 판단하라


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

    core = sum(
        1 for q in question_plan
        if q.get("topic_meta", {}).get("importance") == "core"
    )
    diff_dist: dict = {}
    for q in question_plan:
        d = q.get("difficulty", "medium")
        diff_dist[d] = diff_dist.get(d, 0) + 1

    non_core = sum(
        1 for q in question_plan
        if q.get("topic_meta", {}).get("importance") in ("supporting", "detail")
    )

    lines = [
        f"core 토픽 출제 계획 수: {core}/{len(question_plan)}",
        f"난이도 분포: {json.dumps(diff_dist, ensure_ascii=False)}",
        f"supporting/detail 토픽 비율: {non_core}/{len(question_plan)}",
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
