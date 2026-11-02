"""An interrupted offline probe must never leave a successful receipt."""
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import check_c0_prior_integration as runner


class ProbeReceiptTests(unittest.TestCase):
    def test_legacy_unit_fixtures_do_not_disable_grouped_api_probes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            repo, output, chromium = root / "repo", root / "output", root / "chromium"
            adapter = repo / runner.HARNESS / "retention_adapter.py"
            adapter.parent.mkdir(parents=True)
            adapter.write_text("# synthetic runner test\n")
            chromium.touch()
            with patch.object(runner.sys, "platform", "linux"), \
                    patch.object(runner.sys, "argv", ["check", "--output", str(output)]), \
                    patch.object(runner.shutil, "which", return_value="node"), \
                    patch.object(runner.subprocess, "check_output", side_effect=[str(repo), json.dumps({"chromium": str(chromium)})]), \
                    patch.object(runner, "source_files", return_value={}), \
                    patch.object(runner, "run_logged") as helper, \
                    patch.object(runner, "run_probe") as probes:
                runner.main()
            self.assertNotIn("PRIOR_REQUIRE_GROUPING", helper.call_args.args[4])
            self.assertEqual(probes.call_count, 2)
            for call in probes.call_args_list:
                self.assertEqual(call.args[4]["PRIOR_REQUIRE_GROUPING"], "1")
            self.assertEqual(json.loads((output / "summary.json").read_text())["state"], "PASS")

    def test_interrupt_preserves_failure_and_cleans_only_owned_server(self):
        for boundary in ("wait_ready", "run_logged"):
            for interruption in (KeyboardInterrupt, SystemExit):
                with self.subTest(boundary=boundary, interruption=interruption.__name__):
                    with tempfile.TemporaryDirectory() as temporary:
                        root = Path(temporary)
                        server = Mock()
                        server.poll.return_value = None
                        server.wait.return_value = -signal.SIGTERM
                        with patch.object(runner, "verify_source") as verify, \
                                patch.object(runner, "port_preflight"), \
                                patch.object(runner, "wait_ready"), \
                                patch.object(runner, "run_logged"), \
                                patch.object(runner.subprocess, "Popen", return_value=server), \
                                patch.object(runner, boundary, side_effect=interruption):
                            server.pid = 123
                            with self.assertRaises(interruption):
                                runner.run_probe(root, root, "component", "probe.mjs", {},
                                                 {"files": {}, "snapshot_id": "synthetic"})
                        receipt = json.loads((root / "component/receipt.json").read_text())
                        self.assertEqual(receipt["state"], "FAIL")
                        self.assertIn("Probe interrupted before completion", receipt["errors"])
                        self.assertTrue(receipt["source_unchanged"])
                        self.assertEqual(verify.call_count, 2)
                        server.terminate.assert_called_once_with()
                        server.wait.assert_called_once_with(timeout=15)
                        server.kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
