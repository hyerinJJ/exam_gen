"""
requirements.txt 내용이 시험지에 반영되는지 파이프라인 추적 테스트.
실행: python tests/trace_requirements.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

REQUIREMENTS = (
    "단답형 5개, 에세이형 3개, 응용형 2개. 난이도는 중간 정도로.\n"
    "시험지 제목은 Scientific Management고, 중간고사 시험이야.\n"
    "담당교수님은 박우진 교수님이고, 문제 하나당 한 페이지를 차지하게 해줘."
)

MOCK_TOPICS = ["Scientific Management", "Work System Framework", "Taylor의 과학적 관리법"]

_FIXED_PLAN_KEYS = {"단답형", "에세이형", "응용형", "난이도"}

SAMPLE_QA = [
    {"id": "Q1", "type": "short",  "question": "테일러의 과학적 관리법 4원칙 중 하나를 쓰시오.", "answer": "과학적 직무 분석", "rubric": "정답(10점): 과학적 직무 분석\n오답(0점): 그 외"},
    {"id": "Q2", "type": "essay",  "question": "Work System Framework의 구성 요소를 설명하시오.", "answer": "기술, 프로세스, 참여자, 정보, 환경, 산출물로 구성된다.", "rubric": "[포인트 1]: 구성 요소 나열 (10점)"},
    {"id": "Q3", "type": "application", "question": "A기업이 자동화를 도입했다. Work System 관점에서 변화를 설명하시오.", "answer": "기술과 프로세스가 변경된다.", "rubric": "[포인트 1]: 변화 설명 (10점)"},
]


def _sep(title):
    print("\n" + "=" * 60)
    print("  " + title)
    print("=" * 60)


def _check(label, actual, expected):
    ok = str(actual) == str(expected)
    mark = "✓" if ok else "✗"
    suffix = f"  (기대: {expected!r})" if not ok else ""
    print(f"  {mark} {label}: {actual!r}{suffix}")
    return ok


# ──────────────────────────────────────────────
_sep("Step 1 - planner.py: requirements -> JSON")
from agents.planner import PlannerAgent

planner = PlannerAgent()
planner_input = f"토픽: {MOCK_TOPICS}\n요구사항: {REQUIREMENTS}"
print(f"입력:\n{planner_input}\n")

plan_raw = planner.run(planner_input)
plan = json.loads(plan_raw)
print("planner 출력 JSON:")
print(json.dumps(plan, ensure_ascii=False, indent=2))

# ──────────────────────────────────────────────
_sep("Step 2 - generators에 전달되는 scope 값")

scope = ", ".join(f"{k}: {v}" for k, v in plan.items() if k not in _FIXED_PLAN_KEYS)
print(f"scope = {scope!r}")
print()
print("generators 입력 예시:")
print(json.dumps(
    {"topics": MOCK_TOPICS, "count": plan.get("단답형", 0),
     "difficulty": plan.get("난이도", "mixed"), "scope": scope},
    ensure_ascii=False, indent=2,
))

# ──────────────────────────────────────────────
_sep("Step 3 - assembler에 전달되는 plan의 포맷 관련 키")

for key in ("시험제목", "시험종류", "담당교수", "레이아웃"):
    val = plan.get(key)
    mark = "✓" if val else "✗ (없음)"
    print(f"  {mark} {key}: {val!r}")

# ──────────────────────────────────────────────
_sep("Step 4 - file_writers._interpret_format 결과")

from tools.file_writers import _interpret_format

fmt = _interpret_format(plan)
print(json.dumps(fmt, ensure_ascii=False, indent=2))

# ──────────────────────────────────────────────
_sep("Step 4b - 샘플 docx 생성 (output/trace_test.docx)")

from tools.file_writers import save_exam_docx, save_answer_key_docx

os.makedirs("output", exist_ok=True)
save_exam_docx(SAMPLE_QA, "output/trace_test.docx", plan=plan)
save_answer_key_docx(SAMPLE_QA, "output/trace_test_answer.docx")
print("생성 완료 → output/trace_test.docx 열어서 표지 확인")

# ──────────────────────────────────────────────
_sep("최종 검증")

results = [
    _check("시험지 제목",     fmt["title"],                   "Scientific Management"),
    _check("시험종류",        fmt["course_info"],              "중간고사"),
    _check("담당교수",        fmt["professor"],                "박우진"),
    _check("페이지당 1문제",  fmt["page_break_per_question"],  True),
    _check("단답형 개수",     plan.get("단답형"),              5),
    _check("에세이형 개수",   plan.get("에세이형"),            3),
    _check("응용형 개수",     plan.get("응용형"),              2),
]

print()
if all(results):
    print("전체 통과 ✓  requirements.txt가 시험지에 정상 반영됩니다.")
else:
    fail = [i + 1 for i, ok in enumerate(results) if not ok]
    print(f"실패 항목 있음 ✗  위 {fail}번 항목을 확인하세요.")
