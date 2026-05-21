import json
from agents.base import BaseAgentWorker
from tools.client import get_client, retry_call

FLASH = "gemini-2.5-flash"

SYSTEM_PROMPT = """당신은 대학 시험 출제 계획 전문가입니다.
교수자의 요구사항을 분석하여 최적의 문제 구성을 계획합니다.
항상 아래 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{{"단답형": <정수>, "에세이형": <정수>, "응용형": <정수>, "난이도": "<easy|medium|hard|mixed>", "기타요구사항": ["항목1", "항목2"]}}

규칙:
- 문제 유형별 개수와 난이도는 반드시 고정 키에 추출. 명시되지 않은 유형은 0.
- 그 외 모든 요구사항(출제 범위, 언어, 포맷, 표지, 정직서약, 페이지 구성 등)은 "기타요구사항" 리스트에 원문 그대로 추가.
- 추가 요구사항이 없으면 "기타요구사항": []"""


class PlannerAgent(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Question Planner", task_id="Task 2")
        self._client = get_client()
        # Chat 히스토리 유지 (교수자 요구사항 수정 가능)
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
        json.loads(raw)  # 유효성 검증
        return raw
