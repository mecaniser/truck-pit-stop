"""Offline, fail-closed MongoDB Tools archive0.1 inventory. Never prints BSON values.

Primary format sources (MongoDB, Apache2.0; independently implemented here):
https://github.com/mongodb/mongo-tools/blob/master/common/archive/archive.go
https://github.com/mongodb/mongo-tools/blob/master/common/archive/parser.go
https://github.com/mongodb/mongo-tools/blob/master/common/archive/prelude.go
https://github.com/mongodb/mongo-tools/blob/master/common/archive/demultiplexer.go
https://github.com/mongodb/mongo-tools/blob/master/mongodump/metadata_dump.go
Header/body BSON blocks end in FFFFFFFF; namespace EOF verifies Go CRC64/ECMA.
Raw document bytes are never re-encoded. This is not a production consistency/
point-in-time claim: it inventories the exact immutable exported artifact.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys

MAGIC = b'\x6d\xe2\x99\x81'
END = b'\xff' * 4
MAX_BSON = 16 * 1024 * 1024
MAX_TOTAL = 2 * 1024 * 1024 * 1024
MAX_DOCS = 2_000_000
MASK = (1 << 64) - 1
CREDENTIAL = re.compile(r'(?:password|passwd|secret|access.?token|refresh.?token|api.?key|private.?key|client.?secret|authorization|credential)', re.I)
TOKEN_SCOPE = re.compile(r'(?:session|magic.?link|otp|token.?hash|pin.?hash)', re.I)


class Refused(ValueError):
    """Only fixed diagnostics, never source values/keys/namespace names."""


def require(condition, code):
    if not condition:
        raise Refused(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def ordered(value):
    if isinstance(value, dict):
        require(not any(re.fullmatch(r'[0-9]+', k) for k in value), 'metadata_numeric_key_requires_review')
        return {'$ordered': [[k, ordered(v)] for k, v in value.items()]}
    if isinstance(value, list):
        return [ordered(v) for v in value]
    return value


def fingerprints(metadata, source_namespace):
    require(isinstance(metadata, dict), 'metadata_object_required')
    require(set(metadata) <= {'options', 'indexes', 'uuid', 'collectionName', 'type'}
            and 'indexes' in metadata, 'metadata_fields_require_review')
    require(metadata.get('collectionName', source_namespace.split('.', 1)[1]) == source_namespace.split('.', 1)[1]
            and metadata.get('type', '') in ('', 'collection'), 'metadata_collection_binding')
    options = metadata.get('options', {})
    indexes = metadata['indexes']
    require(isinstance(options, dict) and isinstance(indexes, list), 'metadata_options_indexes_required')
    index_values = []
    names = set()
    for index in indexes:
        require(isinstance(index, dict) and isinstance(index.get('name'), str)
                and isinstance(index.get('key'), dict) and index['name'] not in names, 'index_metadata_refused')
        names.add(index['name'])
        normalized = dict(index)
        if 'ns' in normalized:
            require(normalized['ns'] == source_namespace, 'index_namespace_mismatch')
        # Outer spec field order and index list order are immaterial. All nested
        # field order, especially compound index key order, is retained exactly.
        index_values.append(sha(canonical({k: ordered(v) for k, v in sorted(normalized.items())})))
    return {'collection_options_sha256': sha(canonical(ordered(options))),
            'indexes_sha256': sha(canonical(sorted(index_values))), 'index_count': len(indexes)}


def no_duplicate_json(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate_json_field')
        result[key] = value
    return result


def json_metadata(text):
    require(isinstance(text, str) and bool(text), 'metadata_text_required')
    try:
        return json.loads(text, object_pairs_hook=no_duplicate_json,
                          parse_constant=lambda _: (_ for _ in ()).throw(Refused('nonfinite_metadata')))
    except (json.JSONDecodeError, UnicodeError):
        raise Refused('metadata_json_invalid') from None


# Go hash/crc64.ECMA uses reflected0xC96C5795D7870F42 with initial/final complement.
def crc_table():
    table = []
    for value in range(256):
        for _ in range(8):
            value = (value >> 1) ^ (0xC96C5795D7870F42 if value & 1 else 0)
        table.append(value)
    return table


CRC_TABLE = crc_table()


def crc64(raw, previous=0):
    value = previous ^ MASK
    for byte in raw:
        value = CRC_TABLE[(value ^ byte) & 255] ^ (value >> 8)
    return value ^ MASK


def bson(raw, *, decode=True, visitor=None, depth=0, path=(), array=False, types=None):
    """Validate all BSON1.1 types; decode control frames only. Documents stay raw.

    Body duplicate fields are validatable/preserved, never collapsed into dicts.
    Control-frame duplicates are refused. Deprecated BSON types are validated too.
    """
    require(depth <= 100 and 5 <= len(raw) <= MAX_BSON, 'bson_size_or_depth')
    require(struct.unpack_from('<i', raw)[0] == len(raw) and raw[-1] == 0, 'bson_envelope_invalid')
    pos, result, seen = 4, {}, set()

    def need(size):
        require(size >= 0 and pos + size <= len(raw) - 1, 'bson_value_truncated')

    def cstring():
        nonlocal pos
        end = raw.find(b'\0', pos, len(raw) - 1)
        require(end >= pos, 'bson_cstring_invalid')
        try:
            value = raw[pos:end].decode('utf8')
        except UnicodeError:
            raise Refused('bson_utf8_invalid') from None
        pos = end + 1
        return value

    def string():
        nonlocal pos
        need(4)
        size = struct.unpack_from('<i', raw, pos)[0]
        pos += 4
        need(size)
        require(size >= 1 and raw[pos + size - 1] == 0, 'bson_string_invalid')
        try:
            value = raw[pos:pos + size - 1].decode('utf8')
        except UnicodeError:
            raise Refused('bson_utf8_invalid') from None
        pos += size
        return value

    while pos < len(raw) - 1:
        kind = raw[pos]
        pos += 1
        key = cstring()
        require(not array or key == str(len(seen)), 'bson_array_keys_invalid')
        require(not decode or key not in seen, 'duplicate_control_field')
        seen.add(key)
        if types is not None:
            types[key] = kind
        location = path + (key,)
        if visitor:
            visitor(location)
        value = None
        fixed = {1: 8, 6: 0, 7: 12, 9: 8, 10: 0, 16: 4, 17: 8, 18: 8, 19: 16, 127: 0, 255: 0}
        if kind in fixed:
            size = fixed[kind]
            need(size)
            if decode and kind in (16, 18):
                value = struct.unpack_from('<i' if kind == 16 else '<q', raw, pos)[0]
            elif decode and kind == 1:
                value = struct.unpack_from('<d', raw, pos)[0]
            elif decode and size:
                value = raw[pos:pos + size]
            pos += size
        elif kind == 8:
            need(1)
            require(raw[pos] in (0, 1), 'bson_boolean_invalid')
            value = bool(raw[pos])
            pos += 1
        elif kind in (2, 13, 14):
            value = string()
        elif kind in (3, 4):
            need(4)
            size = struct.unpack_from('<i', raw, pos)[0]
            need(size)
            require(size >= 5, 'bson_nested_size_invalid')
            value = bson(raw[pos:pos + size], decode=decode, visitor=visitor,
                         depth=depth + 1, path=location + (('[]',) if kind == 4 else ()), array=kind == 4)
            pos += size
        elif kind == 5:
            need(5)
            size = struct.unpack_from('<i', raw, pos)[0]
            subtype = raw[pos + 4]
            pos += 5
            need(size)
            if subtype == 2:
                require(size >= 4 and struct.unpack_from('<i', raw, pos)[0] == size - 4, 'bson_binary_old_invalid')
            pos += size
        elif kind == 11:
            cstring()
            cstring()
        elif kind == 12:
            string()
            need(12)
            pos += 12
        elif kind == 15:
            need(4)
            start = pos
            size = struct.unpack_from('<i', raw, pos)[0]
            need(size)
            require(size >= 14, 'bson_code_scope_size_invalid')
            pos += 4
            string()
            need(4)
            scope_size = struct.unpack_from('<i', raw, pos)[0]
            need(scope_size)
            bson(raw[pos:pos + scope_size], decode=decode, visitor=visitor, depth=depth + 1, path=location)
            pos += scope_size
            require(pos == start + size, 'bson_code_scope_size_invalid')
        else:
            raise Refused('bson_type_unsupported')
        if decode:
            result[key] = value
    require(pos == len(raw) - 1, 'bson_trailing_bytes')
    return result if decode else None


class Stream:
    def __init__(self, stream):
        self.stream, self.total = stream, 0

    def read(self, size, *, eof=False):
        raw = self.stream.read(size)
        self.total += len(raw)
        require(self.total <= MAX_TOTAL, 'archive_resource_limit')
        if eof and not raw:
            return None
        require(len(raw) == size, 'archive_truncated')
        return raw

    def frame(self, *, eof=False):
        prefix = self.read(4, eof=eof)
        if prefix is None or prefix == END:
            return prefix
        length = struct.unpack('<i', prefix)[0]
        require(5 <= length <= MAX_BSON, 'archive_bson_length_invalid')
        return prefix + self.read(length - 4)


def namespace(document, database):
    require(document.get('db') == database and isinstance(document.get('collection'), str)
            and 0 < len(document['collection'].encode()) <= 255
            and not any(c in document['collection'] for c in ('\0', '\r', '\n')), 'archive_namespace_refused')
    return database + '.' + document['collection']


def document_fingerprint(counts):
    value = hashlib.sha256(b'raw-bson-multiset-v1\0')
    for raw_hash, count in sorted(counts.items()):
        value.update(raw_hash)
        value.update(struct.pack('>Q', count))
    return value.hexdigest()


def inventory_stream(stream, database='ParkRightDB', scan_keys=False):
    require(database in ('ParkRightDB', 'tph_local_test'), 'fixed_database_required')
    reader = Stream(stream)
    require(reader.read(4) == MAGIC, 'archive_magic_invalid')
    first = reader.frame()
    require(first not in (None, END), 'archive_header_required')
    header_types = {}
    header = bson(first, types=header_types)
    require(set(header) == {'version', 'concurrent_collections', 'server_version', 'tool_version'}
            and header['version'] == '0.1' and header_types['concurrent_collections'] == 16
            and type(header['concurrent_collections']) is int
            and 1 <= header['concurrent_collections'] <= 64
            and isinstance(header['server_version'], str) and isinstance(header['tool_version'], str), 'archive_header_refused')
    records, internals = {}, {}
    while True:
        raw = reader.frame()
        if raw == END:
            break
        require(raw is not None, 'archive_prelude_unfinished')
        metadata = bson(raw)
        require(set(metadata) <= {'db', 'collection', 'metadata', 'size', 'type'}
                and set(metadata) >= {'db', 'collection', 'metadata'}, 'collection_metadata_schema')
        ns = namespace(metadata, database)
        require(ns not in records and len(records) < 4096, 'duplicate_or_excess_namespace')
        require(metadata.get('type', '') in ('', 'collection'), 'special_collection_requires_review')
        require(type(metadata.get('size', 0)) is int and metadata.get('size', 0) >= 0, 'metadata_size_invalid')
        parsed = json_metadata(metadata['metadata'])
        records[ns] = {'count': 0, 'bson_bytes': 0, 'metadata_bson_sha256': sha(raw),
                       'metadata_json_sha256': sha(metadata['metadata'].encode()),
                       **fingerprints(parsed, ns), 'credential_key_findings': []}
        internals[ns] = {'status': 'new', 'crc': 0, 'hashes': Counter(), 'findings': Counter()}
    total_docs = 0
    while True:
        raw = reader.frame(eof=True)
        if raw is None:
            break
        require(raw != END, 'headerless_archive_block')
        block_types = {}
        block = bson(raw, types=block_types)
        require(set(block) == {'db', 'collection', 'EOF', 'CRC'}
                and type(block['EOF']) is bool and type(block['CRC']) is int
                and block_types['CRC'] == 18, 'namespace_header_schema')
        ns = namespace(block, database)
        require(ns in records, 'undeclared_namespace')
        state = internals[ns]
        require(state['status'] != 'closed', 'closed_namespace_reopened')
        if block['EOF']:
            require((block['CRC'] & MASK) == state['crc'], 'namespace_crc_mismatch')
            require(reader.frame() == END, 'eof_block_has_body')
            state['status'] = 'closed'
            continue
        require(block['CRC'] == 0, 'non_eof_crc_refused')
        state['status'] = 'open'
        def visitor(path):
            leaf = path[-1]
            if CREDENTIAL.search(leaf) or TOKEN_SCOPE.search(leaf):
                category = 'credential_key' if CREDENTIAL.search(leaf) else 'auth_capability_key'
                state['findings'][(category, sha(canonical(path)))] += 1
                require(len(state['findings']) <= 4096, 'credential_scan_resource_limit')
        while True:
            document = reader.frame()
            if document == END:
                break
            require(document is not None, 'namespace_block_unfinished')
            bson(document, decode=False, visitor=visitor if scan_keys else None)
            state['crc'] = crc64(document, state['crc'])
            state['hashes'][hashlib.sha256(document).digest()] += 1
            records[ns]['count'] += 1
            records[ns]['bson_bytes'] += len(document)
            total_docs += 1
            require(total_docs <= MAX_DOCS, 'archive_document_limit')
    require(all(s['status'] == 'closed' for s in internals.values()), 'archive_missing_namespace_eof')
    for ns, state in internals.items():
        records[ns]['documents_sha256'] = document_fingerprint(state['hashes'])
        records[ns]['archive_crc64'] = f'{state["crc"]:016x}'
        records[ns]['credential_key_findings'] = [dict(category=k[0], path_sha256=k[1], occurrences=v)
                                                for k, v in sorted(state['findings'].items())]
    return {'version': 1, 'method': 'raw-bson-multiset-v1', 'database': database,
            'archive_format': '0.1', 'namespace_crc_verified': True,
            'bson_structure_validated': True, 'gzip_crc_verified': False,
            'metadata_comparison': 'canonical_extended_json_preserving_nested_key_order',
            'document_count': total_docs, 'namespace_count': len(records),
            'namespaces': records, 'credential_scan': 'key_names_only_not_secret_content_detection' if scan_keys else 'not_run',
            'collection_uuid_equality': 'not_asserted_mongorestore_may_generate_new_uuids',
            'source_point_in_time_consistency': 'not_asserted'}


def same_file(a, b):
    return all(getattr(a, key) == getattr(b, key) for key in
               ('st_dev', 'st_ino', 'st_uid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def inventory_file(path, expected_sha, *, database='ParkRightDB', scan_keys=False):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and not path.is_symlink()
            and bool(re.fullmatch(r'[0-9a-f]{64}', expected_sha)), 'private_archive_path_or_hash_required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as raw:
        before = os.fstat(raw.fileno())
        require(stat.S_ISREG(before.st_mode) and stat.S_IMODE(before.st_mode) == 0o600
                and before.st_uid == os.getuid() and before.st_nlink == 1, 'private_archive_permissions')
        digest = hashlib.sha256()
        while True:
            part = raw.read(1024 * 1024)
            if not part:
                break
            digest.update(part)
        require(digest.hexdigest() == expected_sha, 'archive_sha_mismatch')
        raw.seek(0)
        try:
            with gzip.GzipFile(fileobj=raw, mode='rb') as decompressed:
                result = inventory_stream(decompressed, database=database, scan_keys=scan_keys)
                require(decompressed.read(1) == b'', 'archive_trailing_data')
        except (gzip.BadGzipFile, EOFError, OSError):
            raise Refused('archive_gzip_integrity_failed') from None
        require(same_file(before, os.fstat(raw.fileno())), 'archive_changed_during_read')
        result.update(source_archive_sha256=expected_sha, source_archive_bytes=before.st_size, gzip_crc_verified=True)
        return result


def compare(source, target):
    require(source.get('method') == target.get('method') == 'raw-bson-multiset-v1', 'inventory_method_mismatch')
    require(source.get('namespace_crc_verified') is True and source.get('bson_structure_validated') is True,
            'source_integrity_checks_required')
    expected = source['namespaces']
    actual = target['namespaces']
    require(set(expected) == set(actual), 'inventory_namespace_mismatch')
    require(source['namespace_count'] == target['namespace_count'] == len(expected)
            and source['document_count'] == target['document_count'] == sum(v['count'] for v in expected.values()),
            'inventory_total_mismatch')
    fields = ('count', 'bson_bytes', 'documents_sha256', 'index_count', 'indexes_sha256', 'collection_options_sha256')
    require(all(all(expected[ns][key] == actual[ns][key] for key in fields) for ns in expected), 'inventory_content_or_indexes_mismatch')
    return {'matches': True, 'document_count': source['document_count'], 'namespace_count': len(expected),
            'method': 'raw-bson-multiset-v1', 'collection_uuid_equality': 'not_asserted',
            'source_point_in_time_consistency': 'not_asserted'}


def read_private_receipt(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and not path.is_symlink(), 'private_receipt_path_required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and stat.S_IMODE(before.st_mode) == 0o600
                and before.st_uid == os.getuid() and before.st_nlink == 1 and before.st_size <= 64 * 1024 * 1024,
                'private_receipt_permissions')
        raw = source.read()
        require(same_file(before, os.fstat(source.fileno())), 'receipt_changed_during_read')
    return json.loads(raw, object_pairs_hook=no_duplicate_json)


def write_private(path, value):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and not path.is_symlink(), 'receipt_path_refused')
    parent = path.parent.stat()
    require(parent.st_uid == os.getuid() and not (parent.st_mode & 0o077), 'private_receipt_parent_required')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(canonical(value) + b'\n')
        output.flush()
        os.fsync(output.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive')
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--database', choices=('ParkRightDB', 'tph_local_test'), default='ParkRightDB')
    parser.add_argument('--scan-credential-keys', action='store_true')
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--compare')
    args = parser.parse_args()
    result = inventory_file(args.archive, args.expected_sha256, database=args.database, scan_keys=args.scan_credential_keys)
    if args.compare:
        # Comparison input itself is a private receipt, not a source of executable instructions.
        result['comparison'] = compare(result, read_private_receipt(args.compare))
    write_private(args.receipt, result)
    print(json.dumps({'inventory_created': True, 'namespaces': result['namespace_count'],
                      'documents': result['document_count'], 'receipt_sha256': sha(canonical(result) + b'\n')}))


if __name__ == '__main__':
    try:
        main()
    except Refused as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
    except Exception:
        print('archive_inventory_failed_values_withheld', file=sys.stderr)
        raise SystemExit(1)
