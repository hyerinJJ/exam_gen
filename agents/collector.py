from pathlib import Path
from agents.base import BaseAgentWorker
from tools.file_readers import read_file


class CollectorAgent(BaseAgentWorker):
    def __init__(self):
        super().__init__(name="Content Collector", task_id="Task 0")

    def run(self, input_text: str) -> str:
        file_paths = [p.strip() for p in input_text.strip().splitlines() if p.strip()]
        sections = []
        for path in file_paths:
            try:
                content = read_file(path)
                filename = Path(path).name
                sections.append(f"=== {filename} ===\n{content}")
            except Exception as e:
                print(f"[{self.name}] 건너뜀: {path} - {e}")
        return "\n\n".join(sections)
