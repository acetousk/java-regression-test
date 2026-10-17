import json
from pathlib import Path
import tempfile
import unittest
import urllib.request

from deterministic import DeterministicCoordinator


class DeterministicRandomTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.coordinator = DeterministicCoordinator('test', self.root, random_seed='00' * 32)

    def draw(self, side='java', domain='entity:moqui.server.Visitor', length=16, coordinator=None):
        return (coordinator or self.coordinator).exchange(dict(
            version=1, run_id='test', engine=side, event='random', domain=domain, length=length))['bytes']

    def test_peer_streams_are_equal_without_waiting_or_shared_consumption(self):
        first = self.draw()
        second = self.draw()
        self.assertEqual(first, '06cc2a3fd9cad5c044bc541deace7c95')
        self.assertNotEqual(first, second)
        self.assertEqual(first, self.draw('rust'))
        self.assertEqual(second, self.draw('rust'))
        self.assertEqual(self.coordinator.status()['write_transactions'], 0)

    def test_domains_isolate_unrelated_internal_draws(self):
        self.draw(domain='eeca-location')
        self.draw(domain='session-id', length=20)
        self.assertEqual(self.draw(), self.draw('rust'))

    def test_seed_replays_and_changes_output(self):
        expected = self.draw()
        other = DeterministicCoordinator('test', self.root / 'replay', random_seed='00' * 32)
        self.assertEqual(expected, self.draw(coordinator=other))
        other = DeterministicCoordinator('test', self.root / 'new', random_seed='01' * 32)
        self.assertNotEqual(expected, self.draw(coordinator=other))
        saved = json.loads((self.root / 'random-seed.json').read_text())
        self.assertEqual(saved, {'algorithm': 'hmac-sha256-v1', 'seed': '00' * 32})
        self.assertEqual((self.root / 'random-seed.json').stat().st_mode & 0o777, 0o600)

    def test_step_5_streams_do_not_depend_on_loading_draw_counts(self):
        self.coordinator.bootstrap = True
        loading = self.draw()
        self.draw()
        self.coordinator.activate(lambda: None)
        activity = self.draw()
        self.assertNotEqual(loading, activity)
        self.assertEqual(activity, self.draw('rust'))

    def test_multiblock_bytes_have_stable_prefix_and_private_metadata(self):
        value = self.draw(length=4096)
        self.assertEqual(len(value), 8192)
        self.assertEqual(value[:32], self.draw('rust'))
        records = [json.loads(line) for line in (self.root / 'random-draws.jsonl').read_text().splitlines()]
        self.assertEqual(records[0], dict(engine='java', phase='activity',
            domain='entity:moqui.server.Visitor', index=0, length=4096))
        self.assertNotIn(value, (self.root / 'random-draws.jsonl').read_text())

    def test_invalid_requests_poison_the_coordinator_and_never_fall_back(self):
        for changes in ({'length': 0}, {'length': True}, {'length': 4097}, {'domain': ''},
                        {'domain': '\n'}, {'domain': 'é'}, {'engine': 'other'}, {'run_id': 'other'},
                        {'version': True}, {'extra': 1}):
            with self.subTest(changes=changes):
                coordinator = DeterministicCoordinator('test', self.root, random_seed='00' * 32)
                request = dict(version=1, run_id='test', engine='java', event='random', domain='test', length=16)
                with self.assertRaises(ValueError):
                    coordinator.exchange({**request, **changes})
                self.assertIsNotNone(coordinator.error)
                with self.assertRaises(ValueError):
                    coordinator.exchange(request)

    def test_invalid_seeds_rejected(self):
        for seed in ('', 'aa', 'AA' * 32, 'zz' * 32, 1):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                DeterministicCoordinator('test', self.root, random_seed=seed)

    def test_http_protocol_returns_the_same_bytes_to_both_engines(self):
        url = self.coordinator.start()
        try:
            results = []
            for side in ('java', 'rust'):
                request = dict(version=1, run_id='test', engine=side, event='random', domain='uuid', length=16)
                with urllib.request.urlopen(urllib.request.Request(url,
                        json.dumps(request).encode(), {'Content-Type': 'application/json'})) as response:
                    results.append(json.load(response))
            self.assertEqual(results[0], results[1])
        finally:
            self.coordinator.close()
