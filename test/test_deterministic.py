from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
import urllib.request

from deterministic import DeterministicCoordinator


class DeterministicTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.coordinator = DeterministicCoordinator("test", Path(self.directory.name), timeout=0.5)
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.addCleanup(self.pool.shutdown)

    def begin(self, engine, sequence=1, parent=None, name="example.create#Thing"):
        return {"version": 1, "run_id": "test", "engine": engine, "sequence": sequence,
                "event": "begin", "parent_sequence": parent,
                "artifact": {"type": "AT_SERVICE", "sub_type": "sync", "name": name},
                "artifact_stack": [{"type": "AT_SERVICE", "sub_type": "sync", "name": name}]}

    def complete(self, engine, operation_id="op-00000001", sequence=1, outcome="committed"):
        return {"version": 1, "run_id": "test", "engine": engine, "sequence": sequence,
                "event": "complete", "operation_id": operation_id, "outcome": outcome}

    def pair(self, java, rust):
        futures = [self.pool.submit(self.coordinator.exchange, item) for item in (java, rust)]
        return [future.result(timeout=2) for future in futures]

    def test_exact_time_is_returned_only_after_peer_arrives(self):
        first = self.pool.submit(self.coordinator.exchange, self.begin("java"))
        with self.coordinator.condition:
            self.assertFalse(first.done())
        second = self.pool.submit(self.coordinator.exchange, self.begin("rust"))
        self.assertEqual(first.result(timeout=2), second.result(timeout=2))
        self.assertEqual(first.result()["time_epoch_ms"], 1760000000000)
        self.assertFalse(self.coordinator.report()["operation_order_equal"])
        self.pair(self.complete("java"), self.complete("rust"))
        self.assertTrue(self.coordinator.report()["operation_order_equal"])
        self.assertFalse(self.coordinator.report()["per_transaction_databases_equal"])

    def test_compare_runs_before_completion_acknowledgement(self):
        calls = []
        self.coordinator.compare = lambda operation, outcome: calls.append((operation, outcome)) or True
        self.pair(self.begin("java"), self.begin("rust"))
        self.assertEqual(self.pair(self.complete("java"), self.complete("rust")), [{"ok": True}] * 2)
        self.assertEqual(calls, [("op-00000001", "committed")])
        self.assertTrue(self.coordinator.report()["per_transaction_databases_equal"])

    def test_database_difference_fails_both_engines(self):
        self.coordinator.compare = lambda *args: False
        self.pair(self.begin("java"), self.begin("rust"))
        futures = [self.pool.submit(self.coordinator.exchange, self.complete(side)) for side in ("java", "rust")]
        for future in futures:
            with self.assertRaisesRegex(ValueError, "Database mismatch"):
                future.result(timeout=2)
        self.assertFalse(self.coordinator.report()["per_transaction_databases_equal"])

    def test_operation_order_mismatch_fails_without_assigning_time(self):
        futures = [self.pool.submit(self.coordinator.exchange, self.begin(side, name=name))
                   for side, name in (("java", "one"), ("rust", "two"))]
        for future in futures:
            with self.assertRaisesRegex(ValueError, "metadata mismatch"):
                future.result(timeout=2)
        self.assertEqual(self.coordinator.operations, 0)

    def test_parent_transaction_restored_after_nested_completion(self):
        self.pair(self.begin("java"), self.begin("rust"))
        response = self.pair(self.begin("java", 2, 1), self.begin("rust", 2, 1))[0]
        self.assertEqual(response["time_epoch_ms"], 1760000000001)
        self.pair(self.complete("java", response["operation_id"], 2, "rolled_back"),
                  self.complete("rust", response["operation_id"], 2, "rolled_back"))
        self.assertEqual(self.coordinator.stacks["java"], [(1, "op-00000001")])
        self.pair(self.complete("java"), self.complete("rust"))
        self.assertTrue(self.coordinator.report()["operation_order_equal"])

    def test_missing_peer_times_out_in_real_time(self):
        self.coordinator.timeout = 0.01
        with self.assertRaisesRegex(TimeoutError, "Peer did not reach"):
            self.coordinator.exchange(self.begin("java"))
        self.assertFalse(self.coordinator.report()["operation_order_equal"])

    def test_invalid_protocol_parent_sequence_and_artifact_are_rejected(self):
        for changes in ({"version": 2}, {"version": True}, {"run_id": "other"}, {"engine": "other"},
                        {"parameters": {"password": "must-not-be-recorded"}},
                        {"sequence": True}, {"sequence": 2}, {"parent_sequence": 4},
                        {"artifact": {}}, {"artifact_stack": ["bad"]}):
            with self.subTest(changes=changes):
                coordinator = DeterministicCoordinator("test", Path(self.directory.name))
                request = {**self.begin("java"), **changes}
                with self.assertRaises(ValueError):
                    coordinator.exchange(request)

    def test_wrong_outcome_or_unknown_completion_cannot_pass(self):
        with self.assertRaisesRegex(ValueError, "active transaction"):
            self.coordinator.exchange(self.complete("java"))

    def test_actual_webhook_roundtrip_and_report(self):
        self.coordinator.compare = lambda *args: True
        url = self.coordinator.start()
        self.addCleanup(self.coordinator.close)

        def post(payload):
            request = urllib.request.Request(url, json.dumps(payload).encode(),
                                             {"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=2) as response:
                return json.load(response)

        for event in (self.begin, self.complete):
            replies = [self.pool.submit(post, event(side)) for side in ("java", "rust")]
            self.assertEqual(replies[0].result(timeout=2), replies[1].result(timeout=2))
        self.coordinator.close()
        report = json.loads((Path(self.directory.name) / "deterministic-report.json").read_text())
        self.assertTrue(report["per_transaction_databases_equal"])
        self.assertEqual(report["database_comparisons"], 1)

    def test_engine_log_must_match_acknowledged_events(self):
        self.coordinator.require_logs = True
        self.coordinator.compare = lambda *args: True
        self.pair(self.begin("java"), self.begin("rust"))
        self.pair(self.complete("java"), self.complete("rust"))
        self.assertFalse(self.coordinator.report()["per_transaction_databases_equal"])
        for side in ("java", "rust"):
            events = []
            for barrier in self.coordinator.events:
                event = {**barrier["requests"][side]}
                if event["event"] == "begin":
                    event.update(barrier["response"])
                events.append(json.dumps(event))
            (Path(self.directory.name) / f"{side}-deterministic.log").write_text("\n".join(events) + "\n")
        self.coordinator.verify_logs()
        self.assertTrue(self.coordinator.report()["per_transaction_databases_equal"])
        (Path(self.directory.name) / "rust-deterministic.log").write_text("{}\n")
        self.coordinator.verify_logs()
        self.assertFalse(self.coordinator.report()["per_transaction_databases_equal"])

    def test_operation_traces_are_validated_separately_from_barrier_acknowledgements(self):
        self.pair(self.begin("java"), self.begin("rust"))
        self.pair(self.complete("java"), self.complete("rust"))
        for side in ("java", "rust"):
            records = []
            for barrier in self.coordinator.events:
                event = {**barrier["requests"][side]}
                if event["event"] == "begin":
                    event.update(barrier["response"])
                records.append(event)
            records.insert(1, {"version": 1, "run_id": "test", "engine": side, "event": "trace",
                               "trace_sequence": 1, "kind": "jdbc", "action": "executeUpdate",
                               "name": "CREATE TABLE example (id integer)", "outcome": "succeeded",
                               "parent_sequence": 1, "time_epoch_ms": 1760000000000})
            (Path(self.directory.name) / f"{side}-deterministic.log").write_text(
                "".join(json.dumps(record) + "\n" for record in records))
        self.coordinator.verify_logs()
        self.assertTrue(self.coordinator.logs_verified)
        self.assertEqual(self.coordinator.report()["operation_trace_counts"],
                         {"java": {"jdbc": 1}, "rust": {"jdbc": 1}})
        path = Path(self.directory.name) / "rust-deterministic.log"
        path.write_text(path.read_text().replace('"trace_sequence": 1', '"trace_sequence": 2'))
        self.coordinator.verify_logs()
        self.assertFalse(self.coordinator.logs_verified)
        self.assertIn("Invalid operation trace", self.coordinator.error)

    def test_missing_engine_log_is_not_a_proof(self):
        self.coordinator.require_logs = True
        self.coordinator.compare = lambda *args: True
        self.pair(self.begin("java"), self.begin("rust"))
        self.pair(self.complete("java"), self.complete("rust"))
        self.coordinator.close()
        self.assertFalse(self.coordinator.report()["per_transaction_databases_equal"])
        self.assertIn("log verification failed", self.coordinator.error)

    def test_empty_stream_is_not_a_proof(self):
        self.coordinator.close()
        self.assertFalse(self.coordinator.report()["operation_order_equal"])
        self.assertIsNotNone(self.coordinator.error)


if __name__ == "__main__":
    unittest.main()
