import importlib.util
import subprocess
from pathlib import Path
root = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('screen_probe', root/'ui-test/compare-screen.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
original_loader = probe.importlib.util.module_from_spec

def load_controller(spec):
    module = original_loader(spec)
    if spec.name == 'screen_probe_controller':
        original_exec = spec.loader.exec_module
        def execute(module):
            original_exec(module)
            original_boot = module.boot_and_stop
            def boot(args):
                args.exclude_rust_only = False
                args.source_root = root
                original_probe = module.run_visual_tests
                def with_fixture(args, evidence):
                    sql = """INSERT INTO invoice (invoice_id, invoice_type_enum_id, from_party_id, to_party_id,
                        status_id, invoice_date, due_date, description, currency_uom_id, invoice_total,
                        applied_payments_total, unpaid_total, last_updated_stamp)
                        VALUES ('UI_PARITY_INVOICE', 'InvoiceSales', 'ORG_ZIZI_RETAIL', 'CustJqp',
                        'InvoiceInProcess', '2026-10-01 12:00:00', '2026-10-31 12:00:00',
                        'UI parity invoice', 'USD', 0, 0, 0, '2026-10-01 12:00:00');"""
                    (evidence/'invoice-fixture.sql').write_text(sql+'\n')
                    for engine in ('java','rust'):
                        container = f'moqui-regression-{evidence.name}-{engine}'
                        subprocess.run(['docker','exec','-i',container,'psql','-U','moqui','-d','moqui','-v','ON_ERROR_STOP=1'],
                            input=sql, text=True, check=True)
                    try:
                        original_probe(args,evidence)
                    finally:
                        # Perform the controller's real Step 4 after capture, even on visual mismatch.
                        args.skip_step_4 = False
                module.run_visual_tests = with_fixture
                return original_boot(args)
            module.boot_and_stop = boot
        spec.loader.exec_module = execute
    return module
probe.importlib.util.module_from_spec = load_controller
probe.main()
