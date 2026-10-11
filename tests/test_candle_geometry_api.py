"""Geometry HTTP/CLI boundaries, using fresh synthetic temporary stores only."""
import asyncio
import hashlib
import json
import os

import pytest

from test_cli import run_cli
from test_workbench import ORIGIN, row, running, source, upload




def export_parameters(view, **selection):
    return {**selection, "query_id": view["query"]["query_id"],
            "geometry_id": view["geometry"]["geometry_id"]}


def test_geometry_query_and_export_keep_exact_two_scopes_and_old_source_exports(tmp_path):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            raw_bytes = source(row("0932", "2", "4", "1", "3"),
                               row("2500", "2", "4", "1", "3", volume="bad"),
                               row("0931", "2", "2", "2", "2"),
                               row("0931", "2", "1", "3", "2"), row("0933"))
            attempt = (await upload(client, auth, raw_bytes)).json()["attempt"]
            snapshot = attempt["snapshot_id"]
            raw_path = tmp_path / "root/raw" / attempt["raw_sha256"][:2] / attempt["raw_sha256"]
            selection = {"cutoff": "2021-02-26T09:32", "ordinal_start": 1, "ordinal_end": 4}
            response = await client.get("/api/query/" + snapshot, params=selection)
            assert response.status_code == 200
            view = response.json()
            query, geometry = view["query"], view["geometry"]
            assert set(view) == {"query", "geometry", "display", "navigation"}
            assert [entry["ordinal"] for entry in geometry["rows"]] == [3, 4, 1]
            assert [entry["ordinal"] for entry in geometry["unlocated"]] == [2]
            assert geometry["query_id"] == query["query_id"]
            assert geometry["source_qualification"] == query["manifest"]["qualification"]
            assert geometry["rows"][0]["ratio_reason"] == "zero_range"
            assert geometry["rows"][1]["reason"] == "invalid_ohlc"
            assert geometry["unlocated"][0]["status"] == "computed"
            assert query["unlocated"][0]["label"] is None
            assert geometry["rows"][2]["ratios"]["body"] == {
                "numerator": "1", "denominator": "3", "percent_display": "33.33"}
            before = {}
            for kind in ("json", "parquet"):
                exported = await client.post("/api/export/" + snapshot,
                    params={**selection, "format": kind, "query_id": query["query_id"]}, headers=auth)
                assert exported.status_code == 200
                before[kind] = exported.content
                if kind == "json": assert exported.json() == query
            exported = await client.post("/api/geometry-export/" + snapshot,
                params=export_parameters(view, **selection), headers=auth)
            assert exported.status_code == 200
            assert exported.json() == {"query": query, "geometry": geometry}
            assert exported.headers["x-query-id"] == query["query_id"]
            assert exported.headers["x-geometry-id"] == geometry["geometry_id"]
            assert exported.headers["x-content-sha256"] == hashlib.sha256(exported.content).hexdigest()
            assert geometry["geometry_id"] in exported.headers["content-disposition"]
            assert exported.headers["cache-control"] == "no-store"
            assert raw_path.read_bytes() == raw_bytes
            assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == attempt["raw_sha256"]
            for kind in ("json", "parquet"):
                repeated = await client.post("/api/export/" + snapshot,
                    params={**selection, "format": kind, "query_id": query["query_id"]}, headers=auth)
                assert repeated.content == before[kind]
            repeat = (await client.get("/api/query/" + snapshot, params=selection)).json()
            assert repeat == view
            earlier = (await client.get("/api/query/" + snapshot,
                params={**selection, "cutoff": "2021-02-26T09:31"})).json()
            assert earlier["geometry"]["rows"] == geometry["rows"][:2]
            assert earlier["geometry"]["unlocated"] == geometry["unlocated"]
            assert earlier["geometry"]["geometry_id"] != geometry["geometry_id"]
    asyncio.run(scenario())


@pytest.mark.parametrize("changed,expected", [("query_id", "query_id_mismatch"),
                                               ("geometry_id", "geometry_id_mismatch"),
                                               ("cutoff", "query_id_mismatch")])
def test_geometry_export_rejects_stale_identity_and_selection(tmp_path, changed, expected):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            snapshot = (await upload(client, auth, source(row(), row("0932")))).json()["attempt"]["snapshot_id"]
            view = (await client.get("/api/query/" + snapshot)).json()
            parameters = export_parameters(view)
            parameters[changed] = "2021-02-26T09:31" if changed == "cutoff" else "0" * 64
            result = await client.post("/api/geometry-export/" + snapshot, params=parameters, headers=auth)
            assert result.status_code == 409 and result.json() == {"error": expected}
    asyncio.run(scenario())


@pytest.mark.parametrize("bad", ["missing_query", "missing_geometry", "unknown", "duplicate", "body"])
def test_geometry_export_rejects_invalid_request(tmp_path, bad):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            snapshot = (await upload(client, auth, source(row()))).json()["attempt"]["snapshot_id"]
            view = (await client.get("/api/query/" + snapshot)).json()
            parameters = export_parameters(view)
            if bad == "missing_query": parameters.pop("query_id")
            if bad == "missing_geometry": parameters.pop("geometry_id")
            if bad == "unknown": parameters["sql"] = "forbidden"
            if bad == "duplicate": parameters["geometry_id"] = [parameters["geometry_id"], parameters["geometry_id"]]
            response = await client.post("/api/geometry-export/" + snapshot, params=parameters,
                headers=auth, content=b"payload" if bad == "body" else b"")
            assert response.status_code == 400 and response.json() == {"error": "invalid_request"}
    asyncio.run(scenario())


@pytest.mark.parametrize("bad", ["host", "origin", "missing_origin", "token"])
def test_geometry_export_inherits_local_auth_boundary(tmp_path, bad):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            snapshot = (await upload(client, auth, source(row()))).json()["attempt"]["snapshot_id"]
            view = (await client.get("/api/query/" + snapshot)).json()
            headers = dict(auth)
            if bad == "host": headers["Host"] = "evil.test"
            if bad == "origin": headers["Origin"] = "http://evil.test"
            if bad == "missing_origin": headers.pop("Origin")
            if bad == "token": headers["X-Anatrading-Token"] = "invalid"
            response = await client.post("/api/geometry-export/" + snapshot,
                params=export_parameters(view), headers=headers)
            assert response.status_code == 403
    asyncio.run(scenario())


def test_geometry_export_rechecks_raw_hash(tmp_path):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            attempt = (await upload(client, auth, source(row()))).json()["attempt"]
            snapshot = attempt["snapshot_id"]
            view = (await client.get("/api/query/" + snapshot)).json()
            raw_path = tmp_path / "root/raw" / attempt["raw_sha256"][:2] / attempt["raw_sha256"]
            raw_path.write_bytes(b"changed")
            response = await client.post("/api/geometry-export/" + snapshot,
                params=export_parameters(view), headers=auth)
            assert response.status_code == 409 and response.json() == {"error": "raw_object_corrupt"}
    asyncio.run(scenario())


def test_geometry_survives_plot_precision_limit_and_quantity_diagnostics(tmp_path):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            snapshot = (await upload(client, auth, source(
                row("0931", "9007199254740992", "9007199254740994", "9007199254740992", "9007199254740993"),
                row("0932", "2", "4", "1", "3", volume="bad", amount="-1"),
                row("0933", "", "4", "1", "3")))).json()["attempt"]["snapshot_id"]
            view = (await client.get("/api/query/" + snapshot)).json()
            assert view["display"][0]["precision_lost"] is True
            geometry = view["geometry"]["rows"]
            assert geometry[0]["status"] == "computed" and geometry[0]["direction"] == "up"
            assert geometry[0]["range"] == "2" and geometry[0]["body"] == "1"
            assert geometry[0]["ratios"]["body"] == {"numerator": "1", "denominator": "2", "percent_display": "50.00"}
            assert geometry[1]["status"] == "computed"
            assert view["query"]["rows"][1]["values"]["volume"] is None
            assert view["query"]["rows"][1]["values"]["amount"] == "-1"
            assert geometry[2]["reason"] == "missing_ohlc"
            empty = (await client.get("/api/query/" + snapshot,
                params={"cutoff": "2020-01-01T00:00"})).json()
            assert empty["geometry"]["rows"] == [] and empty["geometry"]["unlocated"] == []
    asyncio.run(scenario())


def test_geometry_export_includes_unlocated_rows_in_budget(tmp_path):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            snapshot = (await upload(client, auth, source(*([row("2500")] * 20001)))).json()["attempt"]["snapshot_id"]
            for selection in ({}, {"ordinal_start": 1}, {"ordinal_start": 1, "ordinal_end": 20001}):
                response = await client.post("/api/geometry-export/" + snapshot,
                    params={**selection, "query_id": "0" * 64, "geometry_id": "0" * 64}, headers=auth)
                assert response.status_code == 400 and response.json() == {"error": "query_row_limit"}
            selection = {"ordinal_start": 1, "ordinal_end": 2, "cutoff": "2020-01-01T00:00"}
            view = (await client.get("/api/query/" + snapshot, params=selection)).json()
            assert view["geometry"]["rows"] == []
            assert [entry["ordinal"] for entry in view["geometry"]["unlocated"]] == [1, 2]
            exported = await client.post("/api/geometry-export/" + snapshot,
                params=export_parameters(view, **selection), headers=auth)
            assert exported.status_code == 200 and exported.json()["geometry"] == view["geometry"]
    asyncio.run(scenario())


def test_cli_geometry_exact_selection_and_version_identity(tmp_path):
    path = tmp_path / "synthetic.txt"
    path.write_bytes(source(row("0931", "2", "4", "1", "3"),
                            row("0932", "3", "4", "1", "2"), row("2500")))
    root = tmp_path / "root"
    imported = run_cli("--root", root, "import", path, "--format", "tdx-public-text-v1")
    assert imported.returncode == 0, imported.stderr
    snapshot = json.loads(imported.stdout)["snapshot_id"]
    selection = ("--cutoff", "2021-02-26T09:31", "--ordinal-start", 1, "--ordinal-end", 3)
    original = run_cli("--root", root, "query", snapshot, *selection)
    result = run_cli("--root", root, "candle-geometry", snapshot, *selection)
    assert result.returncode == 0 and not result.stderr
    envelope = json.loads(result.stdout)
    assert set(envelope) == {"query", "geometry"}
    assert envelope["query"] == json.loads(original.stdout)
    assert [entry["ordinal"] for entry in envelope["geometry"]["rows"]] == [1]
    assert [entry["ordinal"] for entry in envelope["geometry"]["unlocated"]] == [3]
    assert envelope["geometry"]["rows"][0]["ratios"]["body"] == {
        "numerator": "1", "denominator": "3", "percent_display": "33.33"}
    repeated = run_cli("--root", root, "candle-geometry", snapshot, *selection)
    assert repeated.stdout == result.stdout
    later = run_cli("--root", root, "candle-geometry", snapshot, "--cutoff", "2021-02-26T09:32")
    assert later.returncode == 0
    later_envelope = json.loads(later.stdout)
    assert later_envelope["geometry"]["rows"][0] == envelope["geometry"]["rows"][0]
    assert later_envelope["geometry"]["geometry_id"] != envelope["geometry"]["geometry_id"]
    reinterpreted = run_cli("--root", root, "import", path, "--format", "tdx-public-text-v1", "--instrument", "OTHER")
    assert reinterpreted.returncode == 0
    other_snapshot = json.loads(reinterpreted.stdout)["snapshot_id"]
    assert other_snapshot != snapshot
    other = run_cli("--root", root, "candle-geometry", other_snapshot, *selection)
    assert other.returncode == 0
    assert json.loads(other.stdout)["geometry"]["geometry_id"] != envelope["geometry"]["geometry_id"]


def test_cli_geometry_unknown_snapshot_has_typed_error(tmp_path):
    result = run_cli("--root", tmp_path / "root", "candle-geometry", "0" * 64)
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"status": "error", "error_code": "snapshot_not_found"}
    assert "Traceback" not in result.stdout + result.stderr
