import json
from agents.base import BaseAgentWorker
from tools.client import get_client, retry_call

MODEL = "gemini-2.5-flash-lite"

PROMPT_TEMPLATE = """다음 강의자료 텍스트를 분석하여 주요 토픽과 핵심 개념을 추출하세요.

반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{{
  "topics": ["토픽1", "토픽2", ...],
  "key_concepts": ["개념1", "개념2", ...]
}}

강의자료:
{text}"""


class TopicExtractorAgent(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Topic Extractor", task_id="Task 1")
        self._client = get_client()

    def run(self, input_text: str) -> str:
        prompt = PROMPT_TEMPLATE.format(text=input_text)
        response = retry_call(lambda: self._client.models.generate_content(
            model=MODEL,
            contents=prompt,
        ))
        raw = response.text.strip()
        # JSON 블록 추출
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        json.loads(raw)  # 유효성 검증
        return raw
