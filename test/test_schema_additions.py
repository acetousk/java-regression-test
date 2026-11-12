"""Phase2 Change17: catalog proof never grants a broad schema exception."""
from copy import deepcopy
import json
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from test_java_regression import controller


class SchemaAdditionTests(unittest.TestCase):
    def fixture(self, kind='index', shared=False):
        column = dict(name='extra_key', type='character varying(40)', not_null=False, default=None)
        base = dict(name='id', type='character varying(40)', not_null=False, default=None)
        table = 'public.sample'
        columns = ['id'] if shared else ['extra_key']
        if kind == 'index':
            obj = dict(kind=kind, name='sample_extra', columns=columns, method='btree', unique=False,
                       primary=False, exclusion=False, valid=True, ready=True, live=True, expressions=None,
                       predicate=None, constraint_backed=False, plain=True, key_count=1, attribute_count=1,
                       key_metadata=[dict(opclass='pg_catalog.text_ops',collation='pg_catalog.default',option=0)],
                       options=None, owner='tester', partition=False, table_inherits=False,
                       definition=f"CREATE INDEX sample_extra ON public.sample USING btree ({columns[0]})")
            ddl = obj['definition'] + ';'
        else:
            obj = dict(kind=kind, name='sample_extra', columns=columns, target='public.parent',
                       target_column_types=['character varying(40)'], target_columns=['id'], validated=True, deferrable=False, deferred=False,
                       match='s', update='a', delete='a', local=True, inherited=0, parent_constraint=False,
                       target_key_valid=True, target_key_unique=True, target_key_plain=True,
                       target_key_definition='CREATE UNIQUE INDEX parent_pk ON public.parent USING btree (id)',
                       target_kind='r', target_partition=False, table_inherits=False, enforced=True,
                       trigger_states=['O']*4,
                       definition=f"FOREIGN KEY ({columns[0]}) REFERENCES public.parent(id)")
            ddl = f"ALTER TABLE ONLY public.sample\n    ADD CONSTRAINT sample_extra {obj['definition']};"
        snapshots = []
        for rust in (False, True):
            declarations = '    id character varying(40)' + (',\n    extra_key character varying(40)' if rust else '')
            snapshots.append(dict(schema=f'CREATE TABLE {table} (\n{declarations}\n);\n' + (ddl+'\n' if rust else ''),
                records=[dict(relation=table, kind='r', columns=[deepcopy(base)]+([deepcopy(column)] if rust else []),
                              schema_objects=[deepcopy(obj)] if rust else []),
                         dict(table=table,row=dict(id='one', **({'extra_key':None} if rust else {})))]))
        rule = dict(table=table, name='sample_extra', catalog=deepcopy(obj), ddl=ddl)
        column_rule = dict(table=table, name='extra_key', type=column['type'])
        return snapshots, rule, column_rule

    def apply(self, raw, rule, column):
        snapshots=deepcopy(raw)
        applied=controller.apply_rust_only_columns(snapshots,[column])
        result=controller.apply_schema_additions(snapshots,raw,applied,[rule])
        return snapshots,result

    def test_exact_index_and_fk(self):
        for kind in ('index','foreign_key'):
            with self.subTest(kind=kind):
                raw,rule,column=self.fixture(kind)
                before=deepcopy(raw)
                snapshots,result=self.apply(raw,rule,column)
                self.assertEqual(len(result),1)
                self.assertEqual(snapshots[0]['records'],snapshots[1]['records'])
                self.assertEqual(snapshots[0]['schema'],snapshots[1]['schema'])
                self.assertEqual(before,raw)

    def test_null_proof_and_catalog_fail_closed(self):
        for kind in ('index','foreign_key'):
            for change in ('nonnull','missing_field','missing_catalog','missing_java_catalog','missing_column',
                           'type','duplicate','shared','definition','extra_sql','duplicate_sql','catalog_mismatch'):
                with self.subTest(kind=kind,change=change):
                    raw,rule,column=self.fixture(kind)
                    obj=raw[1]['records'][0]['schema_objects'][0]
                    if change=='nonnull':raw[1]['records'][1]['row']['extra_key']='x'
                    elif change=='missing_field':del raw[1]['records'][1]['row']['extra_key']
                    elif change=='missing_catalog':del raw[1]['records'][0]['schema_objects']
                    elif change=='missing_java_catalog':del raw[0]['records'][0]['schema_objects']
                    elif change=='missing_column':raw[1]['records'][0]['columns'].pop()
                    elif change=='type':raw[1]['records'][0]['columns'][-1]['type']='text'
                    elif change=='duplicate':raw[1]['records'][0]['schema_objects'].append(deepcopy(obj))
                    elif change=='shared':raw[0]['records'][0]['schema_objects'].append(deepcopy(obj))
                    elif change=='definition':obj['definition']+=' changed'
                    elif change=='extra_sql':raw[1]['schema']=raw[1]['schema'].replace(rule['ddl'],rule['ddl']+' SELECT 1;')
                    elif change=='duplicate_sql':raw[1]['schema']+=rule['ddl']+'\n'
                    elif change=='catalog_mismatch':obj['name']='different'
                    _,result=self.apply(raw,rule,column)
                    self.assertEqual(result,[])

    def test_unsafe_catalog_cannot_be_approved_even_by_matching_rule(self):
        for kind,changes in [('index',dict(unique=True,primary=True,exclusion=True,valid=False,ready=False,
                live=False,expressions='lower(extra_key)',predicate='true',constraint_backed=True,plain=False,
                attribute_count=2,key_count=2,partition=True,table_inherits=True,options=['fillfactor=50'])),
                ('foreign_key',dict(validated=False,deferrable=True,deferred=True,match='f',update='c',delete='c',
                local=False,inherited=1,parent_constraint=True,target_key_valid=False,target_key_unique=False,
                target_key_plain=False,target_kind='p',target_partition=True,table_inherits=True,enforced=False,
                trigger_states=['D']*4))]:
            for field,value in changes.items():
                with self.subTest(kind=kind,field=field):
                    raw,rule,column=self.fixture(kind)
                    raw[1]['records'][0]['schema_objects'][0][field]=value
                    rule['catalog'][field]=value
                    self.assertEqual(self.apply(raw,rule,column)[1],[])
            raw,rule,column=self.fixture(kind)
            del raw[1]['records'][0]['schema_objects'][0]['validated' if kind=='foreign_key' else 'expressions']
            rule['catalog']=deepcopy(raw[1]['records'][0]['schema_objects'][0])
            self.assertEqual(self.apply(raw,rule,column)[1],[])

    def test_shared_only_needs_explicit_rule_and_bounded_identical_type(self):
        for kind in ('index','foreign_key'):
            raw,rule,column=self.fixture(kind,shared=True)
            self.assertEqual(self.apply(raw,rule,column)[1],[])
            rule['shared_only']=True
            self.assertEqual(len(self.apply(raw,rule,column)[1]),1 if kind=='index' else 0)
            for side in raw:side['records'][0]['columns'][0]['type']='text'
            self.assertEqual(self.apply(raw,rule,column)[1],[])

    def test_header_removal_preserves_neighbor_sql(self):
        raw,rule,column=self.fixture()
        header='--\n-- Name: sample_extra; Type: INDEX; Schema: public; Owner: tester\n--\n\n'
        raw[1]['schema']=raw[1]['schema'].replace(rule['ddl'],header+rule['ddl'])+'SELECT 7;\n'
        snapshots,result=self.apply(raw,rule,column)
        self.assertEqual(len(result),1)
        self.assertNotIn(header,snapshots[1]['schema'])
        self.assertIn('SELECT 7;',snapshots[1]['schema'])

    def test_full_pipeline_preserves_raw(self):
        raw,rule,column=self.fixture()
        for snapshot in raw:snapshot['records']=[json.dumps(r) for r in snapshot['records']]
        before=deepcopy(raw)
        snapshots,applied=controller.apply_approved_differences(*raw,dict(theme_resources=[],full_text_indexes=[],
            rust_only_columns=[column],schema_additions=[rule]))
        self.assertEqual(before,raw)
        self.assertEqual(len(applied),2)
        self.assertEqual(snapshots[0]['records'],snapshots[1]['records'])

    def test_existing_full_text_rule_projects_only_exact_catalog(self):
        from test_startup_exceptions import ApprovedDifferencesTests
        rows_left,rows_right,ddl_left,ddl_right=ApprovedDifferencesTests().fts()
        raw=[dict(schema=ddl_left,records=rows_left),dict(schema=ddl_right,records=rows_right)]
        rule=dict(table='public.test_fts',field='body',java_index='fts_test_fts_body',rust_index='test_fts_body_fts')
        for side,snapshot in zip(('java','rust'),raw):
            obj=self.fixture()[1]['catalog']
            target='body_tsv' if side=='java' else "to_tsvector('english'::regconfig, body)"
            obj.update(name=rule[side+'_index'],method='gin',owner='moqui',
                       definition=f"CREATE INDEX {rule[side+'_index']} ON public.test_fts USING gin ({target})",
                       columns=['body_tsv'] if side=='java' else [None],plain=side=='java',
                       expressions=None if side=='java' else target,
                       key_metadata=[dict(opclass='pg_catalog.tsvector_ops',collation=None,option=0)])
            snapshot['records'][0]['schema_objects']=[obj]
        for change in ('none','unique','valid','predicate','expressions','opclass','missing','duplicate','definition'):
            with self.subTest(change=change):
                candidate=deepcopy(raw)
                objects=candidate[1]['records'][0]['schema_objects']
                if change=='unique':objects[0]['unique']=True
                elif change=='valid':objects[0]['valid']=False
                elif change=='predicate':objects[0]['predicate']='body IS NOT NULL'
                elif change=='expressions':objects[0]['expressions']='different'
                elif change=='opclass':objects[0]['key_metadata'][0]['opclass']='public.custom_ops'
                elif change=='missing':objects.clear()
                elif change=='duplicate':objects.append(deepcopy(objects[0]))
                elif change=='definition':objects[0]['definition']+=' extra'
                for snapshot in candidate:snapshot['records']=[json.dumps(r) for r in snapshot['records']]
                before=deepcopy(candidate)
                normalized,applied=controller.apply_approved_differences(*candidate,dict(theme_resources=[],full_text_indexes=[rule]))
                self.assertEqual(bool(applied),change=='none')
                self.assertEqual(candidate,before)
                if change=='none':self.assertEqual(normalized[0],normalized[1])

    def test_mixed_index_requires_null_extra_and_bounded_shared_key(self):
        raw,rule,column=self.fixture()
        obj=raw[1]['records'][0]['schema_objects'][0]
        obj.update(columns=['id','extra_key'],key_count=2,attribute_count=2,
                   key_metadata=obj['key_metadata']*2,
                   definition='CREATE INDEX sample_extra ON public.sample USING btree (id, extra_key)')
        old=rule['ddl'];rule.update(catalog=deepcopy(obj),ddl=obj['definition']+';')
        raw[1]['schema']=raw[1]['schema'].replace(old,rule['ddl'])
        self.assertEqual(len(self.apply(raw,rule,column)[1]),1)
        for side in raw:side['records'][0]['columns'][0]['type']='character varying(200)'
        self.assertEqual(self.apply(raw,rule,column)[1],[])

    def test_expression_column_null_cannot_crash_matcher(self):
        raw,rule,column=self.fixture()
        raw[1]['records'][0]['schema_objects'][0]['columns']=[None]
        rule['catalog']['columns']=[None]
        self.assertEqual(self.apply(raw,rule,column)[1],[])

    def test_filtered_seed_cannot_hide_populated_foreign_key(self):
        raw,rule,column=self.fixture('foreign_key')
        proof=deepcopy(raw)
        proof[1]['records'][1]['row']['extra_key']='seed-target'
        for pair in (raw,proof):
            for snapshot in pair:snapshot['records']=[json.dumps(r) for r in snapshot['records']]
        _,applied=controller.apply_approved_differences(*raw,dict(theme_resources=[],full_text_indexes=[],
            rust_only_columns=[column],schema_additions=[rule]),schema_proof=proof)
        self.assertFalse(any(r['kind']=='schema_addition' for r in applied))

    def test_every_catalog_field_is_required_even_when_rule_also_omits_it(self):
        for kind in ('index','foreign_key'):
            fields=list(self.fixture(kind)[1]['catalog'])
            for field in fields:
                with self.subTest(kind=kind,field=field):
                    raw,rule,column=self.fixture(kind)
                    del raw[1]['records'][0]['schema_objects'][0][field]
                    del rule['catalog'][field]
                    self.assertEqual(self.apply(raw,rule,column)[1],[])

    def test_catalog_field_types_and_nested_key_proof_are_required(self):
        for kind in ('index','foreign_key'):
            fields=self.fixture(kind)[1]['catalog']
            for field,old in fields.items():
                with self.subTest(kind=kind,field=field):
                    raw,rule,column=self.fixture(kind)
                    bad = 1 if type(old) is bool else True if type(old) is int else {} if isinstance(old,list) else []
                    raw[1]['records'][0]['schema_objects'][0][field]=bad
                    rule['catalog'][field]=deepcopy(bad)
                    self.assertEqual(self.apply(raw,rule,column)[1],[])
        for field in ('opclass','collation','option'):
            for mode in ('missing','bad_type'):
                with self.subTest(field=field,mode=mode):
                    raw,rule,column=self.fixture()
                    for obj in (raw[1]['records'][0]['schema_objects'][0],rule['catalog']):
                        if mode=='missing':del obj['key_metadata'][0][field]
                        else:obj['key_metadata'][0][field]=True
                    self.assertEqual(self.apply(raw,rule,column)[1],[])

    def test_unrelated_names_do_not_block_exact_target(self):
        for kind in ('index','foreign_key'):
            raw,rule,column=self.fixture(kind)
            other=('CREATE INDEX sample_extra ON other.sample USING btree (id);' if kind=='index' else
                   'ALTER TABLE ONLY public.other\n    ADD CONSTRAINT sample_extra FOREIGN KEY (id) REFERENCES public.parent(id);')
            for snapshot in raw:snapshot['schema']+=other+'\n'
            normalized,applied=self.apply(raw,rule,column)
            self.assertEqual(len(applied),1)
            self.assertEqual(normalized[0],normalized[1])
            self.assertIn(other,normalized[1]['schema'])

    def test_same_schema_index_name_or_same_table_fk_duplicate_stays_strict(self):
        for kind in ('index','foreign_key'):
            for side in (0,1):
                with self.subTest(kind=kind,side=side):
                    raw,rule,column=self.fixture(kind)
                    conflict=('CREATE INDEX sample_extra ON public.other USING btree (id);' if kind=='index' else
                              'ALTER TABLE ONLY public.sample\n    ADD CONSTRAINT sample_extra FOREIGN KEY (id) REFERENCES public.parent(id);')
                    raw[side]['schema']+=conflict+'\n'
                    self.assertEqual(self.apply(raw,rule,column)[1],[])

    def test_index_and_foreign_key_can_share_a_name(self):
        raw,rule,column=self.fixture('foreign_key')
        other=self.fixture()[1]['catalog']
        other['columns']=['id']
        other['definition']='CREATE INDEX sample_extra ON public.sample USING btree (id)'
        for snapshot in raw:
            snapshot['schema']+=other['definition']+';\n'
            snapshot['records'][0]['schema_objects'].append(deepcopy(other))
        normalized,applied=self.apply(raw,rule,column)
        self.assertEqual(len(applied),1)
        self.assertEqual(normalized[0],normalized[1])

    def test_snapshot_compare_serializes_exact_catalog_numbers(self):
        for kind in ('index', 'foreign_key'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                raw, rule, column = self.fixture(kind)
                paths = [root / 'java.json', root / 'rust.json']
                for path, snapshot in zip(paths, raw):
                    path.write_text(json.dumps({**snapshot, 'records': [json.dumps(r) for r in snapshot['records']]}))
                approved = {**controller.APPROVED_STARTUP_DIFFERENCES, 'rust_only_columns': [column], 'schema_additions': [rule]}
                self.assertTrue(controller.snapshot_compare(*paths, root, approved_differences=approved, emit_report=False))
                summary = json.loads((root / 'summary.json').read_text(), parse_int=Decimal, parse_float=Decimal)
                catalog = summary['shared_relation_differences']['public.sample']['rust']['schema_objects'][0]
                field = 'key_count' if kind == 'index' else 'inherited'
                self.assertIsInstance(catalog[field], Decimal)
                self.assertEqual(catalog[field], rule['catalog'][field])
                comparison = json.loads((root / 'comparison.json').read_text())
                self.assertFalse(comparison['row_and_sequence_values_equal'])
                self.assertTrue(comparison['comparison_passed'])
                self.assertEqual(len([r for r in comparison['approved_differences_applied'] if r['kind']=='schema_addition']), 1)
                parsed = json.loads(json.dumps(rule['catalog']), parse_int=Decimal)
                self.assertTrue(controller.complete_schema_object(parsed))
                parsed[field] += Decimal('0.5')
                self.assertFalse(controller.complete_schema_object(parsed))

    def test_report_numbers_never_round_or_become_strings(self):
        values = [Decimal('123456789012345678901234567890.1234567890123456789'), Decimal('1e-80'), Decimal('1e80')]
        encoded = controller.report_json({'numbers': values})
        self.assertEqual(json.loads(encoded, parse_int=Decimal, parse_float=Decimal), {'numbers': values})
        for value in ('NaN', 'Infinity', '-Infinity'):
            with self.assertRaises(ValueError):
                controller.report_json({'number': Decimal(value)})
