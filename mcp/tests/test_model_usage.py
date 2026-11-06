"""The app's own models, reported to Luna Sentia's model monitor."""

import asyncio
import time
import unittest

from mcp.server.fastmcp import FastMCP

from app.core import tenancy
from app.integrations import model_usage
from app.integrations.model_usage import ModelUsage


class ModelUsageTests(unittest.TestCase):
    def test_calls_time_and_failures_are_counted(self):
        state = {"loaded": False}
        usage = ModelUsage("test-model", "testing", lambda: (state["loaded"], "cuda" if state["loaded"] else "not loaded"))
        with usage.record():
            time.sleep(0.01)
        with self.assertRaises(ValueError):
            with usage.record():
                raise ValueError("boom")
        state["loaded"] = True
        status = usage.status()
        self.assertEqual((status["calls"], status["failures"], status["active"]), (2, 1, 0))
        self.assertGreater(status["busy_seconds"], 0.005)
        self.assertEqual((status["loaded"], status["device"]), (True, "cuda"))
        self.assertIsNotNone(status["last_used"])

    def test_the_report_lists_this_processes_models(self):
        usage = ModelUsage("listed-model", "testing", lambda: (False, "not loaded"))
        report = model_usage.report("vibia")
        self.assertEqual(report["app"], "vibia")
        self.assertIn("listed-model", [row["name"] for row in report["models"]])
        self.assertIn("gpu", report)
        del usage

    def test_only_the_owner_sees_them(self):
        from app.transport.http_routes import VibiaHTTPRoutes

        routes = VibiaHTTPRoutes.__new__(VibiaHTTPRoutes)
        self.assertEqual(asyncio.run(routes.models(None))["app"], "vibia")
        with tenancy.acting_as("someone"):
            with self.assertRaises(PermissionError):
                asyncio.run(routes.models(None))


if __name__ == "__main__":
    unittest.main()
