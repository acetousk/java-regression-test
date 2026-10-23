from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

from deterministic import DeterministicCoordinator


class FakeCdc:
    """Committed transactions waiting to be read, per side; each read consumes them."""
    def __init__(self):
        self.queued = {"java": [], "rust": []}

    def commit(self, side, *changes):
        self.queued[side].append(list(changes))

    def __call__(self, side):
        items, self.queued[side] = self.queued[side], []
        return items


class DeterministicTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.cdc = FakeCdc()
        self.compared = []
        self.coordinator = DeterministicCoordinator(
            "test", Path(self.directory.name), compare=lambda write: self.compared.append(write) or True,
            cdc=self.cdc, timeout=0.5, start_millis=1760000000000)
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.addCleanup(self.pool.shutdown)

    def begin(self, engine, sequence=1, name="example.create#Thing"):
        return self.coordinator.exchange({
            "version": 1, "run_id": "test", "engine": engine, "sequence": sequence,
            "event": "begin", "parent_sequence": None,
            "artifact": {"type": "AT_SERVICE", "sub_type": "sync", "name": name},
            "artifact_stack": [{"type": "AT_SERVICE", "sub_type": "sync", "name": name}]})

    def complete(self, engine, sequence=1, outcome="committed"):
        return {"version": 1, "run_id": "test", "engine": engine, "sequence": sequence,
                "event": "complete", "operation_id": f"{engine}-{sequence:08d}", "outcome": outcome}

    def write(self, sequence=1, java=("INSERT a",), rust=("INSERT a",)):
        for side, changes in (("java", java), ("rust", rust)):
            self.begin(side, sequence)
            self.cdc.commit(side, *changes)
        futures = [self.pool.submit(self.coordinator.exchange, self.complete(side, sequence))
                   for side in ("java", "rust")]
        return [future.result(timeout=2) for future in futures]

    def test_begin_is_answered_without_waiting_for_peer_or_matching_artifacts(self):
        self.assertEqual(self.begin("java", name="one"),
                         {"operation_id": "java-00000001", "time_epoch_ms": 1760000000000})
        self.assertEqual(self.begin("rust", name="two")["time_epoch_ms"], 1760000000000)

    def test_transaction_gate_ignores_internal_identity_but_checks_database(self):
        self.begin('java', name='java metadata and entity work')
        self.begin('rust', name='rust pool validation and entity work')
        for side in ('java', 'rust'):
            self.cdc.commit(side, 'INSERT a')
        replies = [self.pool.submit(self.coordinator.exchange, self.complete(side)) for side in ('java', 'rust')]
        self.assertEqual([reply.result(timeout=2) for reply in replies], [{'ok': True}] * 2)
        self.assertEqual(self.compared, ['write-00000001'])
        report = self.coordinator.report()
        self.assertTrue(report['per_transaction_databases_equal'])
        self.assertFalse(report['operation_checks_enabled'])
        self.assertIsNone(report['operation_order_equal'])

    def test_read_only_and_rolled_back_transactions_do_not_wait(self):
        self.begin("java")
        self.assertEqual(self.coordinator.exchange(self.complete("java")), {"ok": True})
        self.begin("rust")
        self.assertEqual(self.coordinator.exchange(self.complete("rust", outcome="rolled_back")), {"ok": True})
        self.assertEqual(self.compared, [])

    def test_write_waits_for_peer_write_then_compares_and_advances_time(self):
        self.begin("java", name="java-only read")
        self.coordinator.exchange(self.complete("java"))
        self.begin("java", 2)
        self.cdc.commit("java", "INSERT a")
        first = self.pool.submit(self.coordinator.exchange, self.complete("java", 2))
        with self.coordinator.condition:
            self.assertFalse(first.done())
        self.begin("rust")
        self.cdc.commit("rust", "INSERT a")
        self.assertEqual(self.coordinator.exchange(self.complete("rust")), {"ok": True})
        self.assertEqual(first.result(timeout=2), {"ok": True})
        self.assertEqual(self.compared, ["write-00000001"])
        self.assertEqual(self.begin("rust", 2)["time_epoch_ms"], 1760000000001)
        cdc = json.loads((Path(self.directory.name) / "transactions/write-00000001/java-cdc.json").read_text())
        self.assertEqual(cdc["transactions"][0]["changes"], ["INSERT a"])

    def test_rust_only_table_write_has_no_java_peer(self):
        self.coordinator.rust_only = lambda change: change.startswith("table search.")
        self.begin("rust")
        self.cdc.commit("rust", "table search.document_index: INSERT: document_id[text]:'a'")
        self.assertEqual(self.coordinator.exchange(self.complete("rust")), {"ok": True})
        self.assertEqual(self.coordinator.report()["rust_only_writes"], 1)
        self.write(2, java=("table public.enumeration: INSERT: x",),
                   rust=("table public.enumeration: INSERT: x", "table search.document_index: INSERT: y"))
        self.assertEqual(self.compared, ["write-00000001"])

    def test_ddl_only_transaction_is_a_write(self):
        self.write(java=(), rust=())
        self.assertEqual(self.compared, ["write-00000001"])

    def test_database_difference_fails_both_engines(self):
        self.coordinator.compare = lambda write: False
        with self.assertRaisesRegex(ValueError, "Database mismatch after write 1"):
            self.write()
        self.assertFalse(self.coordinator.report()["per_transaction_databases_equal"])

    def test_extra_committed_transaction_on_one_side_fails(self):
        self.begin("java")
        self.cdc.commit("java", "INSERT a")
        self.cdc.commit("java", "INSERT b")
        self.begin("rust")
        self.cdc.commit("rust", "INSERT a")
        futures = [self.pool.submit(self.coordinator.exchange, self.complete(side)) for side in ("java", "rust")]
        for future in futures:
            with self.assertRaisesRegex(ValueError, "java committed 2 transactions, rust committed 1"):
                future.result(timeout=2)
        self.assertEqual(self.compared, [])

    def test_missing_peer_write_times_out(self):
        self.coordinator.timeout = 0.01
        self.begin("java")
        self.cdc.commit("java", "INSERT a")
        with self.assertRaisesRegex(TimeoutError, "rust did not commit write 1"):
            self.coordinator.exchange(self.complete("java"))

    def test_invalid_protocol_is_rejected(self):
        base = {"version": 1, "run_id": "test", "engine": "java", "sequence": 1, "event": "begin"}
        for changes in ({"version": 2}, {"version": True}, {"run_id": "other"}, {"engine": "other"},
                        {"sequence": True}, {"sequence": 0}, {"event": "other"}):
            with self.subTest(changes=changes):
                coordinator = DeterministicCoordinator("test", Path(self.directory.name))
                with self.assertRaises(ValueError):
                    coordinator.exchange({**base, **changes})

    def test_transaction_sequences_cannot_be_reused(self):
        for completed in (False, True):
            coordinator = DeterministicCoordinator('test', Path(self.directory.name))
            request = dict(version=1, run_id='test', engine='java', sequence=1, event='begin')
            coordinator.exchange(request)
            if completed:
                coordinator.exchange(self.complete('java'))
            with self.assertRaisesRegex(ValueError, 'sequence must increase'):
                coordinator.exchange(request)

    def test_matching_commit_batches_cannot_hide_intermediate_divergence(self):
        for side in ('java', 'rust'):
            self.begin(side)
            self.cdc.commit(side, f'INSERT {side}-specific value')
            self.cdc.commit(side, 'DELETE all values')
        futures = [self.pool.submit(self.coordinator.exchange, self.complete(side)) for side in ('java', 'rust')]
        for future in futures:
            with self.assertRaisesRegex(ValueError, 'multiple commits'):
                future.result(timeout=2)
        self.assertEqual(self.compared, [])
        self.assertFalse(self.coordinator.report()['per_transaction_databases_equal'])

    def test_unknown_completion_or_outcome_cannot_pass(self):
        with self.assertRaisesRegex(ValueError, "active transaction"):
            self.coordinator.exchange(self.complete("java"))
        self.coordinator = DeterministicCoordinator("test", Path(self.directory.name))
        self.begin("rust")
        with self.assertRaisesRegex(ValueError, "outcome"):
            self.coordinator.exchange(self.complete("rust", outcome="maybe"))

    def test_default_clock_samples_real_time_once(self):
        with patch("deterministic.time.time_ns", return_value=1800000000123456789) as clock:
            coordinator = DeterministicCoordinator("test", Path(self.directory.name))
            self.assertEqual(coordinator.report()["start_epoch_ms"], 1800000000123)
            clock.assert_called_once_with()

    def test_webhook_roundtrip_and_report(self):
        url = self.coordinator.start()

        def post(payload):
            request = urllib.request.Request(url, json.dumps(payload).encode(),
                                             {"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=2) as response:
                # The JDK client pools any connection whose reply does not say close.
                self.assertEqual(response.headers["Connection"], "close")
                return json.load(response)

        for side in ("java", "rust"):
            post({"version": 1, "run_id": "test", "engine": side, "sequence": 1, "event": "begin",
                  "parent_sequence": None})
            self.cdc.commit(side, "INSERT a")
        replies = [self.pool.submit(post, self.complete(side)) for side in ("java", "rust")]
        self.assertEqual([reply.result(timeout=2) for reply in replies], [{"ok": True}] * 2)
        (Path(self.directory.name) / "java-deterministic.log").write_text(
            json.dumps({"event": "trace", "kind": "jdbc"}) + "\n")
        self.coordinator.close()
        report = json.loads((Path(self.directory.name) / "deterministic-report.json").read_text())
        self.assertTrue(report["per_transaction_databases_equal"])
        self.assertEqual(report["database_comparisons"], 1)
        self.assertEqual(report["operation_trace_counts"], {"java": {"jdbc": 1}, "rust": None})

    def test_unpaired_write_at_close_fails(self):
        self.write()
        self.cdc.commit("rust", "INSERT late")
        self.coordinator.close()
        self.assertIn("Unpaired write transactions", self.coordinator.error)
        self.assertFalse(self.coordinator.report()["per_transaction_databases_equal"])

    def operation(self, side, sequence=1, name='public.example', parent=None, outcome='succeeded'):
        return {'version': 1, 'run_id': 'test', 'engine': side, 'sequence': sequence, 'event': 'operation',
                'kind': 'jdbc', 'action': 'executeUpdate', 'name': name, 'outcome': outcome,
                'transaction_sequence': parent}

    def test_every_read_or_noop_operation_is_paired_and_checked(self):
        self.coordinator.operation_checks = True
        first = self.pool.submit(self.coordinator.exchange, self.operation('java'))
        self.assertFalse(first.done())
        second = self.coordinator.exchange(self.operation('rust'))
        self.assertEqual(first.result(timeout=2), second)
        self.assertEqual(second, {'ok': True, 'state': 'committed-only', 'uncommitted_pending': False})
        self.assertEqual(self.compared, ['operation-00000001'])
        self.assertEqual(self.coordinator.report()['operation_database_comparisons'], 1)

    def test_operation_mismatch_and_outcome_mismatch_fail_both_peers(self):
        for changes in ({'name': 'different'}, {'outcome': 'failed'}):
            self.coordinator = DeterministicCoordinator('test', Path(self.directory.name), cdc=self.cdc,
                                                       compare=lambda _: True, timeout=0.5, operation_checks=True)
            requests = (self.operation('java'), {**self.operation('rust'), **changes})
            futures = [self.pool.submit(self.coordinator.exchange, request) for request in requests]
            for future in futures:
                with self.assertRaisesRegex(ValueError, 'Operation identity mismatch'):
                    future.result(timeout=2)

    def test_operation_database_difference_is_rejected_before_acknowledgement(self):
        self.coordinator.operation_checks = True
        self.coordinator.compare = lambda _: False
        futures = [self.pool.submit(self.coordinator.exchange, self.operation(side)) for side in ('java', 'rust')]
        for future in futures:
            with self.assertRaisesRegex(ValueError, 'Database mismatch after operation 1'):
                future.result(timeout=2)

    def test_uncommitted_operation_is_explicitly_pending_not_a_full_state_proof(self):
        self.coordinator.operation_checks = True
        for side in ('java', 'rust'):
            self.begin(side)
        futures = [self.pool.submit(self.coordinator.exchange, self.operation(side, parent=1))
                   for side in ('java', 'rust')]
        self.assertTrue(all(future.result(timeout=2)['uncommitted_pending'] for future in futures))
        self.assertFalse(self.coordinator.report()['uncommitted_state_verified'])
        for side in ('java', 'rust'):
            self.coordinator.exchange(self.complete(side, outcome='rolled_back'))

    def test_operation_missing_peer_timeout_and_incomplete_stream_fail_closed(self):
        self.coordinator.operation_checks = True
        self.coordinator.timeout = 0.01
        with self.assertRaisesRegex(TimeoutError, 'Peer did not reach operation'):
            self.coordinator.exchange(self.operation('java'))
        self.coordinator.close()
        self.assertFalse(self.coordinator.report()['operation_order_equal'])

    def test_empty_run_is_not_a_proof(self):
        self.coordinator.close()
        self.assertFalse(self.coordinator.report()["per_transaction_databases_equal"])
        self.assertIsNotNone(self.coordinator.error)


if __name__ == "__main__":
    unittest.main()
