"""Phase 3, Change 13: snapshot identity and live sequence alignment guards."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import operation_database as db

class SnapshotIdentityTests(unittest.TestCase):
    def test_invalid_snapshot_cannot_enter_sql_or_launch_a_process(self):
        for value in ["x'; SELECT 1; --", '', '000-00-1 extra']:
            with patch.object(db.c.subprocess,'check_output') as process:
                with self.assertRaises(ValueError):
                    db.c.capture_snapshot('owned',Path('/unused'),snapshot_id=value)
                process.assert_not_called()

    def test_dump_and_rows_import_same_snapshot_before_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(db.c.subprocess,'check_output',side_effect=['schema','']) as process:
                db.c.capture_snapshot('owned',Path(directory)/'capture.json',snapshot_id='00000003-0000001B-1')
            self.assertIn('--snapshot=00000003-0000001B-1',process.call_args_list[0].args[0])
            sql=process.call_args_list[1].kwargs['input']
            self.assertLess(sql.index("SET TRANSACTION SNAPSHOT '00000003-0000001B-1'"),sql.index('SELECT'))
            self.assertEqual(sql.count('SET TRANSACTION SNAPSHOT'),1)

    def test_changed_or_missing_sequence_state_rejects_approved_completeness(self):
        with tempfile.TemporaryDirectory() as directory:
            raw,typed=Path(directory)/'dump.sql',Path(directory)/'rows.json'
            typed.write_text(json.dumps({'records':[json.dumps({'sequence':'public.seq','state':{'last_value':4,'is_called':True}})]}))
            raw.write_text("SELECT pg_catalog.setval('public.seq', 4, true);\n")
            self.assertTrue(db.sequence_alignment(raw,typed))
            for content in ["SELECT pg_catalog.setval('public.seq', 5, true);\n", "SELECT pg_catalog.setval('public.seq', 4, false);\n",'']:
                raw.write_text(content)
                self.assertFalse(db.sequence_alignment(raw,typed))

    def test_suppressed_stdout_keeps_the_full_failed_comparison_report(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for side,value in [('java',1),('rust',2)]:
                (root/(side+'.json')).write_text(json.dumps({'schema':'schema','records':[json.dumps({'value':value})]}))
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                passed=db.c.snapshot_compare(root/'java.json',root/'rust.json',root,emit_report=False)
            self.assertFalse(passed)
            self.assertEqual(output.getvalue(),'')
            report=json.loads((root/'comparison.json').read_text())
            self.assertFalse(report['comparison_passed'])
            self.assertEqual(len(report['record_byte_differences']),2)
