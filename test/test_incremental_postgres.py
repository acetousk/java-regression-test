"""Opt-in real pinned PostgreSQL integration: MOQUI_INCREMENTAL_POSTGRES_TEST=1.

No engines or mocked database changes: two fresh, independent PostgreSQL instances.
"""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import unittest

from incremental import DatabaseState
from deterministic import DeterministicCoordinator
from test_java_regression import controller


@unittest.skipUnless(os.environ.get('MOQUI_INCREMENTAL_POSTGRES_TEST') == '1', 'opt-in PostgreSQL integration')
class PostgresIncrementalTests(unittest.TestCase):
    def test_real_commit_rollback_ddl_sequence_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            containers = {}
            states = {}
            try:
                for side in ('java', 'rust'):
                    container = f'moqui-incremental-{os.getpid()}-{secrets.token_hex(3)}-{side}'
                    containers[side] = container
                    subprocess.run(['docker', 'run', '--detach', '--rm', '--name', container,
                                    '--env', 'POSTGRES_USER=moqui', '--env', 'POSTGRES_DB=moqui',
                                    '--env', 'POSTGRES_HOST_AUTH_METHOD=trust',
                                    controller.POSTGRES_IMAGE, '-c', 'wal_level=logical', '-c', 'autovacuum=off'],
                                   check=True, stdout=subprocess.DEVNULL, timeout=60)
                    # Resume from PostgreSQL's ready log event, not readiness polling/sleeps.
                    logs = subprocess.Popen(['timeout', '60', 'docker', 'logs', '--follow', container],
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    try:
                        initialized = False
                        for line in logs.stdout:
                            initialized |= 'PostgreSQL init process complete' in line
                            if initialized and 'database system is ready to accept connections' in line:
                                break
                        else:
                            self.fail('PostgreSQL did not emit its final ready event')
                    finally:
                        logs.terminate()
                        logs.communicate(timeout=10)
                    controller.create_cdc_slot(container)
                    path = root / f'{side}-baseline.json'
                    controller.capture_snapshot(container, path)
                    states[side] = DatabaseState(json.loads(path.read_text()))

                def sql(side, statement):
                    return subprocess.check_output(['docker', 'exec', containers[side], 'psql', '-X', '-qAt',
                                                    '-v', 'ON_ERROR_STOP=1', '-U', 'moqui', '-d', 'moqui',
                                                    '-c', statement], text=True, timeout=60)

                def consume(side):
                    transactions, cursor = controller.read_cdc(containers[side], with_cursor=True)
                    states[side].apply(transactions)
                    controller.refresh_incremental_catalog(containers[side], states[side], root / f'{side}-catalog.json')
                    return transactions, cursor

                def compare(expected=True):
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        equal = controller.diff_compare(states['java'], states['rust'], root)
                    self.assertEqual(equal, expected, output.getvalue())

                compare()
                for side in containers:
                    sql(side, 'CREATE TABLE example (id integer PRIMARY KEY, amount numeric, value text); '
                              'CREATE SEQUENCE example_seq;')
                    consume(side)
                compare()
                for side in containers:
                    sql(side, "INSERT INTO example VALUES (1,123456789012345678901234567890.123456789,'a '' quote');")
                    changes, cursor = consume(side)
                    self.assertTrue(changes)
                    self.assertRegex(cursor['after'], r'^[0-9A-F]+/[0-9A-F]+$')
                compare()
                for side in containers:
                    sql(side, "BEGIN; UPDATE example SET value='rolled back'; ROLLBACK;")
                    self.assertEqual(controller.read_cdc(containers[side]), [])
                    sql(side, "UPDATE example SET id=2, value=repeat('toasted',10000);")
                    consume(side)
                    # Reuse unchanged external TOAST data: old/new images must stay complete.
                    sql(side, 'UPDATE example SET amount=1.00;')
                    consume(side)
                compare()
                for side in containers:
                    sql(side, "ALTER TABLE example ADD COLUMN added text DEFAULT 'defaulted';")
                    consume(side)
                compare()
                for side in containers:
                    sql(side, 'CREATE INDEX example_value ON example(value);')
                    consume(side)
                compare()
                for side in containers:
                    sql(side, 'ALTER TABLE example RENAME TO renamed;')
                    consume(side)
                    sql(side, 'ALTER TABLE renamed RENAME TO example;')
                    consume(side)
                    sql(side, 'CREATE TABLE copied AS SELECT * FROM example;')
                    consume(side)
                    sql(side, 'DROP TABLE copied; CREATE TABLE copied (id int); INSERT INTO copied VALUES(2);')
                    consume(side)
                    sql(side, 'DELETE FROM copied WHERE id=2; DROP TABLE copied;')
                    consume(side)
                compare()
                # Nontransactional native sequence state is checked even with no row CDC.
                sql('java', "SELECT nextval('example_seq');")
                consume('java')
                consume('rust')
                compare(False)
                sql('rust', "SELECT nextval('example_seq');")
                consume('rust')
                compare()
                sql('rust', "UPDATE example SET amount=999;")
                consume('rust')
                compare(False)
                sql('java', "UPDATE example SET amount=999;")
                consume('java')
                compare()
                for side in containers:
                    sql(side, 'TRUNCATE example;')
                    consume(side)
                compare()
                for side in containers:
                    sql(side, 'DROP TABLE example; DROP SEQUENCE example_seq;')
                    consume(side)
                compare()
                for side in containers:
                    sql(side, 'CREATE TABLE shared_probe (id int);')
                    consume(side)
                compare()
                # Approved-table-only setup (including an index and no-op drop) has
                # no Java write peer; PostgreSQL, not SQL text, identifies its objects.
                sql('rust', 'BEGIN; DROP TABLE IF EXISTS public.auth_flow; '
                            'CREATE TABLE public.auth_flow (id integer PRIMARY KEY); '
                            'CREATE INDEX auth_flow_id_extra ON public.auth_flow(id); '
                            'INSERT INTO public.auth_flow VALUES (1); COMMIT;')
                setup, _ = consume('rust')
                self.assertEqual(len(setup), 1)
                approvals = controller.ApprovalEngine(controller.APPROVED_STARTUP_DIFFERENCES)
                self.assertTrue(approvals.exempt_transaction('rust', setup[0]), setup)
                compare()
                sql('rust', 'BEGIN; INSERT INTO public.auth_flow VALUES (2); INSERT INTO shared_probe VALUES (1); COMMIT;')
                mixed, _ = consume('rust')
                self.assertFalse(approvals.exempt_transaction('rust', mixed[0]))
                sql('rust', 'DELETE FROM shared_probe;')
                consume('rust')
                compare()
                # Actual synchronous operation barriers over independently committed
                # PostgreSQL changes, followed by the transaction and final-drain gates.
                def replay(side):
                    transactions, _ = consume(side)
                    return transactions

                def gate(_):
                    for side in containers:
                        controller.refresh_incremental_catalog(containers[side], states[side], root / f'{side}-catalog.json')
                    return controller.diff_compare(states['java'], states['rust'], root)

                coordinator = DeterministicCoordinator('probe', root, cdc=replay, compare=gate,
                                                       timeout=5, operation_checks=True)
                def request(side, event, sequence=1, **fields):
                    return dict(version=1, run_id='probe', engine=side, event=event, sequence=sequence, **fields)
                for side in containers:
                    coordinator.exchange(request(side, 'begin'))
                    sql(side, 'CREATE TABLE operation_probe (id integer); INSERT INTO operation_probe VALUES(1);')
                with ThreadPoolExecutor(max_workers=2) as pool:
                    replies = [pool.submit(coordinator.exchange, request(side, 'operation', kind='AT_ENTITY',
                               action='create', name='operation_probe', outcome='exit', transaction_sequence=1))
                               for side in containers]
                    self.assertTrue(all(reply.result(timeout=10)['ok'] for reply in replies))
                    replies = [pool.submit(coordinator.exchange, request(side, 'complete',
                               operation_id=f'{side}-00000001', outcome='committed')) for side in containers]
                    self.assertEqual([reply.result(timeout=10) for reply in replies], [{'ok': True}] * 2)
                coordinator.close()
                self.assertTrue(coordinator.report()['operation_order_equal'])
                self.assertTrue(coordinator.report()['per_transaction_databases_equal'])
                self.assertTrue(coordinator.report()['final_incremental_equal'])
                # Verify a bypass of capture fails instead of manufacturing equality.
                sql('java', 'CREATE TABLE bypass (id int);')
                consume('java')
                sql('java', 'ALTER TABLE bypass DISABLE TRIGGER moqui_regression_row; INSERT INTO bypass VALUES(1);')
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    consume('java')
                self.assertFalse(states['java'].healthy)
                sql('rust', 'DROP EVENT TRIGGER moqui_regression_ddl;')
                with self.assertRaises(subprocess.CalledProcessError):
                    consume('rust')
                self.assertFalse(states['rust'].healthy)
            finally:
                for container in containers.values():
                    subprocess.run(['docker', 'rm', '--force', '--volumes', container],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)


if __name__ == '__main__':
    unittest.main()
