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

    def test_inventory_comments_do_not_hide_element_or_cdata_errors(self):
        import tempfile
        import xml.etree.ElementTree as ET
        import run
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'screen.xml'
            source.write_text('<screen><!-- command --example --option --><actions><script><![CDATA[let x="<!--literal-->";]]></script></actions></screen>')
            tree = run.source_xml(source)
            self.assertEqual(tree.find('actions/script').text, 'let x="<!--literal-->";')
            source.write_text('<screen><!-- command --example --><broken></screen>')
            with self.assertRaises(ET.ParseError):
                run.source_xml(source)

    def test_extra_fixtures_cannot_inject_sql_or_replace_values_with_expressions(self):
        from operation_fixtures import extra_fixture_groups
        group={'name':'example','table':'example','records':[{'id':'one','value':"a'b"}],'keys':['id']}
        self.assertEqual(list(extra_fixture_groups([group]))[0][2][0]['value'],"a'b")
        for changed in [dict(group,table='example; DROP TABLE example'),dict(group,keys=['missing']),
                        dict(group,records=[{'id':{'sql':'now()'},'value':'unsafe'}]),dict(group,records=[])]:
            with self.assertRaises(ValueError):list(extra_fixture_groups([changed]))
