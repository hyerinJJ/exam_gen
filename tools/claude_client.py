import os
import time
import anthropic

DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
_RETRIABLE_STATUS = {429, 500, 529}


def get_claude_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")
    return anthropic.Anthropic(api_key=api_key)


def claude_generate_text(prompt: str, model: str = DEFAULT_MODEL,
                          max_tokens: int = 8192, max_retries: int = 4) -> str:
    client = get_claude_client()
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except anthropic.APIStatusError as e:
            code = e.status_code
            if code not in _RETRIABLE_STATUS or attempt == max_retries - 1:
                print(f"[Claude API] 오류({code}): {e.message}")
                raise
            wait = 60 * (attempt + 1)
            print(f"[Claude API] 오류({code}), {wait}초 후 재시도... ({attempt + 1}/{max_retries})")
            time.sleep(wait)
        except anthropic.APIConnectionError as e:
            if attempt == max_retries - 1:
                print(f"[Claude API] 연결 오류: {e}")
                raise
            wait = 30 * (attempt + 1)
            print(f"[Claude API] 연결 오류, {wait}초 후 재시도... ({attempt + 1}/{max_retries})")
            time.sleep(wait)
