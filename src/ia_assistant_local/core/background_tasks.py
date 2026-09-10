from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor


class TaskManager:
    def __init__(self, workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="oraculo-task")
        self._lock = threading.Lock()
        self._tasks: dict[str, dict] = {}

    def create(self, user_id: int, kind: str, label: str, work: Callable) -> dict:
        task_id = secrets.token_urlsafe(12)
        cancel = threading.Event()
        task = {
            "id": task_id,
            "user_id": user_id,
            "kind": kind,
            "label": label[:160],
            "status": "queued",
            "progress": 0,
            "result": None,
            "error": None,
            "created_at": int(time.time()),
            "cancel": cancel,
        }
        with self._lock:
            self._tasks[task_id] = task
        self._executor.submit(self._run, task, work)
        return self._public(task)

    def _run(self, task: dict, work: Callable) -> None:
        with self._lock:
            if task["cancel"].is_set():
                task["status"] = "cancelled"
                return
            task["status"], task["progress"] = "running", 10

        def progress(value: int) -> None:
            with self._lock:
                if task["cancel"].is_set():
                    raise RuntimeError("Tarefa cancelada.")
                task["progress"] = max(10, min(95, int(value)))

        try:
            result = work(task["cancel"], progress)
            with self._lock:
                if task["cancel"].is_set():
                    task["status"], task["result"] = "cancelled", None
                else:
                    task["status"], task["progress"], task["result"] = "completed", 100, result
        except Exception as exc:  # noqa: BLE001 - worker boundary records task failures
            with self._lock:
                task["status"] = "cancelled" if task["cancel"].is_set() else "failed"
                task["error"] = "Tarefa cancelada." if task["cancel"].is_set() else str(exc)[:500]

    @staticmethod
    def _public(task: dict, include_result: bool = False) -> dict:
        result = {
            key: task[key]
            for key in ("id", "kind", "label", "status", "progress", "error", "created_at")
        }
        if include_result:
            result["result"] = task["result"]
        return result

    def get(self, user_id: int, task_id: str, include_result: bool = True) -> dict:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task["user_id"] != user_id:
                raise PermissionError("Tarefa não encontrada.")
            return self._public(task, include_result)

    def list(self, user_id: int) -> list[dict]:
        with self._lock:
            rows = [
                self._public(task) for task in self._tasks.values() if task["user_id"] == user_id
            ]
        return sorted(rows, key=lambda item: item["created_at"], reverse=True)[:50]

    def cancel(self, user_id: int, task_id: str) -> dict:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task["user_id"] != user_id:
                raise PermissionError("Tarefa não encontrada.")
            if task["status"] in {"queued", "running"}:
                task["cancel"].set()
                task["status"] = "cancelled"
                task["result"] = None
            return self._public(task)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
