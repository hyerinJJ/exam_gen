class BaseAgentWorker:
    def __init__(self, name: str, task_id: str):
        self.name = name
        self.task_id = task_id

    def run(self, input_text: str) -> str:
        raise NotImplementedError(f"{self.name}: run() 미구현")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} task_id={self.task_id!r}>"
