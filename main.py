import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from agents.collector import CollectorAgent
from agents.topic_extractor import TopicExtractorAgent
from agents.planner import PlannerAgent
from agents.generators import ShortAnswerGenerator, EssayGenerator, ApplicationGenerator
from agents.answer_generator import AnswerGeneratorAgent
from agents.quality_reviewer import QualityReviewerAgent
from agents.refiner import RefinerAgent
from agents.assembler import AssemblerAgent


_FIXED_PLAN_KEYS = {"단답형", "에세이형", "응용형", "난이도"}


def _generate_questions(topics: list, plan: dict) -> list:
    """ShortAnswer / Essay / Application 병렬 생성 후 합산."""
    difficulty = plan.get("난이도", "mixed")
    scope = ", ".join(f"{k}: {v}" for k, v in plan.items() if k not in _FIXED_PLAN_KEYS)
    tasks = [
        (ShortAnswerGenerator(), plan.get("단답형", 0)),
        (EssayGenerator(),       plan.get("에세이형", 0)),
        (ApplicationGenerator(), plan.get("응용형", 0)),
    ]

    results = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(
                agent.run,
                json.dumps({"topics": topics, "count": count, "difficulty": difficulty, "scope": scope}, ensure_ascii=False),
            ): agent.name
            for agent, count in tasks
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
    """단답형+에세이형 병렬 / 응용형 순차로 모범답안 생성."""
    se_count = sum(1 for q in questions if q.get("type") != "application")
    app_count = sum(1 for q in questions if q.get("type") == "application")
    print(f"  단답형+에세이형 {se_count}개 병렬, 응용형 {app_count}개 순차")
    answer_gen = AnswerGeneratorAgent()
    return json.loads(answer_gen.run(json.dumps(questions, ensure_ascii=False)))


def _auto_fix_questions(qa_pairs: list, issues: list, topics: list, plan: dict) -> list:
    """품질 문제가 있는 문제를 유형별 generator로 1개 재생성 후 답안도 교체."""
    difficulty = plan.get("난이도", "mixed")
    scope = ", ".join(f"{k}: {v}" for k, v in plan.items() if k not in _FIXED_PLAN_KEYS)
    type_to_gen = {
        "short": ShortAnswerGenerator(),
        "essay": EssayGenerator(),
        "application": ApplicationGenerator(),
    }
    answer_gen = AnswerGeneratorAgent()
    id_to_idx = {qa["id"]: i for i, qa in enumerate(qa_pairs)}

    for issue in issues:
        bad_id = issue["id"]
        idx = id_to_idx.get(bad_id)
        if idx is None:
            continue
        q_type = issue.get("type") or qa_pairs[idx].get("type", "short")
        gen = type_to_gen.get(q_type)
        if gen is None:
            continue
        try:
            raw_q = gen.run(json.dumps(
                {"topics": topics, "count": 1, "difficulty": difficulty, "scope": scope},
                ensure_ascii=False,
            ))
            new_qs = json.loads(raw_q)
            if not new_qs:
                continue
            new_q = new_qs[0]
            new_q["id"] = bad_id
            raw_a = answer_gen.run(json.dumps([new_q], ensure_ascii=False))
            new_qa = json.loads(raw_a)
            if new_qa:
                qa_pairs[idx] = new_qa[0]
                print(f"    {bad_id} 재생성 완료")
        except Exception as e:
            print(f"[main] {bad_id} 자동 재생성 실패: {e}")

    return qa_pairs


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
    print(f"  토픽: {topics}")

    print("\n=== [Step 2] 문제 계획 ===")
    planner = PlannerAgent()
    plan = json.loads(planner.run(f"토픽: {topics}\n요구사항: {requirements}"))
    print(f"  계획: {plan}")

    print("\n=== [Step 3] 문제 병렬 생성 ===")
    questions = _generate_questions(topics, plan)
    print(f"  생성된 문제 수: {len(questions)}")

    print("\n=== [Step 4] 모범답안 생성 ===")
    qa_pairs = _generate_answers(questions)

    print("\n=== [Step 5] AI 품질 검토 ===")
    reviewer = QualityReviewerAgent()
    review = json.loads(reviewer.run(json.dumps({"questions": qa_pairs, "plan": plan}, ensure_ascii=False)))
    if review["pass"]:
        print("  품질 검토 통과.")
    else:
        issues = review.get("issues", [])
        print(f"  품질 문제 발견 ({len(issues)}개): {[i['id'] for i in issues]}")
        for issue in issues:
            print(f"    {issue['id']}: {issue.get('reason', '')}")
        print("  자동 재생성 중...")
        qa_pairs = _auto_fix_questions(qa_pairs, issues, topics, plan)

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
