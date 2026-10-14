"""Bounded local registration of document evidence, never economic qualification."""
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
from urllib.parse import urlsplit

from .store import StoreError, _identity, _json, _utcnow

LIMITS = (256 * 1024, 16 * 1024, 64 * 1024)
MIN_FREE_BYTES = 8 * 1024**3
WRITE_RESERVE = 16 * 1024**2
CONTRACT = 'announcement-evidence-v1'
FEATURE = 'announcement_evidence_schema'
COLUMNS = {'evidence_id': 'VARCHAR', 'pdf_sha256': 'VARCHAR', 'receipt_sha256': 'VARCHAR',
           'extraction_sha256': 'VARCHAR', 'manifest_json': 'VARCHAR', 'registered_at': 'VARCHAR'}


def fail(code='invalid_announcement_evidence'):
    raise StoreError(code)


def bounded(path, limit):
    path = Path(path)
    # Nonblocking open prevents a path replaced by a FIFO from hanging the reader.
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0))
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode):
        os.close(fd)
        fail('announcement_input_limit')
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            fail('announcement_input_limit')
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        if len(raw) > limit or len(raw) != before.st_size or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            fail('announcement_source_changed')
    return raw


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def obj(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: fail()
            result[key] = value
        return result
    def constant(value): fail()
    # This extraction contract uses exact strings for non-integer quantities.
    def number(value): fail()
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant, parse_float=number)
    except (UnicodeError, ValueError, RecursionError):
        fail()
    if type(value) is not dict: fail()
    return value


def text(value, maximum=4096):
    return type(value) is str and bool(value.strip()) and len(value) <= maximum


def valid_origin_paths(paths):
    return type(paths) is list and len(paths) == 3 and all(text(path) for path in paths)


def asserted_value(value):
    if value is None: return False
    if type(value) is str: return bool(value.strip())
    if type(value) in (list, dict): return bool(value)
    return type(value) in (int, bool)


def timestamp(value):
    try:
        result = datetime.fromisoformat(value)
        if result.utcoffset() is None: fail()
        return result
    except (TypeError, ValueError): fail()


def manifest(raws):
    pdf, receipt_raw, extraction_raw = raws
    if not pdf.startswith(b'%PDF-'): fail()
    receipt, extraction = obj(receipt_raw), obj(extraction_raw)
    sha = digest(pdf)
    source, fields = extraction.get('source'), extraction.get('fields')
    if (receipt.get('status') != 'received' or type(receipt.get('http_status')) is not int
            or receipt['http_status'] != 200 or type(receipt.get('requests')) is not int
            or receipt['requests'] != 1 or type(receipt.get('bytes')) is not int
            or receipt['bytes'] != len(pdf) or receipt.get('sha256') != sha): fail()
    url = receipt.get('url')
    try:
        parsed = urlsplit(url) if text(url) else None
        if (parsed is None or parsed.scheme != 'https' or not parsed.hostname
                or parsed.username is not None or parsed.password is not None): fail()
    except ValueError: fail()
    if timestamp(receipt.get('attempted_at')) > timestamp(receipt.get('finished_at')): fail()
    if (extraction.get('schema') != 'private-corporate-action-extraction-v1' or type(source) is not dict
            or source.get('sha256') != sha or type(source.get('bytes')) is not int
            or source['bytes'] != len(pdf) or source.get('url') != url
            or not text(source.get('file'), 255) or type(source.get('pages')) is not int
            or not 1 <= source['pages'] <= 100 or type(fields) is not dict or not 1 <= len(fields) <= 128): fail()
    for name, field in fields.items():
        if (not text(name, 128) or type(field) is not dict or 'value' not in field
                or not text(field.get('status'), 128) or type(field.get('source_anchor')) is not str
                or type(field.get('source_pages_1based')) is not list
                or len(field['source_pages_1based']) > 100
                or any(type(page) is not int or not 1 <= page <= source['pages'] for page in field['source_pages_1based'])): fail()
        if field['status'] == 'document_asserted' and (not asserted_value(field['value'])
                or not text(field['source_anchor']) or not field['source_pages_1based']): fail()
    identity = {}
    patterns = dict(security_code=r'[0-9]{6}', venue=r'SZSE', announcement_id=r'[0-9]{4}-[0-9]{3,}',
                    document_date=r'[0-9]{4}-[0-9]{2}-[0-9]{2}')
    for name, pattern in patterns.items():
        field = fields.get(name, {})
        if (not text(field.get('value'), 128) or not re.fullmatch(pattern, field['value'])
                or field.get('status') != 'document_asserted' or not field.get('source_pages_1based')
                or not text(field.get('source_anchor'))): fail()
        identity[name] = field['value']
    try: date.fromisoformat(identity['document_date'])
    except ValueError: fail()
    hashes = [digest(raw) for raw in raws]
    binding = dict(contract=CONTRACT, pdf_sha256=hashes[0], receipt_sha256=hashes[1], extraction_sha256=hashes[2])
    return dict(**binding, byte_lengths=[len(raw) for raw in raws], source_url=url,
                attempted_at=receipt['attempted_at'], finished_at=receipt['finished_at'],
                identity=dict(values=identity, status='document_asserted'),
                extraction_schema=extraction['schema'], source=source, fields=fields,
                qualification='pending', evidence_kind='source_document_evidence_only',
                limitations=['official_source_authenticity_not_certified', 'historical_known_at_not_certified',
                             'revision_status_not_certified', 'event_history_not_complete',
                             'actual_payment_not_verified', 'not_economic_input'])


def evidence_id(value):
    return _identity({key: value[key] for key in ('contract', 'pdf_sha256', 'receipt_sha256', 'extraction_sha256')})


def require_known_outcome(store):
    if getattr(store, '_announcement_outcome_unknown', False):
        fail('announcement_outcome_unavailable')


def schema(store):
    require_known_outcome(store)
    tables = {row[0] for row in store.db.execute('SHOW TABLES').fetchall()}
    version = store.db.execute('SELECT value FROM app_meta WHERE key=?', [FEATURE]).fetchone()
    present = 'announcement_evidence' in tables
    if not present and version is None: return False
    if not present or version != ('1',): fail('unsupported_announcement_schema')
    columns = dict(store.db.execute("SELECT column_name,data_type FROM information_schema.columns WHERE table_catalog=current_database() AND table_schema='main' AND table_name='announcement_evidence'").fetchall())
    if columns != COLUMNS: fail('unsupported_announcement_schema')
    return True


def initialize(store):
    store.db.execute('''CREATE TABLE announcement_evidence (
        evidence_id VARCHAR PRIMARY KEY, pdf_sha256 VARCHAR NOT NULL REFERENCES raw_objects(sha),
        receipt_sha256 VARCHAR NOT NULL REFERENCES raw_objects(sha),
        extraction_sha256 VARCHAR NOT NULL REFERENCES raw_objects(sha),
        manifest_json VARCHAR NOT NULL, registered_at VARCHAR NOT NULL)''')
    store.db.execute('INSERT INTO app_meta VALUES (?,?)', [FEATURE, '1'])


def read(store, identity):
    if type(identity) is not str or not re.fullmatch('[0-9a-f]{64}', identity): fail('invalid_announcement_id')
    if not schema(store): fail('announcement_not_found')
    row = store.db.execute('SELECT pdf_sha256,receipt_sha256,extraction_sha256,manifest_json,registered_at FROM announcement_evidence WHERE evidence_id=?', [identity]).fetchone()
    if row is None: fail('announcement_not_found')
    raws = []
    for sha, limit in zip(row[:3], LIMITS):
        length = store.db.execute('SELECT byte_length FROM raw_objects WHERE sha=?', [sha]).fetchone()
        if length is None or not 0 < length[0] <= limit: fail('announcement_corrupt')
        raw = bounded(store._raw_path(sha), limit)
        if len(raw) != length[0] or digest(raw) != sha: fail('announcement_corrupt')
        raws.append(raw)
    saved = obj(row[3].encode('utf-8'))
    paths = saved.pop('original_paths', None)
    # Origin-host path syntax is provenance only; managed hashes locate originals.
    if not valid_origin_paths(paths): fail('announcement_corrupt')
    expected = manifest(raws)
    if saved != expected or evidence_id(expected) != identity: fail('announcement_corrupt')
    timestamp(row[4])
    return dict(evidence_id=identity, registered_at=row[4], manifest=dict(**expected, original_paths=paths))


def listing(store, after_id=None, limit=100):
    if type(limit) is not int or not 1 <= limit <= 100: fail('invalid_announcement_page')
    if after_id is not None and (type(after_id) is not str or not re.fullmatch('[0-9a-f]{64}', after_id)): fail('invalid_announcement_page')
    if not schema(store): return []
    ids = store.db.execute('SELECT evidence_id FROM announcement_evidence WHERE evidence_id>? ORDER BY evidence_id LIMIT ?', [after_id or '', limit]).fetchall()
    return [read(store, row[0]) for row in ids]


def register(store, paths):
    require_known_outcome(store)
    store._require_writable()
    paths = [Path(path).resolve() for path in paths]
    origin_paths = [str(path) for path in paths]
    if not valid_origin_paths(origin_paths): fail()
    if any(path.is_relative_to(store.root) for path in paths): fail('announcement_input_inside_store')
    raws = [bounded(path, limit) for path, limit in zip(paths, LIMITS)]
    value = manifest(raws)
    identity = evidence_id(value)
    present = schema(store)
    if present and store.db.execute('SELECT 1 FROM announcement_evidence WHERE evidence_id=?', [identity]).fetchone():
        read(store, identity)
        return dict(status='committed', evidence_id=identity, reused=True)
    if shutil.disk_usage(store.root).free < MIN_FREE_BYTES + sum(map(len, raws)) + WRITE_RESERVE:
        fail('announcement_insufficient_space')
    hashes = [digest(raw) for raw in raws]
    in_transaction = False
    committed = False
    try:
        for raw, sha in zip(raws, hashes):
            store._write_raw(raw, sha)
            store._verify_raw(sha, len(raw))
        store._checkpoint('announcement_raw_published')
        if any(digest(bounded(path, limit)) != sha for path, limit, sha in zip(paths, LIMITS, hashes)):
            fail('announcement_source_changed')
        store.db.execute('BEGIN TRANSACTION')
        in_transaction = True
        store._checkpoint('announcement_transaction_open')
        if not present: initialize(store)
        for raw, sha in zip(raws, hashes):
            store.db.execute('INSERT INTO raw_objects VALUES (?,?) ON CONFLICT DO NOTHING', [sha, len(raw)])
            if store.db.execute('SELECT byte_length FROM raw_objects WHERE sha=?', [sha]).fetchone() != (len(raw),): fail('announcement_corrupt')
        value['original_paths'] = origin_paths
        store.db.execute('INSERT INTO announcement_evidence VALUES (?,?,?,?,?,?)', [identity, *hashes, _json(value), _utcnow()])
        store._checkpoint('announcement_before_commit')
        store.db.execute('COMMIT')
        in_transaction = False
        committed = True
        store._checkpoint('announcement_after_commit')
    except BaseException:
        if in_transaction:
            try: store.db.execute('ROLLBACK')
            except Exception:
                # A failed rollback leaves transaction visibility ambiguous.
                # Never infer durability from this connection's visible rows.
                store._announcement_outcome_unknown = True
                fail('announcement_outcome_unavailable')
        try:
            if schema(store) and store.db.execute('SELECT 1 FROM announcement_evidence WHERE evidence_id=?', [identity]).fetchone():
                read(store, identity)
                return dict(status='committed', evidence_id=identity, reused=False)
        except Exception:
            fail('announcement_outcome_unavailable')
        if committed: fail('announcement_outcome_unavailable')
        raise
    read(store, identity)
    return dict(status='committed', evidence_id=identity, reused=False)
