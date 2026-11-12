"""Change 5: supplied data time for disposable paired runs; this is not a transaction coordinator."""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile

ENV = 'MOQUI_TEST_DATA_CLOCK_FILE'
MAX_MILLIS = 253402300799999


def validate_epoch(value):
    if type(value) is not int or not 1 <= value <= MAX_MILLIS:
        raise ValueError('data clock requires integer epoch milliseconds in years 1970 through 9999')
    return value


def read_assignment(path):
    path = Path(path)
    if not path.is_absolute() or not path.is_file():
        raise ValueError('data clock requires an absolute regular file')
    with path.open('rb') as stream:
        value = stream.read(33)
    if value.endswith(b'\n'):
        value = value[:-1]
    if not 1 <= len(value) <= 15 or not all(48 <= byte <= 57 for byte in value):
        raise ValueError('data clock requires positive ASCII epoch milliseconds')
    return validate_epoch(int(value))


class SuppliedDataClock:
    """Own a new file; caller must await BOTH engines and disable background writers before advancing.

    Hold paired_operation across both operations AND persisted-state verification. This guards harness
    sequencing, not unknown engine tasks: it cannot establish quiescence of unobserved background work.
    """
    def __init__(self, path, epoch_ms):
        self.path = Path(path)
        if not self.path.is_absolute():
            raise ValueError('data clock path must be absolute')
        self.epoch_ms = validate_epoch(epoch_ms)
        self._active = False
        with self.path.open('xb') as stream:
            os.chmod(self.path, 0o600)
            stream.write(f'{self.epoch_ms}\n'.encode('ascii'))
            stream.flush()
            os.fsync(stream.fileno())

    def environment(self):
        self.verify_assignment()
        return {ENV: str(self.path)}

    def verify_assignment(self):
        if read_assignment(self.path) != self.epoch_ms:
            raise ValueError('supplied data clock file differs from harness assignment')
        return self.epoch_ms

    @contextmanager
    def paired_operation(self):
        if self._active:
            raise RuntimeError('a paired operation is already active')
        self.verify_assignment()
        self._active = True
        try:
            yield self.epoch_ms
            self.verify_assignment()
        finally:
            self._active = False

    def advance(self, epoch_ms):
        if self._active:
            raise RuntimeError('cannot advance time while a paired operation is active')
        self.verify_assignment()
        epoch_ms = validate_epoch(epoch_ms)
        if epoch_ms <= self.epoch_ms:
            raise ValueError('next supplied data time must advance')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix='.data-clock-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(f'{epoch_ms}\n'.encode('ascii'))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self.epoch_ms = epoch_ms
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.verify_assignment()


def verify_persisted_millis(expected, observed):
    """Require actual database-extracted milliseconds, independently equal to the supplied assignment.

    The caller queries epoch milliseconds from last_updated_stamp in UTC; do not pass rewritten rows,
    engine log acknowledgments, or only a cross-engine equality boolean.
    """
    validate_epoch(expected)
    if set(observed) != {'java', 'rust'}:
        raise ValueError('timestamp proof requires both engines')
    for side, values in observed.items():
        if not values or any(type(value) is not int or value != expected for value in values):
            raise ValueError(f'{side} persisted timestamp does not match supplied time')
