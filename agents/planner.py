import json
from agents.base import BaseAgentWorker
from tools.client import get_client, retry_call

FLASH = "gemini-2.5-flash"

SYSTEM_PROMPT = """당신은 대학 시험 출제 계획 전문가입니다.
교수자의 요구사항을 분석하여 모든 정보를 JSON으로 정리합니다.
다른 텍스트 없이 JSON만 출력하세요.

규칙:
- 아래 4개 고정 키는 반드시 정확한 이름으로 포함. 명시되지 않은 유형은 0.
  "단답형": <정수>    (키 이름 절대 변경 금지. "단답형 5개" 같은 형태 금지)
  "에세이형": <정수>  (키 이름 절대 변경 금지. "에세이 3개" 같은 형태 금지)
  "응용형": <정수>    (키 이름 절대 변경 금지)
  "난이도": "easy|medium|hard|mixed"
- 시험지 표지/포맷 관련 정보는 아래 정해진 키 이름을 사용:
  "시험제목": "시험지 제목"  (명시된 경우에만 포함)
  "시험종류": "중간고사|기말고사|퀴즈|과제|기타"  (명시된 경우에만 포함)
  "담당교수": "교수 이름"  (명시된 경우에만 포함)
  "레이아웃": "페이지당 문제 1개" 또는 "여러 문제"  (명시된 경우에만 포함)
- 토픽 목록은 절대 JSON에 포함하지 않음 (입력으로 받지만 출력에는 제외)
- 그 외 파악되는 추가 요구사항은 직관적인 한국어 키로 추가. 없으면 포함하지 않음.

예시 입력: "단답형 5개, 에세이형 3개. 시험 제목 Scientific Management, 중간고사, 담당교수 박우진, 페이지당 문제 1개"
예시 출력: {{"단답형": 5, "에세이형": 3, "응용형": 0, "난이도": "medium", "시험제목": "Scientific Management", "시험종류": "중간고사", "담당교수": "박우진", "레이아웃": "페이지당 문제 1개"}}"""

# LLM이 고정 키를 변형해 출력해도 복구하는 정규화
_KEY_FRAGMENTS = {"단답": "단답형", "에세이": "에세이형", "응용": "응용형"}


def _normalize_plan(plan: dict) -> dict:
    result = {}
    for k, v in plan.items():
        canonical = next((c for frag, c in _KEY_FRAGMENTS.items() if frag in k and k != c), None)
        result[canonical if canonical else k] = v
    for key in ("단답형", "에세이형", "응용형"):
        result.setdefault(key, 0)
    result.setdefault("난이도", "mixed")
    return result


class PlannerAgent(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Question Planner", task_id="Task 2")
        self._client = get_client()
        self._chat = self._client.chats.create(
            model=FLASH,
            config={"system_instruction": SYSTEM_PROMPT},
        )

    def run(self, input_text: str) -> str:
        response = retry_call(lambda: self._chat.send_message(input_text))
        raw = response.text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        plan = _normalize_plan(json.loads(raw))
        return json.dumps(plan, ensure_ascii=False)
