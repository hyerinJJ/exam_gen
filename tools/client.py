import os
import re
import time
from dotenv import load_dotenv
from google import genai
from google.genai.errors import ServerError, ClientError

load_dotenv()


def _parse_retry_delay(error, fallback: int = 60) -> int:
    """에러 메시지에서 retryDelay 값(초)을 파싱. 없으면 fallback 반환."""
    match = re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+)", str(error))
    return int(match.group(1)) + 5 if match else fallback


_RETRIABLE_CODES = {429, 503, 500}


def retry_call(fn, max_retries: int = 5, base_delay: int = 60):
    """429/503만 재시도. 인증·권한 오류는 즉시 raise."""
    for attempt in range(max_retries):
        try:
            return fn()
        except (ServerError, ClientError) as e:
            code = getattr(e, "code", None) or getattr(e, "status_code", None)
            # 숫자 코드가 없으면 문자열에서 파싱
            if code is None:
                m = re.search(r"\b(4\d\d|5\d\d)\b", str(e))
                code = int(m.group(1)) if m else 0
            if code not in _RETRIABLE_CODES:
                raise  # 인증(401/403), 잘못된 요청(400) 등은 즉시 실패
            if attempt < max_retries - 1:
                wait = _parse_retry_delay(e, fallback=base_delay * (attempt + 1))
                print(f"[Gemini API] 오류({code}), {wait}초 후 재시도... ({attempt + 1}/{max_retries})")
                time.sleep(wait)
            else:
                raise


def get_client() -> genai.Client:
    gcp_project = os.getenv("GCP_PROJECT_ID")
    if gcp_project:
        location = os.getenv("GCP_LOCATION", "us-central1")
        return genai.Client(vertexai=True, project=gcp_project, location=location)

    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)

    raise ValueError(
        "환경변수 미설정: GCP_PROJECT_ID (Vertex AI) 또는 GEMINI_API_KEY (AI Studio) 중 하나를 .env에 입력하세요."
    )
