import json
import re
from agents.base import BaseAgentWorker
from tools.client import get_client, retry_call

FLASH = "gemini-2.5-flash"
MAX_ATTEMPTS = 3

REFINE_PROMPT = """다음 시험 문제를 피드백을 반영하여 수정하세요.

원본 문제:
{problem}

피드백:
{feedback}

피드백의 모든 사항을 반영하여 개선된 문제를 작성하세요.
원본과 동일한 JSON 형식으로 출력하세요 (id, type, question 필드 유지).
JSON 외 다른 텍스트 없이 JSON만 출력하세요."""

SELF_EVAL_PROMPT = """다음 수정된 시험 문제를 평가하세요.

수정된 문제:
{problem}

적용된 피드백:
{feedback}

1~5점 척도로 점수를 매기세요:
5점: 피드백이 완벽히 반영되고 문제 품질이 우수함
4점: 피드백이 잘 반영되고 품질이 양호함
3점: 피드백이 부분적으로 반영됨
2점: 피드백 반영이 미흡함
1점: 피드백이 거의 반영되지 않음

마지막 줄에 반드시 "점수: X" 형식으로 점수만 출력하세요."""


def _extract_json(text: str) -> dict:
    text = text.strip()
    # 마크다운 코드블록 제거
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    return json.loads(text)


def _extract_score(text: str) -> int:
    match = re.search(r"점수\s*:\s*([1-5])", text)
    if match:
        return int(match.group(1))
    # 숫자만 있는 경우 fallback
    numbers = re.findall(r"\b([1-5])\b", text)
    return int(numbers[-1]) if numbers else 3


class RefinerAgent(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Question Refiner", task_id="Task 6")
        self._client = get_client()

    def _refine(self, problem: dict, feedback: str) -> dict:
        prompt = REFINE_PROMPT.format(
            problem=json.dumps(problem, ensure_ascii=False, indent=2),
            feedback=feedback,
        )
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH, contents=prompt))
        return _extract_json(response.text)

    def _self_evaluate(self, problem: dict, feedback: str) -> int:
        prompt = SELF_EVAL_PROMPT.format(
            problem=json.dumps(problem, ensure_ascii=False, indent=2),
            feedback=feedback,
        )
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH, contents=prompt))
        return _extract_score(response.text)

    def run(self, input_text: str) -> str:
        data = json.loads(input_text)
        problem = data["problem"]
        feedback = data["feedback"]

        current = problem
        for attempt in range(1, MAX_ATTEMPTS + 1):
            refined = self._refine(current, feedback)
            score = self._self_evaluate(refined, feedback)

            print(f"[Refiner] 시도 {attempt}/{MAX_ATTEMPTS} - 자기평가 점수: {score}/5")

            if score >= 4:
                return json.dumps(refined, ensure_ascii=False, indent=2)

            current = refined  # 다음 시도의 입력으로 사용

        # 3회 후에도 4점 미만이면 마지막 결과 반환
        print(f"[Refiner] 최대 시도 초과, 마지막 결과 반환")
        return json.dumps(current, ensure_ascii=False, indent=2)
