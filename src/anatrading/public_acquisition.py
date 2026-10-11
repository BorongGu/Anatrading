"""Bounded explicit public-data runs with durable send reservations.

The existing Store owns the root lock throughout a run. Captures are immutable
source evidence; journals describe acquisition only and never grant coverage.
"""
from contextlib import ExitStack
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import uuid

from .formats import decode
from .models import DecodeError, NonMarketPayload, VERSIONS
from .public_market import (CAPTURE_VERSION, MAX_CAPTURE_BYTES, build_capture, build_request, canonical_json,
                            capture_rows, decoder_identity, preflight_capture, validate_capture, validate_request)
from .public_http_worker import _SAFE_CODES as _TRANSPORT_ERRORS
from .store import EvidenceStore, StoreError, _identity


_PLAN_VERSION = 'public-market-plan-v1'
_JOURNAL_VERSION = 'public-market-journal-v1'
_RESERVATION_VERSION = 'public-market-reservation-v1'
_MAX_ATTEMPTS = 10
_COMMAND_SECONDS = 180
_ATTEMPT_SECONDS = 15
_SEND_INTERVAL = 1
_MAX_DOCUMENT = 1024 * 1024
_STATES = {'pending', 'requested', 'captured', 'committed', 'empty_result', 'failed_transient',
           'failed_terminal', 'blocked', 'cancelled', 'interrupted'}
_STOP_STATES = {'failed_terminal', 'blocked', 'cancelled'}
_FORMAT = {'tencent': 'tencent-daily-capture-v1', 'sina': 'sina-minute-capture-v1'}
_DIAGNOSTICS = {'actual_range', 'requested_range', 'before_start_count', 'in_request_count',
                'after_end_count', 'request_range_mismatch', 'count_saturated', 'truncated_possible',
                'window_kind', 'row_count', 'future_label_count', 'observation_reference_utc',
                'label_timezone_assumption', 'target_start_not_observed', 'revision'}
_TRANSIENT = {'transport_timeout', 'transport_network_error', 'transport_truncated', 'transport_http_transient'}
_RUN_ERRORS = _TRANSPORT_ERRORS | {
    'source_blocked', 'budget_exhausted', 'process_cancelled', 'process_interrupted', 'acquisition_deadline',
    'commit_outcome_unavailable', 'import_not_committed', 'storage_io_error', 'database_error', 'internal_error',
    'invalid_public_capture', 'non_market_payload', 'public_source_error', 'conflicting_public_lengths',
    'duplicate_public_header', 'invalid_public_base64', 'invalid_public_content_type', 'invalid_public_count',
    'invalid_public_hash', 'invalid_public_headers', 'invalid_public_json', 'invalid_public_length',
    'invalid_public_period', 'invalid_public_request', 'invalid_public_request_date', 'invalid_public_request_range',
    'invalid_public_response', 'invalid_public_rows', 'invalid_public_source', 'invalid_public_source_label',
    'invalid_public_symbol', 'invalid_public_transfer_encoding', 'noncanonical_public_capture',
    'public_body_hash_mismatch', 'public_body_length_mismatch', 'public_body_limit', 'public_capture_limit',
    'public_header_hash_mismatch', 'public_json_depth', 'public_request_hash_mismatch', 'public_request_mismatch',
    'public_row_limit', 'public_source_after_end', 'public_source_mismatch', 'unsupported_format',
    'unsupported_public_content_encoding', 'empty_public_market_result', 'unverified_normalization',
}


class PublicAcquisitionError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _fail(code):
    raise PublicAcquisitionError(code) from None


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _utc(now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None:
        _fail('invalid_acquisition_clock')
    return now.astimezone(timezone.utc).isoformat()


def _clock(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.utcoffset() != timedelta(0) or parsed.isoformat() != value:
            raise ValueError
        return parsed
    except (ValueError, TypeError):
        _fail('invalid_acquisition_clock')


def _document(raw, code):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError
            result[key] = value
        return result
    def forbidden(value):
        raise ValueError
    try:
        result = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                            parse_float=forbidden, parse_constant=forbidden)
        if type(result) is not dict or canonical_json(result) != raw:
            raise ValueError
        return result
    except (ValueError, UnicodeError, DecodeError, RecursionError):
        _fail(code)


class _Directory:
    """Descriptor-relative no-follow files; no unsafe platform fallback.

    A platform without directory descriptors/fsync cannot reserve durable sends
    under this contract and fails before networking. Windows native validation
    remains separate; this does not weaken the existing cross-platform Store.
    """
    def __init__(self, descriptor, path):
        self.fd, self.path = descriptor, Path(path)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        os.close(self.fd)

    @staticmethod
    def _name(name):
        if (type(name) is not str or not name or name in {'.', '..'}
                or '/' in name or '\\' in name or '\x00' in name):
            _fail('unsafe_path')

    @classmethod
    def root(cls, path, *, create=True):
        if (not hasattr(os, 'O_NOFOLLOW') or not hasattr(os, 'O_DIRECTORY')
                or os.open not in os.supports_dir_fd or os.rename not in os.supports_dir_fd):
            _fail('durability_unsupported')
        absolute = Path(os.path.abspath(path))
        if '..' in Path(path).parts:
            _fail('unsafe_path')
        current = cls(os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW), absolute.anchor)
        try:
            for part in absolute.parts[1:]:
                child = current.child(part, create=create)
                os.close(current.fd)
                current = child
            current.sync()
            return current
        except BaseException:
            os.close(current.fd)
            raise

    def sync(self):
        try:
            os.fsync(self.fd)
        except OSError:
            _fail('durability_unavailable')

    def child(self, name, create=False):
        self._name(name)
        try:
            if create:
                try:
                    os.mkdir(name, 0o700, dir_fd=self.fd)
                    self.sync()
                except FileExistsError:
                    pass
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.fd)
            return _Directory(fd, self.path / name)
        except OSError:
            _fail('unsafe_path')

    def names(self):
        return sorted(os.listdir(self.fd))

    def exists(self, name):
        self._name(name)
        try:
            info = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            _fail('unsafe_path')
        return True

    def read(self, name, limit):
        self._name(name)
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
        except FileNotFoundError:
            raise
        except OSError:
            _fail('unsafe_path')
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                _fail('unsafe_path')
            if info.st_size > limit:
                _fail('acquisition_file_limit')
            result = bytearray()
            while len(result) <= limit:
                chunk = os.read(fd, min(65536, limit + 1 - len(result)))
                if not chunk:
                    return bytes(result)
                result.extend(chunk)
            _fail('acquisition_file_limit')
        finally:
            os.close(fd)

    def publish(self, name, raw, *, immutable=False, checkpoint=None):
        self._name(name)
        if self.exists(name) and immutable:
            if self.read(name, max(len(raw), _MAX_DOCUMENT)) == raw:
                return
            _fail('acquisition_file_conflict')
        temporary = '.' + name + '.' + uuid.uuid4().hex + '.part'
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            view = memoryview(raw)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
        finally:
            os.close(fd)
        if checkpoint:
            checkpoint()
        if immutable:
            # link is a no-overwrite atomic publication; remove the private
            # temporary name before readers can observe a completed operation.
            os.link(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd, follow_symlinks=False)
            os.unlink(temporary, dir_fd=self.fd)
        else:
            os.replace(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
        self.sync()

    def adopt(self, temporary, name):
        self._name(temporary)
        self._name(name)
        os.link(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd, follow_symlinks=False)
        os.unlink(temporary, dir_fd=self.fd)
        self.sync()


def _plan(source, symbol, asset_type, period, start=None, end=None, count=None, *, run_id=None, reference=None):
    if asset_type != 'stock' or type(asset_type) is not str:
        _fail('explicit_stock_declaration_required')
    if type(source) is not str or source not in _FORMAT:
        _fail('invalid_public_source')
    reference = reference or _utc()
    frozen = _clock(reference)
    requests = []
    try:
        if source == 'tencent':
            if count is not None:
                _fail('invalid_public_options')
            if type(start) is not str or type(end) is not str:
                _fail('invalid_public_options')
            first, last = date.fromisoformat(start), date.fromisoformat(end)
            if first.isoformat() != start or last.isoformat() != end or first > last:
                _fail('invalid_public_request_range')
            if last > frozen.astimezone(timezone(timedelta(hours=8))).date():
                _fail('future_public_request_date')
            if (last - first).days + 1 > 31 * _MAX_ATTEMPTS:
                _fail('public_plan_block_limit')
            while first <= last:
                block_end = min(last, first + timedelta(days=30))
                requests.append(build_request(source, symbol, period, start=first.isoformat(),
                                              end=block_end.isoformat(), count=64))
                first = block_end + timedelta(days=1)
        else:
            if start is not None or end is not None or (count is not None and (type(count) is not int or not 1 <= count <= 240)):
                _fail('invalid_public_options')
            requests.append(build_request(source, symbol, period, count=10 if count is None else count))
    except (ValueError, DecodeError) as error:
        if isinstance(error, PublicAcquisitionError):
            raise
        _fail(getattr(error, 'code', 'invalid_public_options'))
    format_id = _FORMAT[source]
    interpretation = dict(instrument=symbol, venue=symbol[-2:], asset_type=asset_type)
    blocks = []
    for sequence, request in enumerate(requests, 1):
        block = dict(sequence=sequence, source=source, symbol=symbol, period=period, requested_adjustment='none',
                     request=request, request_sha256=_hash(canonical_json(request)), format_id=format_id,
                     interpretation=interpretation, decoder_identity=decoder_identity(format_id))
        block['block_id'] = f'{sequence:04d}-' + _hash(canonical_json(block))
        blocks.append(block)
    plan = dict(version=_PLAN_VERSION, run_id=run_id or uuid.uuid4().hex, observation_reference_utc=reference,
                label_timezone_assumption='Asia/Shanghai', request_policy='small-window-31d-64',
                maximum_attempts=_MAX_ATTEMPTS,
                parameters=dict(source=source, symbol=symbol, asset_type=asset_type, period=period,
                                start=start, end=end, count=count), blocks=blocks)
    plan['plan_sha256'] = _hash(canonical_json(plan))
    return plan


def _read_plan(directory, run_id):
    try:
        value = _document(directory.read('plan.json', _MAX_DOCUMENT), 'corrupt_plan')
        for block in value['blocks']:
            if block['decoder_identity'] != decoder_identity(block['format_id']):
                _fail('decoder_version_mismatch')
        expected = _plan(**value['parameters'], run_id=run_id, reference=value['observation_reference_utc'])
        if value != expected:
            _fail('plan_identity_mismatch')
        return value
    except (KeyError, TypeError, FileNotFoundError, DecodeError):
        _fail('corrupt_plan')


def _new_journal(plan):
    return dict(version=_JOURNAL_VERSION, run_id=plan['run_id'], plan_sha256=plan['plan_sha256'],
                attempts=[], blocks=[dict(block_id=b['block_id'], status='pending', error_code=None,
                                          latest_attempt=None) for b in plan['blocks']], events=[])


def _new_attempt(number, block):
    return dict(number=number, block_id=block['block_id'], status='requested', error_code=None,
                capture_sha256=None, store_attempt_id=None, raw_sha256=None, batch_id=None,
                snapshot_id=None, reused=False, diagnostics={}, retry_after=None, transport=None)


def _valid_hex(value, length):
    return type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is not None


def _safe_error(value):
    return value is None or type(value) is str and value in _RUN_ERRORS


def _safe_retry(value):
    if value is None or type(value) is int and 0 <= value <= 999999999:
        return True
    if type(value) is not str or re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value) is None:
        return False
    try:
        datetime.fromisoformat(value)
        return True
    except ValueError:
        return False


def _safe_diagnostics(value):
    if type(value) is not dict or set(value) - _DIAGNOSTICS:
        return False
    integer_keys = {'before_start_count', 'in_request_count', 'after_end_count', 'row_count', 'future_label_count'}
    bool_keys = {'request_range_mismatch', 'count_saturated', 'truncated_possible', 'target_start_not_observed'}
    for key, item in value.items():
        if key in integer_keys and (type(item) is not int or not 0 <= item <= 1970):
            return False
        if key in bool_keys and type(item) is not bool:
            return False
        if key in {'actual_range', 'requested_range'} and item is not None:
            if type(item) is not dict or set(item) != {'start', 'end'}:
                return False
            for label in item.values():
                if type(label) is not str or re.fullmatch(r'\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?', label) is None:
                    return False
                try:
                    datetime.fromisoformat(label)
                except ValueError:
                    return False
        if key == 'window_kind' and item != 'recent_window':
            return False
        if key == 'label_timezone_assumption' and item != 'Asia/Shanghai':
            return False
        if key == 'observation_reference_utc':
            _clock(item)
        if key == 'revision':
            if (type(item) is not dict or set(item) != {'previous_snapshot_id', 'changed_market_rows', 'added_labels',
                                                       'removed_labels', 'body_changed_without_market_rows'}
                    or not _valid_hex(item['previous_snapshot_id'], 64)
                    or any(type(item[n]) is not int or not 0 <= item[n] <= 3940
                           for n in ('changed_market_rows', 'added_labels', 'removed_labels'))
                    or type(item['body_changed_without_market_rows']) is not bool):
                return False
    return True


def _safe_transport(value):
    return value is None or (type(value) is dict and set(value) == {'status', 'byte_count', 'body_sha256', 'complete'}
                            and (value['status'] is None or type(value['status']) is int and 100 <= value['status'] <= 599)
                            and type(value['byte_count']) is int and 0 <= value['byte_count'] <= 1024*1024
                            and (value['body_sha256'] is None or _valid_hex(value['body_sha256'], 64))
                            and type(value['complete']) is bool)


def _read_journal(directory, plan):
    try:
        result = _document(directory.read('journal.json', _MAX_DOCUMENT), 'corrupt_journal')
        template = _new_journal(plan)
        if (set(result) != set(template) or any(result[key] != template[key] for key in ('version', 'run_id', 'plan_sha256'))
                or type(result['attempts']) is not list or len(result['attempts']) > _MAX_ATTEMPTS
                or type(result['blocks']) is not list or len(result['blocks']) != len(plan['blocks'])
                or type(result['events']) is not list or len(result['events']) > 100):
            _fail('corrupt_journal')
        ids = {b['block_id'] for b in plan['blocks']}
        for number, item in enumerate(result['attempts'], 1):
            if (type(item) is not dict or set(item) != set(_new_attempt(number, plan['blocks'][0]))
                    or type(item['number']) is not int or item['number'] != number or item['block_id'] not in ids
                    or item['status'] not in _STATES or type(item['reused']) is not bool
                    or not _safe_diagnostics(item['diagnostics']) or not _safe_error(item['error_code'])
                    or not _safe_retry(item['retry_after']) or not _safe_transport(item['transport'])):
                _fail('corrupt_journal')
            for key in ('capture_sha256', 'raw_sha256', 'batch_id', 'snapshot_id', 'store_attempt_id'):
                if item[key] is not None and not _valid_hex(item[key], 32 if key == 'store_attempt_id' else 64):
                    _fail('corrupt_journal')
            committed_fields = ('store_attempt_id', 'raw_sha256', 'batch_id', 'snapshot_id')
            if item['status'] == 'committed':
                if (item['capture_sha256'] is None or any(item[key] is None for key in committed_fields)
                        or item['raw_sha256'] != item['capture_sha256'] or item['error_code'] is not None):
                    _fail('corrupt_journal')
            elif any(item[key] is not None for key in committed_fields):
                _fail('corrupt_journal')
            if item['status'] in {'captured', 'empty_result'} and item['capture_sha256'] is None:
                _fail('corrupt_journal')
        for block, expected in zip(result['blocks'], template['blocks']):
            if (type(block) is not dict or set(block) != set(expected) or block['block_id'] != expected['block_id']
                    or block['status'] not in _STATES or not _safe_error(block['error_code']) or block['latest_attempt'] is not None
                    and (type(block['latest_attempt']) is not int or not 1 <= block['latest_attempt'] <= len(result['attempts']))):
                _fail('corrupt_journal')
            if block['latest_attempt'] is not None and result['attempts'][block['latest_attempt']-1]['block_id'] != block['block_id']:
                _fail('corrupt_journal')
            matching = [item for item in result['attempts'] if item['block_id'] == block['block_id']]
            if (matching[-1]['number'] if matching else None) != block['latest_attempt']:
                _fail('corrupt_journal')
            override = ((block['status'], block['error_code']) in {
                ('blocked', 'source_blocked'), ('cancelled', 'process_cancelled'),
                ('failed_transient', 'acquisition_deadline'), ('failed_terminal', 'budget_exhausted')})
            if matching:
                item = matching[-1]
                if ((block['status'], block['error_code']) != (item['status'], item['error_code'])
                        and not (override and item['status'] in {'failed_transient', 'interrupted'})):
                    _fail('corrupt_journal')
            elif (block['status'], block['error_code']) != ('pending', None) and not override:
                _fail('corrupt_journal')
            if block['error_code'] == 'budget_exhausted' and len(result['attempts']) != _MAX_ATTEMPTS:
                _fail('corrupt_journal')
        for event in result['events']:
            if (type(event) is not dict or set(event) != {'kind', 'attempt', 'at_utc'}
                    or event['kind'] not in {'recovered_reservation', 'recovered_capture', 'interrupted'}
                    or type(event['attempt']) is not int or not 1 <= event['attempt'] <= _MAX_ATTEMPTS):
                _fail('corrupt_journal')
            _clock(event['at_utc'])
        return result
    except (FileNotFoundError, KeyError, TypeError):
        _fail('corrupt_journal')


def _save(directory, journal):
    raw = canonical_json(journal)
    if len(raw) > _MAX_DOCUMENT:
        _fail('acquisition_file_limit')
    directory.publish('journal.json', raw)


def _state(journal, block_index, status, error=None, attempt=None):
    block = journal['blocks'][block_index]
    block.update(status=status, error_code=error)
    if attempt is not None:
        attempt.update(status=status, error_code=error)
        block['latest_attempt'] = attempt['number']


def _binding(raw, block):
    capture = preflight_capture(raw, block['format_id'])
    if capture.envelope['capture_version'] != CAPTURE_VERSION:
        _fail('legacy_capture_not_network_evidence')
    if (capture.envelope['request'] != block['request']
            or capture.envelope['request_sha256'] != block['request_sha256']
            or capture.source != block['source'] or capture.symbol != block['symbol'] or capture.period != block['period']):
        _fail('capture_request_mismatch')
    return capture


def _capture_at(directory, block):
    candidates = [name for name in directory.names() if name.startswith('.capture.json.') and name.endswith('.part')]
    if directory.exists('capture.json'):
        if candidates:
            _fail('ambiguous_capture')
        raw = directory.read('capture.json', MAX_CAPTURE_BYTES)
        _binding(raw, block)
        return raw, False
    if len(candidates) > 1:
        _fail('ambiguous_capture')
    if candidates:
        raw = directory.read(candidates[0], MAX_CAPTURE_BYTES)
        try:
            json.loads(raw.decode('utf-8'))
        except (ValueError, UnicodeError):
            # A partial file is retained, never presented as a capture. Its
            # reservation still consumes one send and a retry gets a new slot.
            prefix = b'{"body_base64":'
            if not (prefix.startswith(raw) or raw.startswith(prefix)):
                _fail('corrupt_capture')
            return None, False
        # Complete JSON with wrong binding/hash is corruption, never a retryable
        # interrupted write. Only a genuine incomplete prefix may be retained.
        _binding(raw, block)
        directory.adopt(candidates[0], 'capture.json')
        return raw, True
    return None, False


def _expected(raw, block):
    decoded = decode(raw, block['format_id'], block['interpretation'])
    manifest = dict(raw_sha256=_hash(raw), source_contract_id=_identity(decoded.contract),
                    contract=decoded.contract, interpretation=block['interpretation'], versions=dict(VERSIONS),
                    qualification='source_evidence_retrospective_only')
    if manifest['source_contract_id'] != block['decoder_identity']['source_contract_id']:
        _fail('decoder_version_mismatch')
    batch_id = _identity(manifest)
    snapshot_manifest = dict(batch_id=batch_id, versions=dict(VERSIONS), mode='retrospective')
    return decoded, manifest, batch_id, snapshot_manifest, _identity(snapshot_manifest)


def _receipt(store, attempt_id, raw, block, expected):
    decoded, manifest, batch_id, snapshot_manifest, snapshot_id = expected
    row = store.db.execute('SELECT status,format_id,interpretation_json,raw_sha256,batch_id,snapshot_id '
                           'FROM attempts WHERE attempt_id=?', [attempt_id]).fetchone()
    if (row is None or row[0] != 'committed' or row[1] != block['format_id']
            or json.loads(row[2]) != block['interpretation'] or row[3:] != (manifest['raw_sha256'], batch_id, snapshot_id)):
        _fail('commit_identity_mismatch')
    query = store.query(snapshot_id)
    saved = store.db.execute('SELECT batch_id,manifest_json FROM snapshots WHERE snapshot_id=?', [snapshot_id]).fetchone()
    if (query['manifest'] != manifest or query['batch_id'] != batch_id
            or query['counts']['batch_rows'] != len(decoded.rows)
            or saved is None or saved[0] != batch_id or json.loads(saved[1]) != snapshot_manifest):
        _fail('commit_identity_mismatch')
    return dict(store_attempt_id=attempt_id, raw_sha256=manifest['raw_sha256'], batch_id=batch_id, snapshot_id=snapshot_id)


def _diagnostics(capture, plan):
    metadata, rows = capture_rows(capture)
    result = {key: value for key, value in metadata.items() if key in _DIAGNOSTICS}
    result.update(row_count=len(rows), observation_reference_utc=plan['observation_reference_utc'],
                  label_timezone_assumption=plan['label_timezone_assumption'])
    if capture.source == 'sina':
        day = _clock(plan['observation_reference_utc']).astimezone(timezone(timedelta(hours=8))).date().isoformat()
        result['future_label_count'] = sum(row['day'][:10] > day for row in capture.payload)
    else:
        result['target_start_not_observed'] = (metadata['actual_range'] is None
                                               or metadata['actual_range']['start'] > capture.start)
    return result


def _revision(store, decoded, capture, block):
    found = store.db.execute(
        "SELECT a.snapshot_id FROM attempts a JOIN batches b USING(batch_id) "
        "WHERE a.status='committed' AND a.format_id=? AND a.interpretation_json=? "
        "AND json_extract_string(b.metadata_json,'$.request_sha256')=? "
        "ORDER BY a.started_at DESC,a.attempt_id DESC LIMIT 1",
        [block['format_id'], canonical_json(block['interpretation']).decode(), block['request_sha256']]).fetchone()
    if found is None:
        return None
    previous = store.query(found[0])
    def cells(rows):
        result = {}
        for ordinal, label, tokens in rows:
            key = label if label is not None else 'unlocated:' + str(ordinal)
            result.setdefault(key, []).append(tuple(tokens.get(field) for field in ('open', 'high', 'low', 'close', 'volume', 'amount')))
        return result
    old = cells((row['ordinal'], row['label'], row['tokens']) for row in previous['rows'] + previous['unlocated'])
    new = cells((row.ordinal, row.label, row.tokens) for row in decoded.rows)
    common = old.keys() & new.keys()
    changed = sum(max(len(old[key]), len(new[key])) for key in common if old[key] != new[key])
    return dict(previous_snapshot_id=found[0], changed_market_rows=changed,
                added_labels=len(new.keys()-old.keys()), removed_labels=len(old.keys()-new.keys()),
                body_changed_without_market_rows=(old == new and previous['metadata'].get('body_sha256') != capture.envelope['body_sha256']))


def _commit(store, directory, journal, index, attempt, raw, plan, checkpoint, cancelled):
    block = plan['blocks'][index]
    try:
        capture = validate_capture(raw, block['format_id'])
        diagnostics = _diagnostics(capture, plan)
        if 'revision' in attempt['diagnostics']:
            diagnostics['revision'] = attempt['diagnostics']['revision']
        if attempt['status'] in {'committed', 'empty_result'} and attempt['diagnostics'] != diagnostics:
            _fail('commit_identity_mismatch')
        attempt['diagnostics'] = diagnostics
        if not capture.payload:
            _state(journal, index, 'empty_result', attempt=attempt)
            _save(directory, journal)
            return
        expected = _expected(raw, block)
        if attempt['status'] != 'committed' and 'revision' not in diagnostics:
            revision = _revision(store, expected[0], capture, block)
            if revision is not None:
                diagnostics['revision'] = revision
            # Preserve the comparison reference before Store can commit. An ACK
            # loss must not silently compare against the just-imported result.
            _save(directory, journal)
        if attempt['store_attempt_id'] is not None:
            receipt = _receipt(store, attempt['store_attempt_id'], raw, block, expected)
            reused = attempt['reused']
        else:
            existing = store.db.execute('SELECT attempt_id FROM attempts WHERE status=\'committed\' '
                                        'AND format_id=? AND raw_sha256=? AND batch_id=? AND snapshot_id=? '
                                        'ORDER BY started_at DESC,attempt_id DESC',
                                        [block['format_id'], expected[1]['raw_sha256'], expected[2], expected[4]]).fetchone()
            if existing:
                receipt = _receipt(store, existing[0], raw, block, expected)
                reused = True
            else:
                result = store.import_bytes(raw, block['format_id'], filename=block['source'] + '-capture.json',
                                            interpretation=block['interpretation'], cancelled=cancelled)
                if result['status'] != 'committed':
                    status = 'cancelled' if result['status'] == 'cancelled' else 'failed_terminal'
                    _state(journal, index, status, result.get('error_code') or 'import_not_committed', attempt)
                    _save(directory, journal)
                    return
                receipt = _receipt(store, result['attempt_id'], raw, block, expected)
                reused = bool(result.get('reused'))
        checkpoint('store_commit_verified')
        attempt.update(**receipt, reused=reused)
        _state(journal, index, 'committed', attempt=attempt)
        _save(directory, journal)
    except StoreError as error:
        if error.code == 'import_outcome_unavailable':
            _state(journal, index, 'interrupted', 'commit_outcome_unavailable', attempt)
            _save(directory, journal)
            return
        raise
    except DecodeError as error:
        _state(journal, index, 'failed_terminal', error.code, attempt)
        _save(directory, journal)


def _recover(store, directory, attempts_dir, plan, journal, checkpoint, cancelled):
    names = attempts_dir.names()
    if names != [f'{number:06d}' for number in range(1, len(names)+1)] or len(names) > _MAX_ATTEMPTS:
        _fail('reservation_sequence_mismatch')
    if not len(journal['attempts']) <= len(names) <= len(journal['attempts']) + 1:
        _fail('reservation_journal_mismatch')
    blocks = {block['block_id']: (index, block) for index, block in enumerate(plan['blocks'])}
    for number, name in enumerate(names, 1):
        with attempts_dir.child(name) as slot:
            try:
                reservation = _document(slot.read('reservation.json', 16384), 'corrupt_reservation')
                if (set(reservation) != {'version', 'plan_sha256', 'block_id', 'request_sha256', 'attempt_number', 'reserved_at_utc'}
                        or reservation['version'] != _RESERVATION_VERSION
                        or reservation['plan_sha256'] != plan['plan_sha256']
                        or type(reservation['attempt_number']) is not int or reservation['attempt_number'] != number
                        or reservation['block_id'] not in blocks):
                    _fail('corrupt_reservation')
                _clock(reservation['reserved_at_utc'])
                index, block = blocks[reservation['block_id']]
                if reservation['request_sha256'] != block['request_sha256']:
                    _fail('reservation_request_mismatch')
            except (FileNotFoundError, KeyError, TypeError):
                _fail('corrupt_reservation')
            if number > len(journal['attempts']):
                journal['attempts'].append(_new_attempt(number, block))
                _state(journal, index, 'requested', attempt=journal['attempts'][-1])
                journal['events'].append(dict(kind='recovered_reservation', attempt=number, at_utc=_utc()))
                _save(directory, journal)
            attempt = journal['attempts'][number-1]
            if attempt['block_id'] != block['block_id']:
                _fail('reservation_journal_mismatch')
            try:
                raw, recovered = _capture_at(slot, block)
            except DecodeError:
                _fail('corrupt_capture')
            if raw is not None:
                digest = _hash(raw)
                if attempt['capture_sha256'] is not None and attempt['capture_sha256'] != digest:
                    _fail('corrupt_capture')
                if number != journal['blocks'][index]['latest_attempt']:
                    _fail('ambiguous_capture')
                attempt['capture_sha256'] = digest
                if attempt['status'] == 'empty_result' and validate_capture(raw, block['format_id']).payload:
                    _fail('commit_identity_mismatch')
                if recovered or attempt['status'] == 'requested':
                    journal['events'].append(dict(kind='recovered_capture', attempt=number, at_utc=_utc()))
                if attempt['status'] not in {'failed_terminal', 'blocked', 'cancelled'}:
                    if attempt['status'] not in {'committed', 'empty_result'}:
                        _state(journal, index, 'captured', attempt=attempt)
                        _save(directory, journal)
                    _commit(store, directory, journal, index, attempt, raw, plan, checkpoint, cancelled)
            elif attempt['capture_sha256'] is not None or attempt['status'] in {'captured', 'committed', 'empty_result'}:
                _fail('missing_capture')
            elif attempt['status'] == 'requested':
                _state(journal, index, 'interrupted', 'process_interrupted', attempt)
                journal['events'].append(dict(kind='interrupted', attempt=number, at_utc=_utc()))
                _save(directory, journal)


def _source_blocked(source_dir, source):
    name = source + '.json'
    temporary = [item for item in source_dir.names() if item.startswith('.'+name+'.') and item.endswith('.part')]
    if temporary:
        if len(temporary) != 1 or source_dir.exists(name):
            _fail('ambiguous_source_state')
        value = _document(source_dir.read(temporary[0], 16384), 'corrupt_source_state')
        if (set(value) != {'source', 'status', 'error_code', 'at_utc', 'retry_after'}
                or value['source'] != source or value['status'] != 'blocked'
                or not _safe_error(value['error_code']) or not _safe_retry(value['retry_after'])):
            _fail('corrupt_source_state')
        _clock(value['at_utc'])
        source_dir.adopt(temporary[0], name)
    if not source_dir.exists(name):
        return False
    value = _document(source_dir.read(name, 16384), 'corrupt_source_state')
    if (set(value) != {'source', 'status', 'error_code', 'at_utc', 'retry_after'}
            or value['source'] != source or value['status'] != 'blocked'
            or not _safe_error(value['error_code']) or not _safe_retry(value['retry_after'])):
        _fail('corrupt_source_state')
    _clock(value['at_utc'])
    return True


def _summary(store, plan, journal, elapsed):
    states = [block['status'] for block in journal['blocks']]
    stopped = next((b for b in journal['blocks'] if b['status'] not in {'committed', 'empty_result', 'pending'}), None)
    if all(state == 'committed' for state in states):
        status = 'committed'
    elif 'committed' in states:
        status = 'partial'
    elif all(state == 'empty_result' for state in states):
        status = 'empty_result'
    else:
        status = stopped['status'] if stopped else 'interrupted'
    allowed = bool(stopped and stopped['status'] in {'failed_transient', 'interrupted'}
                   and stopped['error_code'] != 'transport_shutdown_unconfirmed'
                   and len(journal['attempts']) < _MAX_ATTEMPTS)
    blocks = []
    for block, definition in zip(journal['blocks'], plan['blocks']):
        attempt = journal['attempts'][block['latest_attempt']-1] if block['latest_attempt'] else {}
        spec = validate_request(definition['request'], definition['source'])
        requested_range = dict(start=spec['start'], end=spec['end']) if spec['start'] is not None else None
        view = None
        if block['status'] == 'committed' and requested_range is not None:
            query = store.query(attempt['snapshot_id'])
            rows = [dict(ordinal=row['ordinal'], locator=row['locator'], label=row['label']) for row in query['rows']
                    if requested_range['start'] <= row['label'] <= requested_range['end']]
            source_count = query['counts']['selected_rows'] + query['counts']['unlocated_rows']
            view = dict(source_snapshot_id=query['snapshot_id'], source_query_id=query['query_id'],
                        source_raw_sha256=query['manifest']['raw_sha256'], view_start=spec['start'], view_end=spec['end'],
                        selection_rule='located_label_in_inclusive_requested_range', retained_rows=len(rows),
                        excluded_rows=source_count-len(rows), rows=rows, coverage='unverified')
        blocks.append({**block, **{key: attempt.get(key) for key in ('snapshot_id', 'store_attempt_id', 'raw_sha256',
                       'batch_id', 'capture_sha256', 'reused', 'diagnostics')}, 'attempt_id': attempt.get('store_attempt_id'),
                       'request': definition['request'], 'requested_range': requested_range, 'target_view': view})
    return dict(run_id=plan['run_id'], plan_sha256=plan['plan_sha256'], source=plan['parameters']['source'],
                requested_symbol=plan['parameters']['symbol'], period=plan['parameters']['period'], status=status,
                error_code=stopped['error_code'] if stopped else None, stop_reason=stopped['error_code'] if stopped else None,
                resume_allowed=allowed, attempts_used=len(journal['attempts']),
                attempts_remaining=_MAX_ATTEMPTS-len(journal['attempts']), blocks=blocks,
                quantity_normalization='unstandardized', coverage='unverified', elapsed_seconds=round(elapsed, 3))


def _execute(root, plan=None, run_id=None, *, transport=None, checkpoint=None, cancelled=None):
    from .public_transport import PublicTransportError, fetch
    transport, checkpoint, cancelled = transport or fetch, checkpoint or (lambda stage: None), cancelled or (lambda: False)
    started = time.monotonic()
    deadline = started + _COMMAND_SECONDS
    resuming = plan is None
    with ExitStack() as stack:
        safe_root = stack.enter_context(_Directory.root(root, create=not resuming))
        store = stack.enter_context(EvidenceStore(root, checkpoint=lambda stage: checkpoint('store.' + stage)))
        if safe_root.path != store.root or os.fstat(safe_root.fd).st_ino != os.stat(store.root).st_ino:
            _fail('unsafe_path')
        public = stack.enter_context(safe_root.child('public_acquisition', create=True))
        source_dir = stack.enter_context(public.child('sources', create=True))
        if resuming:
            directory = stack.enter_context(public.child(run_id))
            plan = _read_plan(directory, run_id)
            journal = _read_journal(directory, plan)
        else:
            directory = stack.enter_context(public.child(plan['run_id'], create=True))
            directory.publish('plan.json', canonical_json(plan), immutable=True)
            journal = _new_journal(plan)
            _save(directory, journal)
        attempts_dir = stack.enter_context(directory.child('attempts', create=True))
        _recover(store, directory, attempts_dir, plan, journal, checkpoint, cancelled)
        next_send = time.monotonic() + (_SEND_INTERVAL if resuming else 0)
        for index, block in enumerate(plan['blocks']):
            current = journal['blocks'][index]
            if current['status'] in {'committed', 'empty_result'}:
                continue
            if current['status'] in _STOP_STATES or current['error_code'] in {'commit_outcome_unavailable', 'transport_shutdown_unconfirmed'}:
                break
            if _source_blocked(source_dir, block['source']):
                _state(journal, index, 'blocked', 'source_blocked')
                _save(directory, journal)
                break
            if len(journal['attempts']) >= _MAX_ATTEMPTS:
                _state(journal, index, 'failed_terminal', 'budget_exhausted')
                _save(directory, journal)
                break
            while time.monotonic() < next_send and time.monotonic() < deadline and not cancelled():
                time.sleep(min(.05, max(0, next_send-time.monotonic())))
            if cancelled():
                _state(journal, index, 'cancelled', 'process_cancelled')
                _save(directory, journal)
                break
            if time.monotonic() >= deadline:
                _state(journal, index, 'failed_transient', 'acquisition_deadline')
                _save(directory, journal)
                break
            number = len(journal['attempts']) + 1
            with attempts_dir.child(f'{number:06d}', create=True) as slot:
                reservation = dict(version=_RESERVATION_VERSION, plan_sha256=plan['plan_sha256'], block_id=block['block_id'],
                                   request_sha256=block['request_sha256'], attempt_number=number, reserved_at_utc=_utc())
                slot.publish('reservation.json', canonical_json(reservation), immutable=True)
                checkpoint('reservation_published')
                attempt = _new_attempt(number, block)
                journal['attempts'].append(attempt)
                _state(journal, index, 'requested', attempt=attempt)
                _save(directory, journal)
                checkpoint('attempt_requested')
                try:
                    received = transport(block['request'], deadline=min(deadline, time.monotonic()+_ATTEMPT_SECONDS), cancelled=cancelled)
                    next_send = time.monotonic() + _SEND_INTERVAL
                    attempt['transport'] = dict(status=received['status'], byte_count=len(received['body']),
                                                body_sha256=_hash(received['body']), complete=True)
                    raw = build_capture(block['source'], block['request'], status=received['status'],
                                        response_url=received['response_url'], response_headers=received['response_headers'],
                                        body=received['body'])
                    _binding(raw, block)
                    slot.publish('capture.json', raw, immutable=True,
                                 checkpoint=lambda: checkpoint('capture_temporary'))
                    checkpoint('capture_published')
                    attempt['capture_sha256'] = _hash(raw)
                    _state(journal, index, 'captured', attempt=attempt)
                    _save(directory, journal)
                    checkpoint('capture_recorded')
                    _commit(store, directory, journal, index, attempt, raw, plan, checkpoint, cancelled)
                except PublicTransportError as error:
                    code = error.code
                    attempt['transport'] = dict(status=getattr(error, 'status', None), byte_count=getattr(error, 'byte_count', 0),
                                                body_sha256=getattr(error, 'body_sha256', None), complete=getattr(error, 'complete', False))
                    if getattr(error, 'status', None) in {401, 403, 429} or code in {'transport_http_blocked', 'transport_restricted'}:
                        status = 'blocked'
                        source_dir.publish(block['source']+'.json', canonical_json(dict(source=block['source'], status='blocked',
                                           error_code=code, at_utc=_utc(), retry_after=getattr(error, 'retry_after', None))), immutable=True,
                                           checkpoint=lambda: checkpoint('source_block_temporary'))
                        checkpoint('source_block_published')
                    elif code == 'transport_cancelled':
                        status = 'cancelled'
                    elif code in _TRANSIENT:
                        status = 'failed_transient'
                    else:
                        status = 'failed_terminal'
                    attempt['retry_after'] = getattr(error, 'retry_after', None)
                    _state(journal, index, status, code, attempt)
                    _save(directory, journal)
                except DecodeError as error:
                    _state(journal, index, 'failed_terminal', error.code, attempt)
                    _save(directory, journal)
            if journal['blocks'][index]['status'] not in {'committed', 'empty_result'}:
                break
        return _summary(store, plan, journal, time.monotonic()-started)


def acquire_public(root, *, source, symbol, asset_type, period, start=None, end=None, count=None,
                   _transport=None, _checkpoint=None, _cancelled=None, _now=None):
    plan = _plan(source, symbol, asset_type, period, start, end, count, reference=_utc(_now))
    return _execute(root, plan, transport=_transport, checkpoint=_checkpoint, cancelled=_cancelled)


def resume_public(root, run_id, *, _transport=None, _checkpoint=None, _cancelled=None):
    if not _valid_hex(run_id, 32):
        _fail('invalid_public_run_id')
    return _execute(root, run_id=run_id, transport=_transport, checkpoint=_checkpoint, cancelled=_cancelled)
