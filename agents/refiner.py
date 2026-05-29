import json
import re
from agents.base import BaseAgentWorker
from tools.client import get_client, retry_call

FLASH = "gemini-2.5-flash"

REFINE_PROMPT = """다음 시험 문제를 피드백을 반영하여 수정하세요.

원본 문제:
{problem}

피드백:
{feedback}

피드백의 모든 사항을 반영하여 개선된 문제를 작성하세요.
원본과 동일한 JSON 형식으로 출력하세요 (id, type, question 필드 유지).
JSON 외 다른 텍스트 없이 JSON만 출력하세요."""

def _extract_json(text: str) -> dict:
    text = text.strip()
    # 마크다운 코드블록 제거
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    return json.loads(text)

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

    def run(self, input_text: str) -> str:
        data = json.loads(input_text)
        problem = data["problem"]
        feedback = data["feedback"]

        refined = self._refine(problem, feedback)
        return json.dumps(refined, ensure_ascii=False, indent=2)
