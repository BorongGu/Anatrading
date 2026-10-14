"""Synthetic-only announcement registration; real documents never enter git."""
import hashlib
import json
import shutil

import pytest

from anatrading.store import EvidenceStore, StoreError


@pytest.fixture(autouse=True)
def synthetic_disk_budget(monkeypatch):
    # /tmp may be a small tmpfs; capacity failures are exercised explicitly.
    from anatrading import announcement_evidence as module
    monkeypatch.setattr(module, 'MIN_FREE_BYTES', 0)


def sample(tmp_path):
    base = tmp_path / 'input'
    base.mkdir()
    pdf = b'%PDF-1.4\nsynthetic test only\n%%EOF\n'
    sha = hashlib.sha256(pdf).hexdigest()
    url = 'https://example.invalid/test.PDF'
    receipt = dict(status='received', http_status=200, requests=1, bytes=len(pdf), sha256=sha,
                   url=url, attempted_at='2026-10-14T12:00:00+00:00', finished_at='2026-10-14T12:00:01+00:00')
    fields = {key: dict(value=value, status='document_asserted', source_pages_1based=[1], source_anchor=key)
              for key, value in dict(security_code='301039', venue='SZSE', announcement_id='2026-027',
                                     document_date='2026-06-26').items()}
    fields['publication_timestamp'] = dict(value=None, status='unknown', source_pages_1based=[], source_anchor='unknown')
    event = dict(schema='private-corporate-action-extraction-v1', source=dict(file='source.pdf', sha256=sha,
                bytes=len(pdf), url=url, pages=1), fields=fields, qualification='input cannot grant qualification')
    paths = [base / name for name in ('source.pdf', 'receipt.json', 'event.json')]
    paths[0].write_bytes(pdf)
    paths[1].write_text(json.dumps(receipt))
    paths[2].write_text(json.dumps(event))
    return paths


def change(path, mutate):
    value = json.loads(path.read_text())
    mutate(value)
    path.write_text(json.dumps(value))


@pytest.mark.parametrize('mutation', ['hash', 'size', 'bool', 'time', 'page', 'identity', 'url', 'duplicate', 'large', 'directory', 'infinity'])
def test_reject_before_registration(tmp_path, mutation):
    paths = sample(tmp_path)
    if mutation == 'hash': change(paths[1], lambda v: v.update(sha256='0' * 64))
    if mutation == 'size': change(paths[2], lambda v: v['source'].update(bytes=1))
    if mutation == 'bool': change(paths[1], lambda v: v.update(requests=True))
    if mutation == 'time': change(paths[1], lambda v: v.update(finished_at='2026-10-14'))
    if mutation == 'page': change(paths[2], lambda v: v['fields']['venue'].update(source_pages_1based=[2]))
    if mutation == 'identity': change(paths[2], lambda v: v['fields']['security_code'].update(value='oops'))
    if mutation == 'url': change(paths[1], lambda v: v.update(url='https://user:secret@example.invalid/x'))
    if mutation == 'duplicate': paths[1].write_text('{"status":"received","status":"received"}')
    if mutation == 'large': paths[0].write_bytes(b'%PDF-' + b'x' * (256 * 1024))
    if mutation == 'directory': paths[0] = paths[0].parent
    if mutation == 'infinity': paths[2].write_text(paths[2].read_text()[:-1] + ',"extra":1e999}')
    with EvidenceStore(tmp_path / 'root') as store:
        with pytest.raises(StoreError): store.register_announcement(*paths)
        assert store.announcements() == []
        assert store.list_snapshots() == []
        assert store.db.execute('SELECT count(*) FROM raw_objects').fetchone()[0] == 0


def test_register_rename_reopen_backup_restore(tmp_path):
    paths = sample(tmp_path)
    root = tmp_path / 'root'
    with EvidenceStore(root) as store:
        first = store.register_announcement(*paths)
        assert first['status'] == 'committed' and not first['reused']
        renamed = [p.rename(p.with_name('renamed-' + p.name)) for p in paths]
        assert store.register_announcement(*renamed)['reused']
        result = store.announcement(first['evidence_id'])
        assert result['manifest']['qualification'] == 'pending'
        assert result['manifest']['fields']['publication_timestamp']['value'] is None
        assert len(store.announcements()) == 1
        for table in ('batches', 'snapshots', 'observations', 'attempts'):
            assert store.db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
        store.backup(tmp_path / 'backup')
    shutil.rmtree(renamed[0].parent)
    with EvidenceStore(root, read_only=True) as store:
        assert store.announcement(first['evidence_id']) == result
        with pytest.raises(StoreError, match='read_only'): store.register_announcement(*renamed)
    EvidenceStore.restore(tmp_path / 'backup', tmp_path / 'restored')
    with EvidenceStore(tmp_path / 'restored', read_only=True) as store:
        assert store.announcement(first['evidence_id']) == result


def test_multiple_versions_and_pagination(tmp_path, monkeypatch):
    from anatrading import announcement_evidence as module
    paths = sample(tmp_path)
    with EvidenceStore(tmp_path / 'root') as store:
        first = store.register_announcement(*paths)
        original = paths[2].read_bytes()
        change(paths[2], lambda v: v.update(notes=['revision']))
        second = store.register_announcement(*paths)
        assert first['evidence_id'] != second['evidence_id']
        assert store.register_announcement(*paths)['reused']
        change(paths[2], lambda v: v.update(notes=['third']))
        store.register_announcement(*paths)
        paths[2].write_bytes(original)
        monkeypatch.setattr(module, 'MIN_FREE_BYTES', 10**30)
        assert store.register_announcement(*paths)['reused']
        assert len(store.announcements()) == 3
        page = store.announcements(limit=1)
        assert len(page) == 1
        assert len(store.announcements(after_id=page[-1]['evidence_id'])) == 2


@pytest.mark.parametrize('damage', ['raw', 'manifest', 'id', 'version', 'half'])
def test_corruption(tmp_path, damage):
    paths = sample(tmp_path)
    with EvidenceStore(tmp_path / 'root') as store:
        result = store.register_announcement(*paths)
        if damage == 'raw': store._raw_path(hashlib.sha256(paths[0].read_bytes()).hexdigest()).write_bytes(b'bad')
        if damage == 'manifest':
            manifest = store.announcement(result['evidence_id'])['manifest']
            manifest['qualification'] = 'approved'
            store.db.execute('UPDATE announcement_evidence SET manifest_json=?', [json.dumps(manifest)])
        if damage == 'id': store.db.execute("UPDATE announcement_evidence SET evidence_id=?", ['0' * 64])
        if damage == 'version': store.db.execute("UPDATE app_meta SET value='2' WHERE key='announcement_evidence_schema'")
        if damage == 'half': store.db.execute("DELETE FROM app_meta WHERE key='announcement_evidence_schema'")
        with pytest.raises(StoreError): store.announcements()


@pytest.mark.parametrize('stage,committed', [('announcement_raw_published', False),
    ('announcement_transaction_open', False), ('announcement_before_commit', False), ('announcement_after_commit', True)])
def test_faults_and_retry(tmp_path, stage, committed):
    paths = sample(tmp_path)
    def checkpoint(point):
        if point == stage: raise RuntimeError('injected')
    with EvidenceStore(tmp_path / 'root', checkpoint=checkpoint) as store:
        if committed:
            assert store.register_announcement(*paths)['status'] == 'committed'
        else:
            with pytest.raises(RuntimeError, match='injected'): store.register_announcement(*paths)
        assert len(store.announcements()) == int(committed)
        store._checkpoint = lambda point: None
        assert store.register_announcement(*paths)['reused'] == committed


def test_source_change_before_commit_and_writer_lock(tmp_path):
    paths = sample(tmp_path)
    def checkpoint(point):
        if point == 'announcement_raw_published': paths[0].write_bytes(b'%PDF-changed')
    with EvidenceStore(tmp_path / 'root', checkpoint=checkpoint) as store:
        with pytest.raises(StoreError, match='data_directory_busy'): EvidenceStore(tmp_path / 'root')
        with pytest.raises(StoreError, match='source_changed'): store.register_announcement(*paths)
        assert store.announcements() == []


def test_unextended_read_and_cli(tmp_path, capsys):
    from anatrading.cli import main
    paths = sample(tmp_path)
    root = tmp_path / 'root'
    with EvidenceStore(root): pass
    with EvidenceStore(root, read_only=True) as store:
        assert store.announcements() == []
        assert 'announcement_evidence' not in {r[0] for r in store.db.execute('SHOW TABLES').fetchall()}
    assert main(['--root', str(root), 'register-announcement', '--pdf', str(paths[0]), '--receipt', str(paths[1]), '--extraction', str(paths[2])]) == 0
    identity = json.loads(capsys.readouterr().out)['evidence_id']
    assert main(['--root', str(root), 'announcement', identity]) == 0
    assert json.loads(capsys.readouterr().out)['manifest']['qualification'] == 'pending'
    assert main(['--root', str(root), 'announcements']) == 0
    assert len(json.loads(capsys.readouterr().out)) == 1


def test_space_reject_and_invalid_pages(tmp_path, monkeypatch):
    from anatrading import announcement_evidence as module
    paths = sample(tmp_path)
    with EvidenceStore(tmp_path / 'root') as store:
        monkeypatch.setattr(module, 'MIN_FREE_BYTES', 10**30)
        with pytest.raises(StoreError, match='insufficient_space'): store.register_announcement(*paths)
        assert store.announcements() == []
        for limit in (0, 101, True):
            with pytest.raises(StoreError, match='invalid_announcement_page'): store.announcements(limit=limit)
        with pytest.raises(StoreError, match='invalid_announcement_page'): store.announcements(after_id='bad')


def test_missing_raw_and_tampered_binding(tmp_path):
    paths = sample(tmp_path)
    with EvidenceStore(tmp_path / 'root') as store:
        result = store.register_announcement(*paths)
        sha = hashlib.sha256(paths[0].read_bytes()).hexdigest()
        store._raw_path(sha).unlink()
        with pytest.raises(OSError): store.announcement(result['evidence_id'])
        with pytest.raises(OSError): store.register_announcement(*paths)


def test_fifo_rejected_without_blocking(tmp_path):
    import os
    if not hasattr(os, 'mkfifo'): pytest.skip('POSIX FIFO only')
    from anatrading.announcement_evidence import bounded
    path = tmp_path / 'pipe'
    os.mkfifo(path)
    with pytest.raises(StoreError, match='input_limit'): bounded(path, 100)


def test_market_snapshot_identity_unchanged(tmp_path):
    from test_store import text_bytes, record
    with EvidenceStore(tmp_path / 'root') as store:
        market = store.import_bytes(text_bytes([record()]), 'tdx-public-text-v1')
        original = store.query(market['snapshot_id'])
        paths = sample(tmp_path)
        store.register_announcement(*paths)
        replay = store.import_bytes(text_bytes([record()]), 'tdx-public-text-v1')
        assert replay['snapshot_id'] == market['snapshot_id']
        assert store.query(market['snapshot_id']) == original


@pytest.mark.parametrize('origin', [r'C:\evidence', r'\\server\share\evidence', '/source/evidence'])
def test_source_path_hints_are_host_independent(tmp_path, origin):
    paths = sample(tmp_path)
    root = tmp_path / 'root'
    with EvidenceStore(root) as store:
        result = store.register_announcement(*paths)
        identity = result['evidence_id']
        value = store.announcement(identity)['manifest']
        value['original_paths'] = [origin + '/' + name for name in ('source.pdf', 'receipt.json', 'event.json')]
        store.db.execute('UPDATE announcement_evidence SET manifest_json=?', [json.dumps(value)])
        expected = store.announcement(identity)
        assert expected['manifest']['original_paths'] == value['original_paths']
        assert store.announcements() == [expected]
        assert store.register_announcement(*paths)['reused']
        store.backup(tmp_path / 'backup')
    shutil.rmtree(paths[0].parent)
    with EvidenceStore(root, read_only=True) as store:
        assert store.announcement(identity) == expected
    EvidenceStore.restore(tmp_path / 'backup', tmp_path / 'restored')
    with EvidenceStore(tmp_path / 'restored', read_only=True) as store:
        assert store.announcements() == [expected]


@pytest.mark.parametrize('hints', [None, [], ['', 'x', 'y'], [1, 'x', 'y'], ['x' * 4097, 'x', 'y']])
def test_invalid_source_path_hints_rejected(tmp_path, hints):
    paths = sample(tmp_path)
    with EvidenceStore(tmp_path / 'root') as store:
        identity = store.register_announcement(*paths)['evidence_id']
        value = store.announcement(identity)['manifest']
        value['original_paths'] = hints
        store.db.execute('UPDATE announcement_evidence SET manifest_json=?', [json.dumps(value)])
        with pytest.raises(StoreError, match='announcement_corrupt'):
            store.announcement(identity)


def test_long_origin_path_rejected_before_read_or_write(tmp_path, monkeypatch):
    from anatrading import announcement_evidence as module
    with EvidenceStore(tmp_path / 'root') as store:
        class LongOrigin:
            def resolve(self): return self
            def is_relative_to(self, root): return False
            def __str__(self): return 'C:/' + 'x' * 4096
        monkeypatch.setattr(module, 'Path', lambda path: LongOrigin())
        def unexpected_read(*args): raise AssertionError('input read before path validation')
        monkeypatch.setattr(module, 'bounded', unexpected_read)
        with pytest.raises(StoreError, match='invalid_announcement_evidence'):
            store.register_announcement('pdf', 'receipt', 'extraction')
        assert store.announcements() == []
        assert store.db.execute('SELECT count(*) FROM raw_objects').fetchone() == (0,)


@pytest.mark.parametrize('bad', ['null', 'empty_text', 'empty_list', 'empty_object', 'anchor', 'pages'])
def test_asserted_nonidentity_fields_need_value_and_evidence(tmp_path, bad):
    paths = sample(tmp_path)
    field = dict(value='3.50', status='document_asserted', source_pages_1based=[1], source_anchor='dividend paragraph')
    values = dict(null=None, empty_text='  ', empty_list=[], empty_object={})
    if bad in values: field['value'] = values[bad]
    if bad == 'anchor': field['source_anchor'] = ''
    if bad == 'pages': field['source_pages_1based'] = []
    change(paths[2], lambda v: v['fields'].update(dividend=field))
    with EvidenceStore(tmp_path / 'root') as store:
        with pytest.raises(StoreError, match='invalid_announcement_evidence'):
            store.register_announcement(*paths)
        assert store.announcements() == []
        assert store.db.execute('SELECT count(*) FROM raw_objects').fetchone() == (0,)
