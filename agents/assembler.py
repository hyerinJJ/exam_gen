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
        extra_reqs = data.get("extra_reqs", [])

        exam_path = os.path.join(OUTPUT_DIR, "exam.docx")
        answer_path = os.path.join(OUTPUT_DIR, "answer_key.docx")

        save_exam_docx(qa_pairs, exam_path, extra_reqs=extra_reqs)
        save_answer_key_docx(qa_pairs, answer_path)

        result = {
            "exam": os.path.abspath(exam_path),
            "answer_key": os.path.abspath(answer_path),
        }
        print(f"[Assembler] 완료 — {result}")
        return json.dumps(result, ensure_ascii=False, indent=2)
