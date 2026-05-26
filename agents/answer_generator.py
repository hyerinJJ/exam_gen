import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from agents.base import BaseAgentWorker
from tools.client import get_client, retry_call
from tools.search_tools import search_arxiv, search_with_google
from tools.search_cache import get_cached, set_cached

FLASH_LITE = "gemini-2.5-flash-lite"
FLASH = "gemini-2.5-flash"

_NO_MARKDOWN = "마크다운 기호(**,##,*,#,__)를 절대 사용하지 마시오."

_CORE_PRINCIPLE = """핵심 원칙: 문제가 요구하는 것에만 정확히 답한다. 요구 이상 절대 확장 금지.
문제를 먼저 읽고 학생이 어떻게 답해야 하는가를 판단한 후 그 형식으로만 작성하라."""

SHORT_ANSWER_PROMPT = f"""{_CORE_PRINCIPLE}
{_NO_MARKDOWN}

단답형 답안 규칙:
- 반드시 용어 또는 단어만 작성. 한 단어.
- 영어 원어가 있으면 괄호 안에 병기. 예: 과적합 (Overfitting)
- 줄글, 설명, 부연 설명 일체 금지.

나쁜 예: "과적합은 모델이 훈련 데이터에 지나치게 맞춰져서 새로운 데이터에 성능이 떨어지는 현상이다."
좋은 예: "과적합 (Overfitting)"

문제: {{question}}"""

ESSAY_PROMPT = f"""{_CORE_PRINCIPLE}
{_NO_MARKDOWN}

문제 유형에 따라 아래 형식 중 하나만 사용하라. 서론·결론·도입부 금지.
- 설명/서술 요구 → 핵심 내용만 3~5문장
- 비교/차이점 요구 → 비교 항목과 차이만
- 단계/절차 요구 → 번호 붙여 각 단계 1~2문장
- 계산 요구 → 풀이 과정과 결과값만
- 사례 제시 요구 → 구체적 사례 1~2개만

{{difficulty_hint}}문제: {{question}}"""

APPLICATION_PROMPT = f"""{_CORE_PRINCIPLE}
{_NO_MARKDOWN}

답안 작성 원칙:
- 답안의 핵심은 반드시 수업에서 배운 개념, 이론, 프레임워크를 시나리오에 적용하는 것이다.
- 참고 자료(arXiv, Google)는 현실 사례나 배경 맥락 확인용으로만 참고하라.
  참고 자료에서만 나오는 내용을 답안의 근거로 쓰지 마라.
- 시나리오 및 질문 재서술 금지.
- 각 관점마다 1~2문장만 작성하라.

{{seed_context}}참고 자료:
{{search_results}}

문제: {{question}}"""

APPLICATION_RUBRIC_PROMPT = f"""응용형 문제의 채점 기준을 작성하세요.
{_NO_MARKDOWN}

채점 구조: 아래 세 축을 기준으로 포인트를 추출하세요.
1. 수업 개념·프레임워크 적용 — 문제에서 명시한 개념을 올바르게 사용했는가
2. 시나리오 요소 연결 — 시나리오의 구체적 상황·조건을 근거로 활용했는가
3. 연결 판단 — 개념과 시나리오를 논리적으로 연결하여 결론을 도출했는가

포인트 3~4개, 합계 10점. 핵심 포인트에 높은 점수. 점수는 정수만.
반드시 아래 형식으로만 출력하세요. 다른 텍스트 없이.

[포인트 1]: 내용 (N점)
[포인트 2]: 내용 (N점)
[포인트 3]: 내용 (N점)

{{seed_context}}문제: {{question}}
모범답안: {{answer}}"""

RUBRIC_PROMPT = f"""문제와 모범답안을 보고 채점 기준을 작성하세요.
{_NO_MARKDOWN}
문제가 요구하는 답의 유형을 먼저 파악해 아래 형식 중 하나만 출력하세요. 다른 텍스트 없이.

1) TF형:
정답(1점): [T 또는 F]
오답:(0점): 그 외

2) 단어/용어형:
정답(10점): [정답]
오답(0점): 그 외

3) 나열형 (N가지):
총 N항목. 항목당 [10/N]점. 순서 무관.
- [항목1]([N점])
- [항목2]([N점])

4) 순서/단계형 (N단계):
총 N단계. 단계당 [10/N]점. 순서 오류 시 해당 단계 0점.
1단계([N점]): [내용]
2단계([N점]): [내용]

5) 계산형 (풀이 N단계 N점, 정답 N점):
필요한 수식 정확히 작성 시(N점)
풀이와 정답 점수를 먼저 동일하게 배분하세요. 그 다음, 풀이 단계를 N단계로 나누어 점수를 배분하세요.

6) 서술형:
포인트별 중요도에 따라 점수를 다르게 배분하세요. 핵심 포인트 > 부수적 포인트. 합계 반드시 10점. 점수는 정수만. 나누어 떨어지지 않으면 중요도 높은 포인트에 나머지 점수 추가.
[포인트 1]: 내용 (N점)
[포인트 2]: 내용 (N점)
[포인트 3]: 내용 (N점)

문제: {{question}}
모범답안: {{answer}}"""

TF_ANSWER_PROMPT = """다음 진위형 문제의 정답을 강의 내용 기준으로 판별하세요.
T(참) 또는 F(거짓) 중 하나만 출력하세요. 다른 텍스트 없이.

문제: {question}"""

TF_RUBRIC_PROMPT = """다음 진위형 문제와 정답에 대해 왜 그 정답인지 강의 내용 기준으로 한 문장만 작성하세요.
다른 텍스트 없이 한 문장만 출력하세요.

문제: {question}
정답: {answer}"""

KEYWORD_PROMPT = """다음 문제에서 arXiv 검색에 적합한 영어 키워드 3~5개를 추출하세요.
반드시 영어 단어만, 공백으로 구분하여 한 줄로만 출력하세요. 다른 텍스트 없이.

문제: {question}"""


def _seed_context(seed: dict) -> str:
    """grading_seed를 프롬프트 주입용 텍스트로 변환. 없으면 빈 문자열 반환."""
    if not seed:
        return ""
    parts = []
    if seed.get("target_framework"):
        parts.append(f"적용 프레임워크: {seed['target_framework']}")
    if seed.get("expected_reasoning"):
        parts.append(f"분석 방향: {seed['expected_reasoning']}")
    if seed.get("answer_direction"):
        parts.append(f"답안 방향: {seed['answer_direction']}")
    if seed.get("must_include"):
        parts.append(f"반드시 포함: {', '.join(seed['must_include'])}")
    if seed.get("rubric_focus"):
        parts.append(f"채점 포인트: {', '.join(seed['rubric_focus'])}")
    for m in seed.get("scenario_mapping", []):
        parts.append(f"시나리오↔개념: {m.get('scenario_element', '')} → {m.get('course_concept', '')}")
    return "\n".join(parts)


def _normalize_tf_answer(raw: str) -> str:
    cleaned = raw.strip().upper()
    if cleaned in ("T", "TRUE", "참", "O"):
        return "T"
    if cleaned in ("F", "FALSE", "거짓", "X"):
        return "F"
    if cleaned.startswith("T") or "TRUE" in cleaned or "참" in cleaned:
        return "T"
    return "F"


class AnswerGeneratorAgent(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Answer Generator", task_id="Task 4")
        self._client = get_client()

    def _extract_english_keywords(self, question: str) -> str:
        prompt = KEYWORD_PROMPT.format(question=question)
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=prompt))
        return response.text.strip()

    def _generate_rubric(self, question: str, answer: str) -> str:
        prompt = RUBRIC_PROMPT.format(question=question, answer=answer)
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=prompt))
        return response.text.strip()

    def _generate_short_answer(self, question: dict) -> dict:
        seed = question.get("grading_seed")
        if seed and seed.get("expected_answer"):
            answer = seed["expected_answer"]
            variants = seed.get("accepted_variants", [])
            if variants:
                rubric = f"정답(10점): {answer}\n허용 답안: {', '.join(variants)}\n오답(0점): 그 외"
            else:
                rubric = f"정답(10점): {answer}\n오답(0점): 그 외"
            return {"answer": answer, "rubric": rubric}
        prompt = SHORT_ANSWER_PROMPT.format(question=question["question"])
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=prompt))
        answer = response.text.strip()
        rubric = self._generate_rubric(question["question"], answer)
        return {"answer": answer, "rubric": rubric}

    def _generate_essay_answer(self, question: dict) -> dict:
        diff = question.get("difficulty", "")
        if diff == "hard":
            diff_hint = "난이도: hard — 비판적 분석과 종합적 이해가 드러나는 수준으로 답하라.\n"
        elif diff == "easy":
            diff_hint = "난이도: easy — 핵심 개념만 간결하게 서술하라.\n"
        else:
            diff_hint = ""
        seed_ctx = _seed_context(question.get("grading_seed"))
        if seed_ctx:
            diff_hint += f"출제 의도:\n{seed_ctx}\n"
        prompt = ESSAY_PROMPT.format(question=question["question"], difficulty_hint=diff_hint)
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=prompt))
        answer = response.text.strip()
        rubric = self._generate_rubric(question["question"], answer)
        return {"answer": answer, "rubric": rubric}

    def _generate_application_answer(self, question: dict) -> dict:
        seed = question.get("grading_seed") or {}
        has_seed = bool(
            seed.get("target_framework")
            or seed.get("scenario_mapping")
            or seed.get("expected_reasoning")
        )

        if has_seed:
            search_results = ""
        else:
            en_keywords = self._extract_english_keywords(question["question"])

            arxiv_query = en_keywords
            arxiv_results = get_cached(arxiv_query)
            if arxiv_results is None:
                try:
                    arxiv_results = search_arxiv(en_keywords, max_results=2)
                except Exception:
                    arxiv_results = "(arXiv 검색 결과 없음)"
                set_cached(arxiv_query, arxiv_results)

            google_query = f"{question['question'][:80]} 해결 방법 사례"
            google_results = get_cached(google_query)
            if google_results is None:
                google_results = search_with_google(google_query)
                set_cached(google_query, google_results)

            search_results = f"[arXiv]\n{arxiv_results}\n\n[Google]\n{google_results}"

        seed_ctx = _seed_context(seed)
        seed_block = f"출제 의도:\n{seed_ctx}\n\n" if seed_ctx else ""

        prompt = APPLICATION_PROMPT.format(
            question=question["question"],
            search_results=search_results,
            seed_context=seed_block,
        )
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH, contents=prompt))
        answer = response.text.strip()
        rubric_prompt = APPLICATION_RUBRIC_PROMPT.format(
            question=question["question"],
            answer=answer,
            seed_context=seed_block,
        )
        rubric_response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=rubric_prompt))
        rubric = rubric_response.text.strip()
        return {"answer": answer, "rubric": rubric}

    def _generate_tf_answer(self, question: dict) -> dict:
        seed = question.get("grading_seed")
        if seed and seed.get("expected_answer"):
            answer = _normalize_tf_answer(seed["expected_answer"])
            reason = seed.get("reason", "")
            if reason:
                rubric = f"정답: {answer} — {reason}"
                return {"answer": answer, "rubric": rubric}
            # reason이 없으면 모델에게 한 문장 이유만 요청
            rubric_prompt = TF_RUBRIC_PROMPT.format(question=question["question"], answer=answer)
            rubric_response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=rubric_prompt))
            rubric = f"정답: {answer} — {rubric_response.text.strip()}"
            return {"answer": answer, "rubric": rubric}
        # fallback: 정답 방향 정보 없을 때 모델이 직접 판별
        answer_prompt = TF_ANSWER_PROMPT.format(question=question["question"])
        response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=answer_prompt))
        answer = _normalize_tf_answer(response.text)
        rubric_prompt = TF_RUBRIC_PROMPT.format(question=question["question"], answer=answer)
        rubric_response = retry_call(lambda: self._client.models.generate_content(model=FLASH_LITE, contents=rubric_prompt))
        rubric = f"정답: {answer} — {rubric_response.text.strip()}"
        return {"answer": answer, "rubric": rubric}

    def _generate_answer(self, question: dict) -> dict:
        """유형별 라우터 (병렬 실행용)."""
        q_type = question.get("type")
        if q_type == "short":
            return self._generate_short_answer(question)
        if q_type == "application":
            return self._generate_application_answer(question)
        if q_type == "tf":
            return self._generate_tf_answer(question)
        return self._generate_essay_answer(question)

    def run(self, input_text: str) -> str:
        questions = json.loads(input_text)
        results_map: dict = {}

        with ThreadPoolExecutor(max_workers=min(3, max(1, len(questions)))) as executor:
            future_to_q = {executor.submit(self._generate_answer, q): q for q in questions}
            for future in as_completed(future_to_q):
                q = future_to_q[future]
                result = future.result()
                results_map[q["id"]] = {
                    "id": q["id"], "type": q["type"],
                    "question": q["question"], **result,
                }

        ordered = [results_map[q["id"]] for q in questions]
        return json.dumps(ordered, ensure_ascii=False, indent=2)
