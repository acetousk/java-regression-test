"""Phase 3, Change 13: compression retains bytes and rejects damaged evidence."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from evidence_archive import archive_file, read_archived

class EvidenceArchiveTests(unittest.TestCase):
    def test_exact_binary_bytes_and_both_hashes_survive_compression(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'evidence.json'
            data=bytes(range(256))*1000+b'\x00\xff\r\n end '
            path.write_bytes(data)
            metadata=archive_file(path)
            self.assertFalse(path.exists())
            self.assertTrue(metadata['decodedVerified'])
            self.assertEqual(metadata['originalSha256'],hashlib.sha256(data).hexdigest())
            self.assertEqual(read_archived(directory,metadata),data)
            compressed=Path(directory)/metadata['compressedPath']
            compressed.write_bytes(compressed.read_bytes()+b'changed')
            with self.assertRaisesRegex(ValueError,'Compressed evidence hash mismatch'):
                read_archived(directory,metadata)

    def test_failed_verification_preserves_the_uncompressed_original(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'evidence.json'
            path.write_bytes(b'original')
            with patch('evidence_archive.file_hash',return_value='incorrect'):
                with self.assertRaises(ValueError):archive_file(path)
            self.assertEqual(path.read_bytes(),b'original')
