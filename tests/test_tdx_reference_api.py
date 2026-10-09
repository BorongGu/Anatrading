import asyncio
from pathlib import Path

import httpx

from anatrading import tdx_reference
from anatrading.workbench import create_app
from test_tdx_reference import response


def test_reference_api_archives_without_creating_ohlcv_snapshots(tmp_path, monkeypatch):
    raw = response(["19970901", "20260624"], types=["1", "1"], values=[["0", "0", "8", "0"], ["0.90", "0.00", "0.00", "0.00"]])
    monkeypatch.setattr(tdx_reference.acquisition, "_client_identity", lambda client: dict(pid=123))
    monkeypatch.setattr(tdx_reference.acquisition, "_http", lambda *a, **kw: (200, raw))
    async def scenario():
        app = create_app(tmp_path / "data")
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                config = (await client.get('/api/config')).json()
                headers = {'Origin': 'http://127.0.0.1:8765', 'X-Anatrading-Token': config['csrf_token']}
                path = '/api/read-tdx-reference'
                parameters = dict(kind='actions', target='600059.SH', start='2026-01-01', end='2026-10-08')
                result = await client.post(path, params=parameters, headers=headers)
                assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
                report = result.json()['reference']
                assert report['selected_count'] == 1 and report['before_start'] == 1
                assert Path(report['evidence_directory'], 'response.bin').read_bytes() == raw
                assert (await client.get('/api/snapshots')).json()['snapshots'] == []
                assert (await client.get('/api/attempts')).json()['attempts'] == []
                assert (await client.post(path, params=parameters, headers={**headers, 'X-Anatrading-Token':'wrong'})).status_code == 403
                assert (await client.post(path, params=parameters, headers=headers, content=b'unexpected')).status_code == 400
                assert (await client.post(path+'?kind=calendar&kind=actions&target=SH&start=2026-01-01&end=2026-10-08', headers=headers)).status_code == 400
                assert (await client.post(path, params={**parameters, 'kind':'calendar', 'target':'SZ'}, headers=headers)).status_code == 400
    asyncio.run(scenario())
