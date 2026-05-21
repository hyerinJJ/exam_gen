import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from agents.collector import CollectorAgent
from agents.topic_extractor import TopicExtractorAgent
from agents.planner import PlannerAgent
from agents.generators import ShortAnswerGenerator, EssayGenerator, ApplicationGenerator
from agents.answer_generator import AnswerGeneratorAgent
from agents.refiner import RefinerAgent
from agents.assembler import AssemblerAgent
from tools.file_writers import save_exam_docx


def _generate_questions(topics: list, plan: dict) -> list:
    """ShortAnswer / Essay / Application 병렬 생성 후 합산."""
    difficulty = plan.get("난이도", "mixed")
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
                json.dumps({"topics": topics, "count": count, "difficulty": difficulty}, ensure_ascii=False),
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

    # 전체 ID 재번호 부여 (Q1, Q2, ...)
    for i, q in enumerate(results, start=1):
        q["id"] = f"Q{i}"
    return results



def run_pipeline(file_paths: list[str], requirements: str) -> dict:
    print("\n=== [Step 0] 파일 수집 ===")
    collector = CollectorAgent()
    raw_text = collector.run("\n".join(file_paths))

    print("\n=== [Step 1] 토픽 추출 ===")
    extractor = TopicExtractorAgent()
    topic_data = json.loads(extractor.run(raw_text))
    topics = topic_data.get("topics", [])
    print(f"  토픽: {topics}")

    planner = PlannerAgent()
    print("\n=== [Step 2] 문제 계획 ===")
    plan = json.loads(planner.run(f"토픽: {topics}\n요구사항: {requirements}"))
    extra_reqs = plan.get("기타요구사항", [])
    print(f"  계획: {plan}")

    print("\n=== [Step 3] 문제 병렬 생성 ===")
    questions = _generate_questions(topics, plan)
    print(f"  생성된 문제 수: {len(questions)}")

    print("\n=== [Step 4] 모범답안 생성 ===")
    answer_gen = AnswerGeneratorAgent()
    qa_pairs = json.loads(answer_gen.run(json.dumps(questions, ensure_ascii=False)))

    print("\n=== [Step 5] 교수자 검토 ===")
    refiner = RefinerAgent()
    while True:
        while True:
            try:
                save_exam_docx(qa_pairs, "output/exam.docx", extra_reqs=extra_reqs)
                break
            except PermissionError:
                print("output/exam.docx 가 열려 있습니다. 파일을 닫은 후 엔터를 누르세요.")
                input()
        print("\noutput/exam.docx 확인 후 엔터를 누르세요.")
        input()

        print("피드백을 입력하세요 (형식: 'Q1: 피드백내용', 빈 줄로 제출):")
        feedback_lines = []
        while True:
            line = input()
            if not line.strip():
                break
            feedback_lines.append(line.strip())

        if not feedback_lines:
            print("[main] 검토 완료 → 최종 조립")
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
        print(f"[main] {len(feedback_lines)}개 문제 재작성 완료, 다시 확인하세요.")

    print("\n=== [Step 6] 문서 조립 ===")
    assembler = AssemblerAgent()
    output = json.loads(assembler.run(json.dumps({"qa_pairs": qa_pairs, "extra_reqs": extra_reqs}, ensure_ascii=False)))

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
