"""The explicit public CLI is bounded and never performs real vendor I/O here."""
import json

import pytest

from anatrading import cli, public_acquisition, public_transport
from test_cli import run_cli
from test_public_acquisition import response


@pytest.mark.parametrize('options', [
    ['--source', 'tencent', '--symbol', '601577.SH', '--period', '1d', '--start', '2025-01-01', '--end', '2025-01-02'],
    ['--source', 'tencent', '--symbol', '601577.SH', '--asset-type', 'stock', '--period', '1m', '--start', '2025-01-01', '--end', '2025-01-02'],
    ['--source', 'tencent', '--symbol', '601577.SH', '--asset-type', 'stock', '--period', '1d', '--start', '2025-01-01', '--end', '2025-01-02', '--count', '64'],
    ['--source', 'sina', '--symbol', '601577.SH', '--asset-type', 'stock', '--period', '1m', '--count', '241'],
    ['--source', 'sina', '--symbol', '601577.SH', '--asset-type', 'stock', '--period', '5m', '--start', '2025-01-01'],
])
def test_invalid_cli_combinations_do_not_create_root(tmp_path, options):
    root = tmp_path / 'unused'
    result = run_cli('--root', root, 'acquire-public', *options)
    assert result.returncode == 2 and 'Traceback' not in result.stdout + result.stderr
    assert not root.exists()


def test_public_cli_commit_query_export_and_resume(tmp_path, monkeypatch, capsys):
    root = tmp_path / 'store'
    monkeypatch.setattr(public_transport, 'fetch', response)
    monkeypatch.setattr(public_acquisition, '_SEND_INTERVAL', 0)
    arguments = ['--root', str(root), 'acquire-public', '--source', 'tencent', '--symbol', '601577.SH',
                 '--asset-type', 'stock', '--period', '1d', '--start', '2025-01-01', '--end', '2025-01-02']
    assert cli.main(arguments) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'committed' and result['coverage'] == 'unverified'
    assert result['transport_diagnostics'] == []
    sid = result['blocks'][0]['snapshot_id']
    assert cli.main(['--root', str(root), 'query', sid]) == 0
    query = json.loads(capsys.readouterr().out)
    assert query['rows'][0]['values']['close'] == '10.5'
    assert query['rows'][0]['values']['volume'] is None
    def forbidden(*args, **kwargs):
        raise AssertionError('resuming published source triggered new request')
    monkeypatch.setattr(public_transport, 'fetch', forbidden)
    assert cli.main(['--root', str(root), 'resume-public', result['run_id']]) == 0
    assert json.loads(capsys.readouterr().out)['blocks'][0]['snapshot_id'] == sid
    assert cli.main(['--root', str(root), 'export', sid, '--format', 'json']) == 0
    assert json.loads(capsys.readouterr().out)['query_id'] == query['query_id']


@pytest.mark.parametrize('status,expected', [('transport_timeout', 'failed_transient'),
                                            ('transport_http_blocked', 'blocked'),
                                            ('transport_headers_invalid', 'failed_terminal')])
def test_public_cli_stops_with_nonzero_safe_status(tmp_path, monkeypatch, capsys, status, expected):
    def failure(*args, **kwargs):
        raise public_transport.PublicTransportError(status)
    monkeypatch.setattr(public_transport, 'fetch', failure)
    arguments = ['--root', str(tmp_path / 'store'), 'acquire-public', '--source', 'tencent', '--symbol', '601577.SH',
                 '--asset-type', 'stock', '--period', '1d', '--start', '2025-01-01', '--end', '2025-01-02']
    assert cli.main(arguments) == 2
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == expected and result['error_code'] == status
    assert result['transport_diagnostics'] == [dict(run_id=result['run_id'], attempt_number=1,
        block_id=result['blocks'][0]['block_id'], code=status, phase='unknown')]
    legacy = {key: value for key, value in result.items() if key != 'transport_diagnostics'}
    assert legacy.get('transport_diagnostics', []) == []


@pytest.mark.parametrize('run_id', ['../escape', '/tmp/elsewhere', 'A'*32, 'a'*31])
def test_resume_cli_rejects_paths_and_noncanonical_ids(tmp_path, run_id):
    root = tmp_path / 'unused'
    result = run_cli('--root', root, 'resume-public', run_id)
    assert result.returncode == 2
    assert json.loads(result.stdout) == {'status': 'error', 'error_code': 'invalid_public_run_id'}
    assert not root.exists()
