"""Per-write-transaction database barriers for the Java/Rust regression harness (stdlib only)."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time


class DeterministicCoordinator:
    """Pairs the engines' committed write transactions and compares both databases after each pair.

    Transaction begins are answered at once with the shared logical time: the run's start plus the
    number of write transactions paired so far. Operation order and artifact identity are not
    compared; the engines' logs are diagnostics only.

    On each completion the coordinator reads that engine's PostgreSQL change data capture (``cdc``).
    A completion that produced no committed change (a read, a rollback) is acknowledged at once, as
    is a Rust write made only of approved Rust-only changes. Any other write waits for the peer's next write; both databases are then compared before either engine
    continues. A pair whose sides committed different numbers of transactions fails.
    """
    def __init__(self, run_id, evidence, compare=None, cdc=None, timeout=120, start_millis=None,
                 rust_only=None, operation_checks=False, exempt=None):
        self.run_id = run_id
        self.operation_checks = operation_checks
        self.operation_events = []
        self.operation_positions = {side: 0 for side in ('java', 'rust')}
        self.operation_sequences = {side: 0 for side in ('java', 'rust')}
        self.operation_comparisons = 0
        # rust_only(change) is true for a CDC change line covered by an approved Rust-only difference.
        # A Rust transaction made only of such changes has no Java peer.
        self.rust_only = rust_only
        self.exempt = exempt
        self.exempt_writes = {side: 0 for side in ('java', 'rust')}
        self.rust_only_writes = 0
        self.evidence = Path(evidence)
        self.compare = compare
        self.cdc = cdc
        self.timeout = timeout
        self.start_millis = time.time_ns() // 1_000_000 if start_millis is None else start_millis
        self.condition = threading.Condition()
        self.sides = ("java", "rust")
        self.stacks = {side: [] for side in self.sides}
        self.sequences = {side: 0 for side in self.sides}
        self.counts = {side: {"begin": 0, "committed": 0, "rolled_back": 0, "begin_failed": 0}
                       for side in self.sides}
        self.pending = {side: [] for side in self.sides}
        self.arrived = {side: None for side in self.sides}
        self.pairs = []
        self.comparisons = 0
        self.trace_counts = {}
        self.error = None
        self.closed = False
        self.final_incremental_equal = None
        self.server = None
        self.thread = None

    def fail(self, message):
        with self.condition:
            if self.error is None:
                self.error = message
            self.condition.notify_all()

    def check_health(self):
        with self.condition:
            if self.error:
                raise RuntimeError(f"Deterministic verification failed: {self.error}")

    def _validate(self, request):
        side = request.get("engine")
        if (type(request.get("version")) is not int or request["version"] != 1
                or request.get("run_id") != self.run_id or side not in self.sides):
            raise ValueError("Invalid protocol version, run, or engine")
        sequence = request.get("sequence")
        if type(sequence) is not int or sequence <= 0:
            raise ValueError("sequence must be a positive integer")
        event = request.get("event")
        if event == "operation":
            if not self.operation_checks:
                raise ValueError('Operation checks are not enabled')
            if set(request) != {'version', 'run_id', 'engine', 'event', 'sequence', 'kind', 'action', 'name', 'outcome', 'transaction_sequence'}:
                raise ValueError('Unexpected operation fields')
            if (sequence <= self.operation_sequences[side]
                    or any(not isinstance(request.get(key), str) or not request[key]
                           for key in ('kind', 'action', 'name'))):
                raise ValueError('Invalid operation identity or sequence')
            if request['outcome'] not in ('exit', 'succeeded', 'failed', 'skipped'):
                raise ValueError('Invalid operation outcome')
            parent = request['transaction_sequence']
            if parent is not None and (type(parent) is not int or not any(entry[0] == parent for entry in self.stacks[side])):
                raise ValueError('Operation transaction scope is not active')
            return side, sequence, event
        if event == "begin":
            if sequence <= self.sequences[side]:
                raise ValueError("Transaction sequence must increase")
            return side, sequence, event
        if event == "complete":
            if request.get("outcome") not in ("committed", "rolled_back", "begin_failed"):
                raise ValueError("Invalid completion outcome")
            if not any(entry[0] == sequence and entry[1] == request.get("operation_id")
                       for entry in self.stacks[side]):
                raise ValueError("Completion does not match an active transaction")
            return side, sequence, event
        raise ValueError("Unknown transaction event")

    def _exempt(self, side, transaction):
        approved = (self.exempt(side, transaction) if self.exempt is not None else
                    side == 'rust' and transaction and self.rust_only is not None
                    and all(map(self.rust_only, transaction)))
        if approved:
            self.exempt_writes[side] += 1
            if side == 'rust':
                self.rust_only_writes += 1
        return bool(approved)

    def _time(self):
        return self.start_millis + len(self.pairs)

    def exchange(self, request):
        with self.condition:
            try:
                if self.error:
                    raise ValueError(self.error)
                side, sequence, event = self._validate(request)
                if event == 'operation':
                    return self._operation(side, request)
                if event == "begin":
                    self.sequences[side] = sequence
                    self.counts[side]["begin"] += 1
                    operation_id = f"{side}-{sequence:08d}"
                    self.stacks[side].append((sequence, operation_id))
                    return {"operation_id": operation_id, "time_epoch_ms": self._time()}
                self.stacks[side] = [entry for entry in self.stacks[side] if entry[0] != sequence]
                self.counts[side][request["outcome"]] += 1
                changes = []
                if self.cdc is not None:
                    # Read outside the lock so the peer can arrive meanwhile.
                    self.condition.release()
                    try:
                        changes = self.cdc(side)
                    finally:
                        self.condition.acquire()
                if self.error:
                    raise ValueError(self.error)
                changes = [transaction for transaction in changes
                           if not self._exempt(side, transaction)]
                for transaction in changes:
                    self.pending[side].append({"operation_id": request["operation_id"],
                                               "outcome": request["outcome"], "changes": transaction})
                if not self.pending[side]:
                    return {"ok": True}
                return self._barrier(side, request)
            except Exception as exc:
                self.fail(str(exc))
                raise

    def _operation(self, side, request):
        index = self.operation_positions[side]
        signature = {key: request[key] for key in ('kind', 'action', 'name', 'outcome')}
        if index == len(self.operation_events):
            self.operation_events.append({'signature': signature, 'requests': {}, 'ready': False})
        event = self.operation_events[index]
        if side in event['requests']:
            raise ValueError('Concurrent operation execution in one engine')
        event['requests'][side] = deepcopy(request)
        self.operation_sequences[side] = request['sequence']
        if signature != event['signature']:
            raise ValueError(f'Operation identity mismatch at operation {index + 1}: {event["requests"]}')
        if self.cdc is not None:
            self.condition.release()
            try:
                changes = self.cdc(side)
            finally:
                self.condition.acquire()
            self.pending[side].extend({'operation_id': None, 'outcome': 'operation-boundary', 'changes': item}
                                      for item in changes if not self._exempt(side, item))
        # Arrival includes PostgreSQL capture, not merely receipt of the engine hook.
        event.setdefault('captured', set()).add(side)
        if len(event['captured']) == 2:
            if self.compare is None:
                raise ValueError('Operation comparison callback is required')
            self.condition.release()
            try:
                equal = self.compare(f'operation-{index + 1:08d}')
            finally:
                self.condition.acquire()
            if self.error:
                raise ValueError(self.error)
            if not equal:
                raise ValueError(f'Database mismatch after operation {index + 1}')
            self.operation_comparisons += 1
            event['ready'] = True
            self.condition.notify_all()
        deadline = time.monotonic() + self.timeout
        while not event['ready'] and not self.error:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f'Peer did not reach operation {index + 1}')
            self.condition.wait(remaining)
        if self.error:
            raise ValueError(self.error)
        self.operation_positions[side] += 1
        return {'ok': True, 'state': 'committed-only',
                'uncommitted_pending': request['transaction_sequence'] is not None}

    def _barrier(self, side, request):
        if self.arrived[side] is not None:
            raise ValueError("Concurrent write transactions in one engine")
        self.arrived[side] = request["operation_id"]
        round_number = len(self.pairs)
        peer = "rust" if side == "java" else "java"
        if self.arrived[peer] is not None:
            index = round_number + 1
            pair = {"index": index, "time_epoch_ms": self._time(),
                    **{name: {"operation_id": self.arrived[name],
                              "transactions": deepcopy(self.pending[name])} for name in self.sides}}
            self._write_cdc(index, pair)
            counts = {name: len(self.pending[name]) for name in self.sides}
            if counts["java"] != counts["rust"]:
                raise ValueError(f"Write {index}: java committed {counts['java']} transactions, "
                                 f"rust committed {counts['rust']}")
            if counts["java"] != 1:
                raise ValueError(f"Write {index}: multiple commits cannot be verified as one transaction")
            # Approved differences can change raw rows, so the database comparison is the gate.
            cdc_equal = ([t["changes"] for t in self.pending["java"]]
                         == [t["changes"] for t in self.pending["rust"]])
            if self.compare is not None:
                self.condition.release()
                try:
                    equal = self.compare(f"write-{index:08d}")
                finally:
                    self.condition.acquire()
                if self.error:
                    raise ValueError(self.error)
                if not equal:
                    raise ValueError(f"Database mismatch after write {index}")
                self.comparisons += 1
            self.pairs.append({key: value for key, value in pair.items() if key not in self.sides}
                              | {"transactions": counts["java"], "cdc_equal": cdc_equal}
                              | {name: {"operation_id": pair[name]["operation_id"],
                                        "changes": sum(len(t["changes"]) for t in pair[name]["transactions"])}
                                 for name in self.sides})
            for name in self.sides:
                self.pending[name] = []
                self.arrived[name] = None
            self.condition.notify_all()
            return {"ok": True}
        deadline = time.monotonic() + self.timeout
        while len(self.pairs) == round_number and not self.error:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{peer} did not commit write {round_number + 1}")
            self.condition.wait(remaining)
        if self.error:
            raise ValueError(self.error)
        return {"ok": True}

    def _write_cdc(self, index, pair):
        directory = self.evidence / "transactions" / f"write-{index:08d}"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        for name in self.sides:
            (directory / f"{name}-cdc.json").write_text(json.dumps(pair[name], indent=2) + "\n")

    def start(self):
        coordinator = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                # Read-only progress for UI drivers: proves an action's writes were paired and compared.
                if self.path == "/status":
                    payload, status = coordinator.status(), 200
                else:
                    payload, status = {"error": "Unknown status path"}, 404
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                try:
                    if self.path != "/transaction":
                        raise ValueError("Unknown hook path")
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 65536:
                        raise ValueError("Invalid request size")
                    request = json.loads(self.rfile.read(size))
                    if not isinstance(request, dict):
                        raise ValueError("Expected a JSON object")
                    payload = coordinator.exchange(request)
                    status = 200
                except Exception as exc:
                    coordinator.fail(str(exc))
                    payload, status = {"error": str(exc)}, 409
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except OSError:
                    coordinator.fail("Engine disconnected before receiving hook response")

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return f"http://127.0.0.1:{self.server.server_port}/transaction"

    def status(self):
        with self.condition:
            return {"error": self.error, "write_transactions": len(self.pairs),
                    "database_comparisons": self.comparisons, "rust_only_writes": self.rust_only_writes,
                    "unpaired_writes": {side: len(items) for side, items in self.pending.items()},
                    "waiting_at_barrier": {side: self.arrived[side] is not None for side in self.sides}}

    def report(self):
        with self.condition:
            operation_settled = (not self.operation_checks or (self.operation_comparisons > 0
                                 and all(event['ready'] for event in self.operation_events)
                                 and self.operation_positions['java'] == self.operation_positions['rust']
                                 == len(self.operation_events)))
            settled = not any(self.pending.values()) and not any(self.stacks.values()) and operation_settled
            return {"protocol_version": 2, "run_id": self.run_id, "start_epoch_ms": self.start_millis,
                    "write_transactions": len(self.pairs), "database_comparisons": self.comparisons,
                    "error": self.error, "transaction_counts": deepcopy(self.counts),
                    "rust_only_writes": self.rust_only_writes,
                    "exempt_writes": deepcopy(self.exempt_writes),
                    "unpaired_writes": {side: len(items) for side, items in self.pending.items()},
                    "operation_trace_counts": deepcopy(self.trace_counts),
                    "operation_checks_enabled": self.operation_checks,
                    "operation_order_equal": (operation_settled and self.error is None) if self.operation_checks else None,
                    "operation_database_comparisons": self.operation_comparisons,
                    "uncommitted_state_verified": False,
                    "final_incremental_equal": self.final_incremental_equal,
                    "operations": [{key: deepcopy(value) for key, value in event.items() if key != 'captured'}
                                   for event in self.operation_events],
                    "per_transaction_databases_equal": self.error is None and settled
                    and bool(self.pairs) and self.compare is not None
                    and self.cdc is not None and self.comparisons == len(self.pairs)
                    and (not self.closed or self.final_incremental_equal is True),
                    "pairs": deepcopy(self.pairs)}

    def summarize_logs(self):
        """Count each engine's trace kinds. Logs are diagnostics, not a parity gate."""
        with self.condition:
            self.trace_counts = {}
            for side in self.sides:
                counts = {}
                try:
                    for line in (self.evidence / f"{side}-deterministic.log").read_text().splitlines():
                        record = json.loads(line)
                        if isinstance(record, dict) and record.get("event") == "trace":
                            counts[str(record.get("kind"))] = counts.get(str(record.get("kind")), 0) + 1
                except (OSError, ValueError):
                    counts = None
                self.trace_counts[side] = counts

    def close(self):
        with self.condition:
            if self.error is None and (any(self.arrived.values())
                                       or any(not event['ready'] for event in self.operation_events)):
                self.fail('Controller closed with engines waiting at a barrier')
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join()
        # A late write still on one side has no peer: drain it so it is reported, not lost.
        if self.cdc is not None and self.error is None:
            for side in self.sides:
                try:
                    self.pending[side].extend({"operation_id": None, "outcome": "unhooked", "changes": changes}
                                              for changes in self.cdc(side)
                                              if not self._exempt(side, changes))
                except Exception as exc:  # The database may be gone after a failed start.
                    self.fail(f"Could not read {side} change data: {exc}")
        with self.condition:
            if self.error is None and self.operation_checks and not self.report()['operation_order_equal']:
                self.fail('Incomplete operation stream')
            if self.error is None and any(self.stacks.values()):
                self.fail('Incomplete transaction stream')
            if self.error is None and any(self.pending.values()):
                self.fail(f"Unpaired write transactions: {self.report()['unpaired_writes']}")
            if self.error is None and not self.pairs:
                self.fail("No write transactions were paired")
        if self.error is None and self.compare is not None:
            try:
                self.final_incremental_equal = bool(self.compare('final-drain'))
                if not self.final_incremental_equal:
                    self.fail('Database mismatch after final incremental drain')
            except Exception as exc:
                self.fail(f'Final incremental drain failed: {exc}')
        self.closed = True
        self.summarize_logs()
        path = self.evidence / "deterministic-report.json"
        path.write_text(json.dumps(self.report(), indent=2) + "\n")
