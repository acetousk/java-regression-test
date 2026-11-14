"""Phase 3, Change 13: retain exact evidence through verified lossless compression."""
import gzip
import hashlib
import json
from pathlib import Path


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def archive_file(path):
    path=Path(path)
    target=path.with_name(path.name+'.gz')
    temporary=target.with_name(target.name+'.tmp')
    original_hash=file_hash(path)
    original_size=path.stat().st_size
    try:
        with path.open('rb') as source,gzip.open(temporary,'wb',compresslevel=1) as compressed:
            while block:=source.read(1024*1024):compressed.write(block)
        with gzip.open(temporary,'rb') as decoded:
            decoded_hash=hashlib.file_digest(decoded,'sha256').hexdigest()
        if decoded_hash!=original_hash or file_hash(path)!=original_hash or path.stat().st_size!=original_size:
            raise ValueError('Evidence compression did not retain the exact original bytes')
        temporary.replace(target)
        info={'originalPath':path.name,'originalSize':original_size,'originalSha256':original_hash,
            'compressedPath':target.name,'compressedSize':target.stat().st_size,'compressedSha256':file_hash(target),
            'compression':'gzip','level':1,'decodedVerified':True}
        path.unlink()
        return info
    finally:
        temporary.unlink(missing_ok=True)


def read_archived(directory,metadata):
    path=Path(directory)/metadata['compressedPath']
    if file_hash(path)!=metadata['compressedSha256']:
        raise ValueError('Compressed evidence hash mismatch')
    data=gzip.decompress(path.read_bytes())
    if len(data)!=metadata['originalSize'] or hashlib.sha256(data).hexdigest()!=metadata['originalSha256']:
        raise ValueError('Decoded evidence hash mismatch')
    return data


def load_json_artifact(directory,name):
    directory=Path(directory)
    manifest=directory/'artifact-manifest.json'
    if not manifest.exists():return json.loads((directory/name).read_bytes())
    metadata=json.loads(manifest.read_text())[name]
    return json.loads(read_archived(directory,metadata))
