import json
from agents.base import BaseAgentWorker
from tools.client import get_client, retry_call

FLASH = "gemini-2.5-flash"

REVIEW_PROMPT = """다음 시험 문제들을 평가하세요.

문제 목록:
{problems}

각 문제에 대해 다음 기준으로 평가하세요:
1. 명확성: 문제가 명확하고 이해하기 쉬운가?
2. 적절성: 난이도와 유형이 적절한가?
3. 완전성: 답안이 완전하고 정확한가?
4. 학습 목표 부합성: 강의 내용을 잘 반영하는가?

평가 결과를 다음 형식으로 출력하세요:
- 전체 평가 요약
- 각 문제별 개선이 필요한 사항 (문제 ID와 함께)
- 종합 의견"""


class QualityReviewerAgent(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Quality Reviewer", task_id="Task 5")
        self._client = get_client()

    def _ai_review(self, problems: list) -> str:
        problems_text = json.dumps(problems, ensure_ascii=False, indent=2)
        prompt = REVIEW_PROMPT.format(problems=problems_text)
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH, contents=prompt))
        return response.text.strip()

    def run(self, input_text: str) -> str:
        problems = json.loads(input_text)

        # AI 1차 평가
        ai_feedback = self._ai_review(problems)

        # 콘솔 출력
        print("\n" + "=" * 60)
        print("[AI 품질 평가 결과]")
        print("=" * 60)
        print(ai_feedback)
        print("=" * 60)

        problem_ids = [p["id"] for p in problems]
        print(f"\n문제 목록: {', '.join(problem_ids)}")
        print("\n[교수자 검토]")
        print("  p = 통과 (조립 단계로 진행)")
        print("  i = 개별 문제 재생성")
        print("  r = 전체 재생성 (planner부터)")

        while True:
            decision_input = input("\n선택 (p/i/r): ").strip().lower()
            if decision_input in ("p", "i", "r"):
                break
            print("p, i, r 중 하나를 입력하세요.")

        selected_ids = []
        if decision_input == "i":
            print(f"재생성할 문제 ID를 입력하세요 (쉼표 구분, 예: Q1,Q3)")
            print(f"사용 가능한 ID: {', '.join(problem_ids)}")
            while True:
                ids_input = input("문제 ID: ").strip()
                selected_ids = [id_.strip() for id_ in ids_input.split(",") if id_.strip()]
                if selected_ids:
                    break
                print("하나 이상의 문제 ID를 입력하세요.")

        decision_map = {"p": "pass", "i": "individual", "r": "regenerate"}
        result = {
            "decision": decision_map[decision_input],
            "feedback": ai_feedback,
            "problem_ids": selected_ids,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
