import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from agents.collector import CollectorAgent
from agents.topic_extractor import TopicExtractorAgent
from agents.planner import PlannerAgent
from agents.generators import ShortAnswerGenerator, EssayGenerator, ApplicationGenerator, TFGenerator
from agents.answer_generator import AnswerGeneratorAgent
from agents.quality_reviewer import QualityReviewerAgent
from agents.refiner import RefinerAgent
from agents.assembler import AssemblerAgent
from tools.quality_rules import run_quality_rules


_FIXED_PLAN_KEYS = {"단답형", "에세이형", "응용형", "진위형", "난이도"}
_TYPE_PLAN = {"short": "단답형", "essay": "에세이형", "application": "응용형", "tf": "진위형"}


def _generate_questions(topics: list, plan: dict) -> list:
    """ShortAnswer / Essay / Application 병렬 생성 후 합산."""
    difficulty = plan.get("난이도", "mixed")
    scope = ", ".join(f"{k}: {v}" for k, v in plan.items() if k not in _FIXED_PLAN_KEYS)
    question_plan = plan.get("question_plan", [])

    results = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        if question_plan:
            # 신형: planner가 question_plan을 생성한 경우 plan_items 형식 사용
            short_items = [p for p in question_plan if p["question_type"] == "short_answer"]
            essay_items = [p for p in question_plan if p["question_type"] == "essay"]
            app_items   = [p for p in question_plan if p["question_type"] == "application"]
            tf_items    = [p for p in question_plan if p["question_type"] == "tf"]
            tasks_new = [
                (ShortAnswerGenerator(), short_items),
                (EssayGenerator(),       essay_items),
                (ApplicationGenerator(), app_items),
                (TFGenerator(),          tf_items),
            ]
            futures = {
                executor.submit(
                    agent.run,
                    json.dumps({"plan_items": items}, ensure_ascii=False),
                ): agent.name
                for agent, items in tasks_new
                if items
            }
        else:
            # 구형 fallback: topic 이름 문자열만 추출해서 전달
            topic_names = [t["name"] if isinstance(t, dict) else t for t in topics]
            tasks_old = [
                (ShortAnswerGenerator(), plan.get("단답형", 0)),
                (EssayGenerator(),       plan.get("에세이형", 0)),
                (ApplicationGenerator(), plan.get("응용형", 0)),
                (TFGenerator(),          plan.get("진위형", 0)),
            ]
            futures = {
                executor.submit(
                    agent.run,
                    json.dumps({"topics": topic_names, "count": count, "difficulty": difficulty, "scope": scope}, ensure_ascii=False),
                ): agent.name
                for agent, count in tasks_old
                if count > 0
            }

        for future in as_completed(futures):
            name = futures[future]
            try:
                results.extend(json.loads(future.result()))
            except Exception as e:
                print(f"[main] {name} 오류: {e}")

    for i, q in enumerate(results, start=1):
        q["id"] = f"Q{i}"
    return results


def _generate_answers(questions: list) -> list:
    """모든 유형 병렬로 모범답안 생성."""
    print(f"  전체 {len(questions)}개 병렬 생성")
    answer_gen = AnswerGeneratorAgent()
    return json.loads(answer_gen.run(json.dumps(questions, ensure_ascii=False)))


def _normalize_reason(reason: str) -> str:
    """숫자를 N으로 치환해 escalation 비교에 쓸 이슈 유형 키를 생성."""
    return re.sub(r"\d+", "N", reason.strip())[:60]


def _find_plan_item(bad_id: str, plan: dict):
    """Q{n} ID로 question_plan 항목 검색. 없으면 None."""
    question_plan = plan.get("question_plan", [])
    if not question_plan:
        return None
    try:
        idx = int(bad_id.lstrip("Q")) - 1
        if 0 <= idx < len(question_plan):
            return question_plan[idx]
    except (ValueError, AttributeError):
        pass
    return None


def _regenerate_qa(bad_id: str, iss: dict, qa_pairs: list, idx: int,
                   topics: list, plan: dict, answer_gen: AnswerGeneratorAgent) -> bool:
    """generator 기반 재생성. 가능하면 question_plan 항목 사용."""
    q_type = iss.get("type") or qa_pairs[idx].get("type", "short")
    type_to_gen = {
        "short": ShortAnswerGenerator(),
        "essay": EssayGenerator(),
        "application": ApplicationGenerator(),
        "tf": TFGenerator(),
    }
    gen = type_to_gen.get(q_type)
    if gen is None:
        return False
    try:
        plan_item = _find_plan_item(bad_id, plan)
        if plan_item:
            raw_q = gen.run(json.dumps({"plan_items": [plan_item]}, ensure_ascii=False))
            mode = "plan_item"
        else:
            difficulty = plan.get("난이도", "mixed")
            scope = ", ".join(f"{k}: {v}" for k, v in plan.items() if k not in _FIXED_PLAN_KEYS)
            topic_names = [t["name"] if isinstance(t, dict) else t for t in topics]
            raw_q = gen.run(json.dumps(
                {"topics": topic_names, "count": 1, "difficulty": difficulty, "scope": scope},
                ensure_ascii=False,
            ))
            mode = "fallback"
        new_qs = json.loads(raw_q)
        if not new_qs:
            return False
        new_q = new_qs[0]
        new_q["id"] = bad_id
        raw_a = answer_gen.run(json.dumps([new_q], ensure_ascii=False))
        new_qa = json.loads(raw_a)
        if new_qa:
            qa_pairs[idx] = new_qa[0]
            print(f"    {bad_id} 재생성 완료 (generator/{mode})")
            return True
    except Exception as e:
        print(f"    {bad_id} 재생성 실패: {e}")
    return False


def _refine_qa(bad_id: str, iss: dict, qa_pairs: list, idx: int,
               refiner: RefinerAgent, answer_gen: AnswerGeneratorAgent) -> bool:
    """RefinerAgent 기반 targeted refine."""
    try:
        refined_text = refiner.run(json.dumps({
            "problem": qa_pairs[idx],
            "feedback": f"품질검토 지적: {iss.get('reason', '')}. 이 지적이 사라지도록 문제를 수정하라.",
        }, ensure_ascii=False))
        refined = json.loads(refined_text)
        refined["id"] = bad_id
        raw_a = answer_gen.run(json.dumps([refined], ensure_ascii=False))
        new_qa = json.loads(raw_a)
        qa_pairs[idx] = new_qa[0] if new_qa else refined
        print(f"    {bad_id} targeted refine 완료")
        return True
    except Exception as e:
        print(f"    {bad_id} targeted refine 실패: {e}")
    return False


def _apply_fixes(qa_pairs: list, issues: list, topics: list, plan: dict,
                 issue_history: dict, unresolved: list) -> list:
    """escalation-aware 자동 수정.

    issue_history[(id, normalized_reason)] 발생 횟수에 따라:
    1회 → generator 재생성
    2회 → RefinerAgent targeted refine
    3회+ → unresolved에 기록, 수정 포기
    """
    answer_gen = AnswerGeneratorAgent()
    refiner = RefinerAgent()
    id_to_idx = {qa["id"]: i for i, qa in enumerate(qa_pairs)}

    for iss in issues:
        bad_id = iss["id"]
        if bad_id == "Q0":
            continue
        idx = id_to_idx.get(bad_id)
        if idx is None:
            continue

        key = (bad_id, _normalize_reason(iss.get("reason", "")))
        count = issue_history.get(key, 0) + 1
        issue_history[key] = count

        if count == 1:
            _regenerate_qa(bad_id, iss, qa_pairs, idx, topics, plan, answer_gen)
        elif count == 2:
            print(f"    {bad_id} 동일 지적 2회 → targeted refine")
            _refine_qa(bad_id, iss, qa_pairs, idx, refiner, answer_gen)
        else:
            print(f"    [미해결] {bad_id}: {iss.get('reason', '')} (3회 반복 → 수정 포기)")
            unresolved.append(iss)

    return qa_pairs


def _run_quality_step(qa_pairs: list, plan: dict, topics: list) -> tuple:
    """rule-based check → AI reviewer 최대 2회. (qa_pairs, unresolved_issues) 반환."""
    issue_history: dict = {}
    unresolved: list = []

    # ─ rule-based ──────────────────────────────────────────────────────────
    rule_result = run_quality_rules(qa_pairs, plan)
    if not rule_result["pass"]:
        print(f"  [rule] 규칙 위반 {len(rule_result['issues'])}개:")
        for iss in rule_result["issues"]:
            print(f"    {iss['id']}: {iss['reason']}")
        qa_pairs = _apply_fixes(qa_pairs, rule_result["issues"], topics, plan, issue_history, unresolved)
    else:
        print("  [rule] 규칙 검사 통과.")

    # ─ AI reviewer 1차 ─────────────────────────────────────────────────────
    reviewer = QualityReviewerAgent()
    print("  AI reviewer 1차 검토...")
    review1 = json.loads(reviewer.run(json.dumps({"questions": qa_pairs, "plan": plan}, ensure_ascii=False)))

    if review1["pass"]:
        print("  AI reviewer 1차 통과.")
        return qa_pairs, unresolved

    ai_issues1 = review1.get("issues", [])
    fixed_ids = {iss["id"] for iss in ai_issues1}
    print(f"  [1차] AI reviewer 문제 {len(ai_issues1)}개:")
    for iss in ai_issues1:
        print(f"    {iss['id']}: {iss.get('reason', '')}")
    qa_pairs = _apply_fixes(qa_pairs, ai_issues1, topics, plan, issue_history, unresolved)

    # ─ AI reviewer 2차 (수정 문항만) ────────────────────────────────────────
    fixed_pairs = [q for q in qa_pairs if q["id"] in fixed_ids]
    if not fixed_pairs:
        return qa_pairs, unresolved

    sub_plan: dict = {}
    for q in fixed_pairs:
        plan_key = _TYPE_PLAN.get(q.get("type", ""), "단답형")
        sub_plan[plan_key] = sub_plan.get(plan_key, 0) + 1
    sub_plan["난이도"] = plan.get("난이도", "mixed")
    if plan.get("question_plan"):
        sub_plan["question_plan"] = plan["question_plan"]

    print(f"  AI reviewer 2차 검토 ({len(fixed_pairs)}개 수정 문항)...")
    review2 = json.loads(reviewer.run(json.dumps({"questions": fixed_pairs, "plan": sub_plan}, ensure_ascii=False)))

    if review2["pass"]:
        print("  AI reviewer 2차 통과.")
    else:
        ai_issues2 = review2.get("issues", [])
        print(f"  [2차] 남은 문제 {len(ai_issues2)}개 — 추가 AI 검토 없이 기록")
        for iss in ai_issues2:
            print(f"    [미해결] {iss['id']}: {iss.get('reason', '')}")
            unresolved.append(iss)

    return qa_pairs, unresolved


def _assemble(assembler: AssemblerAgent, qa_pairs: list, plan: dict) -> dict:
    return json.loads(assembler.run(json.dumps({"qa_pairs": qa_pairs, "plan": plan}, ensure_ascii=False)))


def run_pipeline(file_paths: list[str], requirements: str) -> dict:
    print("\n=== [Step 0] 파일 수집 ===")
    collector = CollectorAgent()
    raw_text = collector.run("\n".join(file_paths))

    print("\n=== [Step 1] 토픽 추출 ===")
    extractor = TopicExtractorAgent()
    topic_data = json.loads(extractor.run(raw_text))
    topics = topic_data.get("topics", [])
    topic_names = [t.get("name", "") for t in topics]
    print(f"  토픽 {len(topic_names)}개: {', '.join(topic_names)}")

    print("\n=== [Step 2] 문제 계획 ===")
    planner = PlannerAgent()
    plan = json.loads(planner.run(
        json.dumps({"topic_extraction": topic_data, "requirements": requirements}, ensure_ascii=False)
    ))

    _COUNT_KEYS = {"단답형", "에세이형", "응용형", "진위형", "난이도"}
    _FORMAT_KEYS = {"시험제목", "시험종류", "담당교수", "레이아웃"}

    count_parts = [f"단답형 {plan.get('단답형', 0)}개", f"에세이형 {plan.get('에세이형', 0)}개",
                   f"응용형 {plan.get('응용형', 0)}개", f"진위형 {plan.get('진위형', 0)}개",
                   f"난이도: {plan.get('난이도', 'mixed')}"]
    print(f"  문제 구성: {' | '.join(count_parts)}")

    fmt_parts = [f"{k}={plan[k]}" for k in _FORMAT_KEYS if k in plan]
    if fmt_parts:
        print(f"  포맷 설정: {' | '.join(fmt_parts)}")

    _HIDDEN_KEYS = {"question_plan"}
    etc_parts = [f"{k}={v}" for k, v in plan.items() if k not in _COUNT_KEYS and k not in _FORMAT_KEYS and k not in _HIDDEN_KEYS]
    if etc_parts:
        print(f"  기타 요구사항: {' | '.join(etc_parts)}")

    print("\n=== [Step 3] 문제 병렬 생성 ===")
    questions = _generate_questions(topics, plan)
    print(f"  생성된 문제 수: {len(questions)}")

    print("\n=== [Step 4] 모범답안 생성 ===")
    qa_pairs = _generate_answers(questions)

    print("\n=== [Step 5] 품질 검토 ===")
    qa_pairs, unresolved = _run_quality_step(qa_pairs, plan, topics)
    if unresolved:
        print(f"\n  ⚠ 미해결 품질 문제 {len(unresolved)}개:")
        for iss in unresolved:
            print(f"    {iss['id']}: {iss.get('reason', '')}")

    print("\n=== [Step 6] 초안 조립 ===")
    assembler = AssemblerAgent()
    output = _assemble(assembler, qa_pairs, plan)

    print("\n=== [Step 7] 교수자 검토 ===")
    refiner = RefinerAgent()
    while True:
        print("\noutput/exam.docx와 output/answer_key.docx를 모두 확인한 후 엔터를 누르세요.")
        input()

        print("수정할 문제의 피드백을 입력하세요 (형식: 'Q1: 피드백내용', 빈 줄로 제출):")
        feedback_lines = []
        while True:
            line = input()
            if not line.strip():
                break
            feedback_lines.append(line.strip())

        if not feedback_lines:
            print("[main] 검토 완료 → 파이프라인 종료")
            break

        id_to_idx = {qa["id"]: i for i, qa in enumerate(qa_pairs)}
        for line in feedback_lines:
            if ":" not in line:
                print(f"[main] 형식 오류, 건너뜀: {line}")
                continue
            problem_id, feedback_text = line.split(":", 1)
            problem_id = problem_id.strip()
            idx = id_to_idx.get(problem_id)
            if idx is None:
                print(f"[main] 문제 ID '{problem_id}' 없음, 건너뜀")
                continue
            refined_text = refiner.run(
                json.dumps({"problem": qa_pairs[idx], "feedback": feedback_text.strip()}, ensure_ascii=False)
            )
            qa_pairs[idx] = json.loads(refined_text)
        print(f"[main] {len(feedback_lines)}개 문제 재작성 완료.")

        print("\n=== 재조립 ===")
        output = _assemble(assembler, qa_pairs, plan)
        print("파일이 업데이트되었습니다. 다시 확인해 주세요.")

    print("\n=== 파이프라인 완료 ===")
    print(f"  시험지:  {output['exam']}")
    print(f"  답안지:  {output['answer_key']}")
    return output


def _load_inputs(input_dir: str = "input") -> tuple[list[str], str]:
    LECTURE_EXTS = {".pdf", ".pptx", ".ppt", ".mp4", ".mov", ".avi", ".mkv", ".txt"}

    if not os.path.isdir(input_dir):
        os.makedirs(input_dir)
        print(f"input/ 폴더에 강의자료와 requirements.txt를 넣고 다시 실행하세요.")
        sys.exit(0)

    req_path = os.path.join(input_dir, "requirements.txt")
    if not os.path.isfile(req_path):
        print("input/ 폴더에 requirements.txt를 넣어주세요.")
        sys.exit(0)

    requirements = open(req_path, encoding="utf-8").read().strip()

    file_paths = [
        os.path.join(input_dir, f)
        for f in os.listdir(input_dir)
        if os.path.splitext(f)[1].lower() in LECTURE_EXTS and f != "requirements.txt"
    ]

    if not file_paths:
        print("input/ 폴더에 강의자료를 넣어주세요.")
        sys.exit(0)

    return file_paths, requirements


if __name__ == "__main__":
    file_paths, requirements = _load_inputs()
    run_pipeline(file_paths, requirements)
