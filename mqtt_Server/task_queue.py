from collections import deque

class TaskQueue:
    def __init__(self):
        self.queue = deque()
    def add_task(self, task):
        self.queue.append(task)
    def get_next(self):
        self.queue.popleft() if self.queue else None
    def has_task(self):
        return len(self.queue) > 0