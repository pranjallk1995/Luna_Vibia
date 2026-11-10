"""Tests for gpu_worker.py (the same file in every app with a model of its own)."""

import os
import time
import unittest

from app.integrations.gpu_worker import IdleWorker, WorkerDiedError


class Echo:
    """A stand-in model: built once per process, so its pid shows which process answered."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix

    def say(self, text: str) -> str:
        return f"{self.prefix}{text}"

    def pid(self) -> int:
        return os.getpid()

    def fail(self) -> None:
        raise ValueError("no such page")

    def die(self) -> None:
        os._exit(3)


class IdleWorkerTests(unittest.TestCase):
    def test_answers_in_its_own_process_and_raises_its_errors(self):
        worker = IdleWorker(Echo, ("luna: ",), idle_seconds=30)
        try:
            self.assertEqual(worker.call("say", "hi"), "luna: hi")
            self.assertNotEqual(worker.call("pid"), os.getpid())
            with self.assertRaisesRegex(ValueError, "no such page"):
                worker.call("fail")
            self.assertTrue(worker.alive)
        finally:
            worker.close()
        self.assertFalse(worker.alive)

    def test_exits_when_idle_and_starts_again_on_the_next_call(self):
        worker = IdleWorker(Echo, ("",), idle_seconds=1.5)
        try:
            first = worker.call("pid")
            time.sleep(3)
            self.assertFalse(worker.alive)
            self.assertNotEqual(worker.call("pid"), first)
        finally:
            worker.close()

    def test_a_dead_process_fails_its_call_and_is_replaced(self):
        worker = IdleWorker(Echo, ("",), idle_seconds=30)
        try:
            with self.assertRaises(WorkerDiedError):
                worker.call("die")
            self.assertEqual(worker.call("say", "back"), "back")
        finally:
            worker.close()


if __name__ == "__main__":
    unittest.main()
