import json
import os
from agents.base import BaseAgentWorker
from tools.file_writers import save_exam_docx, save_answer_key_docx

OUTPUT_DIR = "output"


class AssemblerAgent(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Exam Assembler", task_id="Task 7")

    def run(self, input_text: str) -> str:
        data = json.loads(input_text)
        qa_pairs = data["qa_pairs"]
        plan = data.get("plan", {})

        exam_path = os.path.join(OUTPUT_DIR, "exam.docx")
        answer_path = os.path.join(OUTPUT_DIR, "answer_key.docx")

        print(f"[Assembler] plan 전달 확인: {plan}")

        def _save_with_retry(fn, *args, **kwargs):
            label = args[1] if len(args) > 1 else ""
            while True:
                try:
                    fn(*args, **kwargs)
                    break
                except PermissionError:
                    print(f"{label} 이(가) 열려 있습니다. 파일을 닫은 후 엔터를 누르세요.")
                    input()

        _save_with_retry(save_exam_docx, qa_pairs, exam_path, plan=plan)
        _save_with_retry(save_answer_key_docx, qa_pairs, answer_path)

        result = {
            "exam": os.path.abspath(exam_path),
            "answer_key": os.path.abspath(answer_path),
        }
        print(f"[Assembler] 완료 — {result}")
        return json.dumps(result, ensure_ascii=False, indent=2)
