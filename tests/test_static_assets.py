"""Raw ASGI representation tests; synthetic files, no lifespan/Store/socket."""
import asyncio
import gzip
import hashlib
import json
from pathlib import Path
import threading

import pytest

from anatrading import static_assets as module
from anatrading.workbench import create_app

NAME = "assets/index-12345678.js"
BODY = b'const synthetic = "static bytes";\n' * 100


def digest(body):
    return hashlib.sha256(body).hexdigest()


@pytest.fixture
def built(tmp_path):
    root = tmp_path / "web"
    (root / "assets").mkdir(parents=True)
    (root / ".encoded/assets").mkdir(parents=True)
    (root / NAME).write_bytes(BODY)
    encoded = gzip.compress(BODY, mtime=0)
    (root / f".encoded/{NAME}.gz").write_bytes(encoded)
    manifest = {"schema_version": 1, "assets": [{
        "identity_path": NAME, "gzip_path": f".encoded/{NAME}.gz",
        "identity_sha256": digest(BODY), "gzip_sha256": digest(encoded),
        "identity_bytes": len(BODY), "gzip_bytes": len(encoded),
        "media_type": "text/javascript", "cap": module.CAP}]}
    (root / module.MANIFEST).write_text(json.dumps(manifest))
    (root / "index.html").write_bytes(b"<title>Synthetic</title>")
    (root / "public.json").write_bytes(b'{"synthetic":true}')
    return root, manifest, encoded


def scope(path="/" + NAME, method="GET", headers=(), pathsend=False):
    return {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
            "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
            "headers": [(b"host", b"127.0.0.1:8765"), *headers], "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 8765), "extensions": {"http.response.pathsend": {}} if pathsend else {}}


async def call(app, request=None):
    messages = []
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    async def send(message):
        messages.append(message)
    await app(request or scope(), receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    return start["status"], dict(start["headers"]), b"".join(m.get("body", b"") for m in messages), messages


def run(root, **kwargs):
    app = create_app(root.parent / "unused-store", web_directory=root)
    return asyncio.run(call(app, scope(**kwargs)))


def verify(result, expected, coding=None):
    status, headers, body, messages = result
    assert status == 200
    assert body == expected
    assert headers[b"content-length"] == str(len(body)).encode()
    assert headers[b"etag"] == ('"' + digest(body) + '"').encode()
    assert headers.get(b"content-encoding") == coding
    assert headers[b"vary"] == b"Accept-Encoding"
    assert headers[b"accept-ranges"] == b"none"
    assert headers[b"x-content-type-options"] == b"nosniff"
    assert b"last-modified" not in headers
    assert all(m["type"] != "http.response.pathsend" for m in messages)
    if coding:
        assert gzip.decompress(body) == BODY


@pytest.mark.parametrize("accept,coding,status", [
    (None,None,200), ("",None,200), ("identity",None,200), ("gzip","gzip",200),
    ("GZIP","gzip",200), ("gzip;q=0",None,200), ("gzip;q=0.5",None,200),
    ("gzip;q=0.5,identity;q=0.2","gzip",200), ("*","gzip",200),
    ("*;q=0",None,406), ("*;q=0,gzip;q=1","gzip",200),
    ("gzip;q=0,identity;q=0",None,406), ("br",None,200), ("xgzip",None,200),
    (",gzip,,","gzip",200), ("gzip;q=1.000","gzip",200), ("gzip;q=1.001",None,400),
    ("gzip;q=.5",None,400), ("gzip;q=0.0000",None,400), ("gzip;q=nan",None,400),
    ("gzip;foo=1",None,400), ("gzip,gzip;q=0",None,400), ("a"*4097,None,431),
])
def test_negotiation(built, accept, coding, status):
    root, _, encoded = built
    headers = [] if accept is None else [(b"accept-encoding", accept.encode())]
    result = run(root, headers=headers)
    assert result[0] == status
    if status == 200:
        verify(result, encoded if coding else BODY, coding.encode() if coding else None)
    else:
        assert not result[2]


def test_duplicate_headers_and_conditionals(built):
    root, _, encoded = built
    result = run(root, headers=[(b"accept-encoding",b"gzip"),(b"accept-encoding",b"gzip;q=1")])
    verify(result, encoded, b"gzip")
    identity = run(root)
    assert identity[1][b"etag"] != result[1][b"etag"]
    for coding, selected in [(b"identity", identity), (b"gzip", result)]:
        for method in ["GET", "HEAD"]:
            for condition in [selected[1][b"etag"], b"W/"+selected[1][b"etag"], b'"other", '+selected[1][b"etag"], b"*"]:
                response = run(root, method=method, headers=[(b"accept-encoding",coding),(b"if-none-match",condition)])
                assert response[0] == 304 and not response[2]
                assert response[1][b"etag"] == selected[1][b"etag"]
                assert response[1][b"vary"] == b"Accept-Encoding"
                assert response[1].get(b"content-encoding") == selected[1].get(b"content-encoding")
            other = result if coding == b"identity" else identity
            response = run(root, method=method, headers=[(b"accept-encoding",coding),(b"if-none-match",other[1][b"etag"]),
                (b"if-modified-since",b"Wed, 31 Dec 2099 00:00:00 GMT")])
            assert response[0] == 200
        repeated = run(root, headers=[(b"accept-encoding",coding),(b"if-none-match",b'"other"'),(b"if-none-match",selected[1][b"etag"])])
        assert repeated[0] == 304
        head = run(root, method="HEAD", headers=[(b"accept-encoding",coding)])
        assert head[1] == selected[1] and head[2] == b""


@pytest.mark.parametrize("range_value", ["bytes=0-4", "bytes=-10", "bytes=999999-", "bytes=1-3,5-7", "broken"])
@pytest.mark.parametrize("coding", [b"gzip", b"identity"])
def test_ranges_and_pathsend(built, range_value, coding):
    root, _, encoded = built
    headers = [(b"accept-encoding",coding),(b"range",range_value.encode()),(b"if-range",b'"anything"')]
    verify(run(root, headers=headers, pathsend=True), encoded if coding == b"gzip" else BODY,
           coding if coding == b"gzip" else None)
    get = run(root, headers=headers)
    head = run(root, method="HEAD", headers=headers)
    assert head[1] == get[1] and not head[2]


@pytest.mark.parametrize("damage", ["missing", "corrupt", "truncate", "same_length", "oversize", "directory", "symlink", "unreadable"])
def test_bad_sidecar_fallback(built, damage, monkeypatch):
    root, _, encoded = built
    side = root / f".encoded/{NAME}.gz"
    if damage == "unreadable":
        original = module._bounded
        def read(path, cap):
            if path == side:
                raise PermissionError("synthetic")
            return original(path, cap)
        monkeypatch.setattr(module, "_bounded", read)
    else:
        side.unlink()
        if damage == "corrupt": side.write_bytes(b"bad")
        if damage == "truncate": side.write_bytes(encoded[:-1])
        if damage == "same_length": side.write_bytes(b"x" * len(encoded))
        if damage == "oversize": side.write_bytes(b"x" * (module.CAP + 1))
        if damage == "directory": side.mkdir()
        if damage == "symlink": side.symlink_to(root / NAME)
    verify(run(root, headers=[(b"accept-encoding",b"gzip")]), BODY)
    response = run(root, headers=[(b"accept-encoding",b"gzip,identity;q=0")])
    assert response[0] == 406 and not response[2]


def test_original_changes(built):
    root, _, _ = built
    changed = b"changed original"
    (root / NAME).write_bytes(changed)
    verify(run(root, headers=[(b"accept-encoding",b"gzip")]), changed)
    assert run(root, headers=[(b"accept-encoding",b"gzip,identity;q=0")])[0] == 406
    (root / NAME).write_bytes(b"x" * (module.CAP + 1))
    assert run(root)[0] == 503
    (root / NAME).unlink()
    assert run(root)[0] == 404


@pytest.mark.parametrize("coding", [b"identity", b"gzip"])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_response_immutable_after_read(built, coding, method):
    root, _, encoded = built
    app = module.EncodedStaticFiles(directory=root)
    async def scenario():
        request = scope(method=method, headers=[(b"accept-encoding", coding)], pathsend=True)
        response = await app.get_response(NAME, request)
        (root / NAME).write_bytes(b"new source")
        (root / f".encoded/{NAME}.gz").unlink()
        result = await call(response, request)
        expected = encoded if coding == b"gzip" else BODY
        assert result[1][b"content-length"] == str(len(expected)).encode()
        assert result[1][b"etag"] == ('"'+digest(expected)+'"').encode()
        assert result[2] == (b"" if method == "HEAD" else expected)
        assert not any(m["type"] == "http.response.pathsend" for m in result[3])
    asyncio.run(scenario())


def test_between_reads_and_threadpool(built, monkeypatch):
    root, _, encoded = built
    original = module.EncodedStaticFiles._read
    worker_threads = []
    def read(self, path, cap):
        worker_threads.append(threading.get_ident())
        value = original(self, path, cap)
        if path == NAME:
            (root / NAME).write_bytes(b"changed after snapshot")
        return value
    monkeypatch.setattr(module.EncodedStaticFiles,"_read",read)
    verify(run(root, headers=[(b"accept-encoding",b"gzip")]), encoded, b"gzip")
    assert worker_threads and threading.get_ident() not in worker_threads


@pytest.mark.parametrize("path", ["/.static-encodings.json", "/.STATIC-ENCODINGS.JSON", "/.ENCODED/x", "/assets/FILE.GZ", "/.encoded/"+NAME+".gz", "/a/../.static-encodings.json", "/assets/../.encoded/a", "/assets/file.gz", "/.encoded/../index.html", "/../outside.js"])
def test_reserved_and_escape(built, path):
    assert run(built[0], path=path)[0] == 404


@pytest.mark.parametrize("field,value", [("cap",True),("cap",0),("cap",module.CAP+1),("identity_bytes",True),
    ("gzip_bytes",-1),("identity_sha256","bad"),("media_type","application/json"),
    ("identity_path","../index-12345678.js"),("gzip_path","/outside.gz"),("gzip_path",".encoded/../bad.gz")])
def test_invalid_manifest_values(built, field, value):
    root, manifest, _ = built
    manifest["assets"][0][field] = value
    (root / module.MANIFEST).write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="invalid_static_encoding_manifest"):
        create_app(root.parent / "unused", web_directory=root)


@pytest.mark.parametrize("damage", ["json", "duplicate", "version_bool", "entry_duplicate", "unknown", "oversize", "directory", "symlink"])
def test_manifest_rejected(built, damage):
    root, manifest, _ = built
    path = root / module.MANIFEST
    if damage == "json": path.write_text("{")
    if damage == "duplicate": path.write_text('{"schema_version":1,"schema_version":1,"assets":[]}')
    if damage == "version_bool":
        manifest["schema_version"] = True; path.write_text(json.dumps(manifest))
    if damage == "entry_duplicate":
        manifest["assets"] *= 2; path.write_text(json.dumps(manifest))
    if damage == "unknown":
        manifest["extra"] = 1; path.write_text(json.dumps(manifest))
    if damage == "oversize": path.write_bytes(b" " * (module._MANIFEST_CAP+1))
    if damage in {"directory","symlink"}:
        path.unlink()
        if damage == "directory": path.mkdir()
        else: path.symlink_to(root / "public.json")
    with pytest.raises(ValueError, match="invalid_static_encoding_manifest"):
        module.EncodedStaticFiles(directory=root)


def test_non_targets_legacy_and_local_boundary(built):
    root, _, _ = built
    for path in ["/", "/public.json", "/api/config"]:
        result = run(root, path=path, headers=[(b"accept-encoding",b"gzip;q=broken")])
        assert result[0] == 200 and b"content-encoding" not in result[1]
        assert b"vary" not in result[1]
    assert run(root, path="/api/config")[1][b"cache-control"] == b"no-store"
    assert run(root, path="/api/export/synthetic", method="POST")[0] == 403
    assert run(root, headers=[(b"host",b"evil.test")])[0] == 403
    (root / module.MANIFEST).unlink()
    result = run(root, headers=[(b"accept-encoding",b"gzip")])
    assert result[0] == 200 and result[2] == BODY
    assert b"content-encoding" not in result[1] and b"last-modified" in result[1]
    assert run(root, path=f"/.encoded/{NAME}.gz")[0] == 404


def test_target_nonregular_and_parent_symlink(built):
    root, _, _ = built
    target = root / NAME
    target.unlink(); target.mkdir()
    assert run(root)[0] == 503
    target.rmdir()
    target.symlink_to(root / "public.json")
    assert run(root)[0] == 503
    target.unlink()
    (root / "assets").rmdir()
    (root / "assets").symlink_to(root / ".encoded/assets", target_is_directory=True)
    assert run(root)[0] == 503


@pytest.mark.parametrize("destination", [module.MANIFEST, f".encoded/{NAME}.gz"])
def test_public_alias_cannot_expose_internal_files(built, destination):
    root, _, _ = built
    (root / "alias.txt").symlink_to(root / destination)
    assert run(root, path="/alias.txt")[0] == 404
    (root / module.MANIFEST).unlink()
    assert run(root, path="/alias.txt")[0] == 404


@pytest.mark.skipif(not hasattr(__import__('os'), 'mkfifo'), reason='POSIX FIFO only; Windows native separately unverified')
def test_fifo_rejected_before_open(built):
    import os
    root, _, _ = built
    target = root / NAME
    target.unlink(); os.mkfifo(target)
    assert run(root)[0] == 503
    manifest = root / module.MANIFEST
    manifest.unlink(); os.mkfifo(manifest)
    with pytest.raises(ValueError, match="invalid_static_encoding_manifest"):
        module.EncodedStaticFiles(directory=root)


@pytest.mark.parametrize("alias", ["ASSETS/index-12345678.js", "assets/INDEX-12345678.js", "assets/index-12345678.JS"])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_target_case_alias_never_reaches_legacy_fallback(built, monkeypatch, alias, method):
    # Explicit synthetic permissive fallback, not a claim of native Windows testing.
    delegated = []
    async def permissive_fallback(self, path, request):
        delegated.append(path)
        return module.Response(BODY, headers={"X-Synthetic-Legacy": "reached"})
    monkeypatch.setattr(module.StaticFiles, "get_response", permissive_fallback)
    root, _, _ = built
    result = run(root, path="/"+alias, method=method, headers=[
        (b"accept-encoding", b"gzip,identity;q=0"), (b"range", b"bytes=0-4")])
    assert result[0] == 404
    assert not delegated and not result[2]


def test_manifest_rejects_casefold_target_collision(built):
    root, manifest, _ = built
    other = dict(manifest["assets"][0], identity_path="assets/Index-12345678.js",
                 gzip_path=".encoded/assets/Index-12345678.js.gz")
    manifest["assets"].append(other)
    (root / module.MANIFEST).write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="invalid_static_encoding_manifest"):
        module.EncodedStaticFiles(directory=root)


@pytest.mark.parametrize("alias", ["assets/index-12345678.js.", "assets/index-12345678.js ",
    "assets./index-12345678.js", "assets /index-12345678.js", "assets/index-12345678.js::$DATA",
    "assets\\index-12345678.js", "assets/INDEX-~1.JS", "public-alias.js"])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_noncanonical_managed_destinations_never_use_legacy(built, monkeypatch, alias, method):
    # Only filesystem lookup is simulated; real dispatch/fallback/response runs.
    root, _, _ = built
    original = module.StaticFiles.lookup_path
    def resolved_lookup(self, path):
        if path == alias:
            target = root / NAME
            return str(target), target.stat()
        return original(self, path)
    monkeypatch.setattr(module.StaticFiles, "lookup_path", resolved_lookup)
    result = run(root, path="/"+alias, method=method, headers=[
        (b"accept-encoding",b"gzip,identity;q=0"), (b"range",b"bytes=0-4"),
        (b"if-modified-since",b"Wed, 31 Dec 2099 00:00:00 GMT")])
    assert result[0] == 404
    assert b"content-range" not in result[1]
    assert BODY not in result[2]


@pytest.mark.parametrize("target", [NAME, module.MANIFEST, f".encoded/{NAME}.gz", "public.json"])
def test_fallback_hardlinks_are_denied(built, target):
    import os
    root, _, _ = built
    os.link(root / target, root / "hardlink-alias.txt")
    assert run(root, path="/hardlink-alias.txt")[0] == 404
    # Canonical managed assets are still served through their own snapshots.
    assert run(root)[0] == 200


def test_public_symlink_and_ambiguous_destination_controls(built):
    root, _, _ = built
    (root / "normal-alias.json").symlink_to(root / "public.json")
    assert run(root, path="/normal-alias.json")[2] == b'{"synthetic":true}'
    (root / "managed-alias.js").symlink_to(root / NAME)
    assert run(root, path="/managed-alias.js")[0] == 404
    for index, name in enumerate(["odd.txt.", "odd.txt ", "odd:stream"]):
        (root / name).write_bytes(b"AMBIGUOUS_SYNTHETIC")
        (root / f"innocent{index}.txt").symlink_to(root / name)
        assert run(root, path=f"/innocent{index}.txt")[0] == 404


def test_native_internal_separators_are_not_raw_url_backslashes(built, monkeypatch):
    import ntpath
    import os
    from types import SimpleNamespace
    root, _, encoded = built
    (root / "licenses").mkdir()
    (root / "licenses/notice.txt").write_bytes(b"PUBLIC_SYNTHETIC_NOTICE")
    app = module.EncodedStaticFiles(directory=root, html=True)
    # Isolated internal path normalization only; no OS identity override.
    monkeypatch.setattr(module, "os", SimpleNamespace(sep="\\", path=ntpath, fstat=os.fstat))
    async def scenario():
        request = scope(headers=[(b"accept-encoding",b"gzip")])
        response = await app.get_response(ntpath.normpath(NAME), request)
        verify(await call(response, request), encoded, b"gzip")
        public = await app.get_response(ntpath.normpath("licenses/notice.txt"), scope(path="/licenses/notice.txt"))
        result = await call(public, scope(path="/licenses/notice.txt"))
        assert result[0] == 200 and result[2] == b"PUBLIC_SYNTHETIC_NOTICE"
        raw = await call(app, scope(path="/assets\\index-12345678.js"))
        assert raw[0] == 404
    asyncio.run(scenario())
