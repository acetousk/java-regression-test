"""Change 6: sampling and destructive fixture ownership guards."""
import hashlib
import json
from pathlib import Path
import unittest
from operation_fixtures import setup_operation_fixtures

class SampleGuards(unittest.TestCase):
    def test_frozen_sample_is_reproducible_and_distinct(self):
        sample = json.loads(Path(__file__).with_name('sample25.json').read_text())
        ranked = sorted(sample['eligible'], key=lambda key: hashlib.sha256((sample['seed']+'\0'+key).encode()).hexdigest())
        selected = [row['key'] for row in sample['selected']]
        self.assertEqual(selected, ranked[:25])
        self.assertEqual(len(set(selected)),25)
        self.assertTrue(sample['frozen'])

    def test_fixture_setup_rejects_unowned_or_shared_databases(self):
        for containers, owned in [({'java':'production','rust':'production2'},True),
                                  ({'java':'phase-three-one','rust':'phase-three-one'},True),
                                  ({'java':'phase-three-java','rust':'phase-three-rust'},False)]:
            with self.assertRaises(ValueError):
                setup_operation_fixtures({'java':1,'rust':2},containers,Path('/unused'),{},disposable=owned)

    def test_scheduler_isolation_preserves_other_configuration(self):
        import tempfile
        import xml.etree.ElementTree as ET
        import run
        with tempfile.TemporaryDirectory() as directory:
            conf = Path(directory)/'conf.xml'
            conf.write_text('<moqui-conf><default-property name="scheduled_job_check_time" value="60"/><service-facade job-pool-core="2"/><entity-facade marker="retained"/></moqui-conf>')
            run.isolate_operation_scheduler(conf)
            tree = ET.parse(conf).getroot()
            self.assertEqual(tree.find('default-property').get('value'),'0')
            self.assertEqual(tree.find('service-facade').get('scheduled-job-check-time'),'0')
            self.assertEqual(tree.find('service-facade').get('job-pool-core'),'2')
            self.assertEqual(tree.find('entity-facade').get('marker'),'retained')
