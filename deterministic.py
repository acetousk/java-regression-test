"""Strict paired transaction barriers for the Java/Rust regression harness (stdlib only)."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time


class DeterministicCoordinator:
    """Neither engine leaves a barrier until its peer supplies the same event.

    A completion barrier optionally compares committed database state before either
    engine is acknowledged. No unmatched operation is skipped or assigned a time.
    """
    def __init__(self, run_id, evidence, compare=None, timeout=120,
                 start_millis=1760000000000, require_logs=False):
        self.run_id = run_id
        self.evidence = Path(evidence)
        self.compare = compare
        self.timeout = timeout
        self.start_millis = start_millis
        self.require_logs = require_logs
        self.logs_verified = False
        self.trace_counts = {}
        self.condition = threading.Condition()
        self.events = []
        self.positions = {side: 0 for side in ("java", "rust")}
        self.sequences = {side: 0 for side in self.positions}
        self.stacks = {side: [] for side in self.positions}
        self.operations = 0
        self.comparisons = 0
        self.error = None
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
                or request.get("run_id") != self.run_id or not isinstance(side, str) or side not in self.positions):
            raise ValueError("Invalid protocol version, run, or engine")
        sequence = request.get("sequence")
        if type(sequence) is not int or sequence <= 0:
            raise ValueError("sequence must be a positive integer")
        event = request.get("event")
        fields = {"version", "run_id", "engine", "sequence", "event"}
        if event == "begin":
            fields |= {"parent_sequence", "artifact", "artifact_stack"}
        elif event == "complete":
            fields |= {"operation_id", "outcome"}
        if set(request) != fields:
            raise ValueError("Unexpected or missing transaction event fields")
        if event == "begin":
            if sequence != self.sequences[side] + 1:
                raise ValueError("Non-consecutive operation sequence")
            parent = self.stacks[side][-1][0] if self.stacks[side] else None
            if request.get("parent_sequence") != parent:
                raise ValueError("Incorrect parent transaction sequence")
            artifact = request.get("artifact")
            stack = request.get("artifact_stack")
            if (not isinstance(artifact, dict) or not isinstance(stack, list)
                    or not stack or stack[0] != artifact):
                raise ValueError("Missing artifact metadata or innermost-first stack")
            for item in [artifact, *stack]:
                if (not isinstance(item, dict) or set(item) != {"type", "sub_type", "name"}
                        or any(not isinstance(value, str) for value in item.values())):
                    raise ValueError("Invalid artifact metadata")
            return {"event": event, "parent_sequence": parent,
                    "artifact": artifact, "artifact_stack": stack}
        if event == "complete":
            if not self.stacks[side] or self.stacks[side][-1] != (sequence, request.get("operation_id")):
                raise ValueError("Completion does not match the active transaction")
            outcome = request.get("outcome")
            if outcome not in ("committed", "rolled_back", "begin_failed"):
                raise ValueError("Invalid completion outcome")
            return {"event": event, "operation_id": request["operation_id"], "outcome": outcome}
        raise ValueError("Unknown transaction event")

    def exchange(self, request):
        deadline = time.monotonic() + self.timeout
        with self.condition:
            try:
                if self.error:
                    raise ValueError(self.error)
                signature = self._validate(request)
                side = request["engine"]
                index = self.positions[side]
                if index == len(self.events):
                    self.events.append({"requests": {}, "signature": signature, "ready": False})
                barrier = self.events[index]
                if side in barrier["requests"]:
                    raise ValueError("Concurrent application execution detected")
                barrier["requests"][side] = deepcopy(request)
                if signature != barrier["signature"]:
                    raise ValueError(f"Operation order/metadata mismatch at event {index + 1}")
                if len(barrier["requests"]) == 2:
                    if signature["event"] == "begin":
                        self.operations += 1
                        response = {"operation_id": f"op-{self.operations:08d}",
                                    "time_epoch_ms": self.start_millis + self.operations - 1}
                        for engine, incoming in barrier["requests"].items():
                            self.sequences[engine] = incoming["sequence"]
                            self.stacks[engine].append((incoming["sequence"], response["operation_id"]))
                    else:
                        # Both applications are paused after completing the transaction.
                        # Keep the barrier closed, but let health checks/abort acquire the lock.
                        if self.compare is not None:
                            self.condition.release()
                            try:
                                equal = self.compare(signature["operation_id"], signature["outcome"])
                            finally:
                                self.condition.acquire()
                            if self.error:
                                raise ValueError(self.error)
                            if not equal:
                                raise ValueError(f"Database mismatch after {signature['operation_id']}")
                            self.comparisons += 1
                        for engine in self.stacks:
                            self.stacks[engine].pop()
                        response = {"ok": True}
                    barrier["response"] = response
                    barrier["ready"] = True
                    self.condition.notify_all()
                while not barrier["ready"] and not self.error:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(f"Peer did not reach event {index + 1}")
                    self.condition.wait(remaining)
                if self.error:
                    raise ValueError(self.error)
                self.positions[side] += 1
                return deepcopy(barrier["response"])
            except Exception as exc:
                self.fail(str(exc))
                raise

    def start(self):
        coordinator = self

        class Handler(BaseHTTPRequestHandler):
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

    def report(self):
        with self.condition:
            complete = (self.operations > 0 and self.positions["java"] == self.positions["rust"]
                        == len(self.events) and all(event["ready"] for event in self.events)
                        and not any(self.stacks.values()))
            return {"protocol_version": 1, "run_id": self.run_id, "operations": self.operations,
                    "database_comparisons": self.comparisons, "error": self.error,
                    "engine_logs_verified": self.logs_verified,
                    "operation_trace_counts": deepcopy(self.trace_counts),
                    "operation_order_equal": complete and self.error is None,
                    "per_transaction_databases_equal": complete and self.error is None
                    and (self.logs_verified or not self.require_logs)
                    and self.compare is not None and self.comparisons == self.operations,
                    "events": deepcopy(self.events)}

    def verify_logs(self):
        with self.condition:
            self.logs_verified = False
            for side in self.positions:
                path = self.evidence / f"{side}-deterministic.log"
                try:
                    records = [json.loads(line) for line in path.read_text().splitlines()]
                    traces = [record for record in records if isinstance(record, dict) and record.get("event") == "trace"]
                    counts = {}
                    for sequence, trace in enumerate(traces, 1):
                        if (set(trace) != {"version", "run_id", "engine", "event", "trace_sequence",
                                          "kind", "action", "name", "outcome", "parent_sequence", "time_epoch_ms"}
                                or type(trace["version"]) is not int or trace["version"] != 1
                                or trace["run_id"] != self.run_id or trace["engine"] != side
                                or type(trace["trace_sequence"]) is not int or trace["trace_sequence"] != sequence
                                or any(not isinstance(trace[key], str) for key in ("kind", "action", "name"))
                                or trace["outcome"] not in ("requested", "succeeded", "failed", "enter", "exit", "skipped")
                                or (trace["parent_sequence"] is not None and
                                    (type(trace["parent_sequence"]) is not int or trace["parent_sequence"] <= 0))
                                or (trace["time_epoch_ms"] is not None and type(trace["time_epoch_ms"]) is not int)):
                            raise ValueError("Invalid operation trace")
                        counts[trace["kind"]] = counts.get(trace["kind"], 0) + 1
                    self.trace_counts[side] = counts
                    records = [record for record in records if not isinstance(record, dict) or record.get("event") != "trace"]
                    expected = []
                    for barrier in self.events:
                        if not barrier["ready"]:
                            raise ValueError("Unacknowledged transaction event")
                        event = deepcopy(barrier["requests"][side])
                        if event["event"] == "begin":
                            event.update(barrier["response"])
                        expected.append(event)
                    if len(records) != len(expected) or any(
                            not isinstance(actual, dict) or any(actual.get(key) != value
                                                               for key, value in event.items())
                            for actual, event in zip(records, expected)):
                        raise ValueError("Engine log differs from acknowledged transaction stream")
                except (OSError, ValueError, KeyError) as exc:
                    self.fail(f"{side} deterministic.log verification failed: {exc}")
                    return
            self.logs_verified = True

    def close(self):
        # Release any requests still waiting for an engine that exited.
        with self.condition:
            if not self.report()["operation_order_equal"] and self.error is None:
                self.fail("Incomplete deterministic transaction stream")
        if self.require_logs and self.error is None:
            self.verify_logs()
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join()
        path = self.evidence / "deterministic-report.json"
        path.write_text(json.dumps(self.report(), indent=2) + "\n")
