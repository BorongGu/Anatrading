"""Bounded representations of trusted, fixed-build JS/CSS; no API compression."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from starlette.concurrency import run_in_threadpool
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

CAP = 2_097_152
MANIFEST = ".static-encodings.json"
_MANIFEST_CAP = 1_048_576
_ASSET = re.compile(r"assets/[A-Za-z0-9_-]+-[A-Za-z0-9_-]{8,}\.(js|css)")
_QVALUE = re.compile(r"\s*([!#$%&'*+.^_`|~0-9A-Za-z-]+)\s*(?:;\s*q\s*=\s*(0(?:\.\d{0,3})?|1(?:\.0{0,3})?))?\s*", re.I)


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _bounded(path, cap):
    # Fixed, trusted build tree; reject nonregular files before open (FIFO, etc.).
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("nonregular_static_asset")
    with path.open("rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("nonregular_static_asset")
        value = stream.read(cap + 1)
    if len(value) > cap:
        raise ValueError("static_asset_size_cap")
    return value


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_manifest_key")
        result[key] = value
    return result


@dataclass(frozen=True)
class _Asset:
    identity_path: str
    gzip_path: str
    identity_sha256: str
    gzip_sha256: str
    identity_bytes: int
    gzip_bytes: int
    media_type: str
    cap: int


def _load_manifest(root):
    path = root / MANIFEST
    try:
        path.lstat()
    except FileNotFoundError:
        return {}  # Backward-compatible old dist; no encoded representation promised.
    except OSError as error:
        raise ValueError("invalid_static_encoding_manifest") from error
    try:
        data = json.loads(_bounded(path, _MANIFEST_CAP), object_pairs_hook=_object)
        if (not isinstance(data, dict) or set(data) != {"schema_version", "assets"}
                or type(data["schema_version"]) is not int or data["schema_version"] != 1
                or not isinstance(data["assets"], list) or len(data["assets"]) > 1024):
            raise ValueError("manifest_schema")
        result = {}
        for item in data["assets"]:
            if not isinstance(item, dict) or set(item) != set(_Asset.__dataclass_fields__):
                raise ValueError("manifest_asset_schema")
            asset = _Asset(**item)
            if (not isinstance(asset.identity_path, str) or not _ASSET.fullmatch(asset.identity_path)
                    or asset.gzip_path != f".encoded/{asset.identity_path}.gz"
                    or asset.media_type != ("text/javascript" if asset.identity_path.endswith(".js") else "text/css")
                    or type(asset.cap) is not int or not 0 < asset.cap <= CAP
                    or any(type(size) is not int or not 0 <= size <= asset.cap
                           for size in (asset.identity_bytes, asset.gzip_bytes))
                    or any(not isinstance(tag, str) or not re.fullmatch(r"[0-9a-f]{64}", tag)
                           for tag in (asset.identity_sha256, asset.gzip_sha256))
                    or asset.identity_path in result):
                raise ValueError("manifest_asset_value")
            result[asset.identity_path] = asset
        return result
    except (OSError, ValueError, TypeError, RecursionError) as error:
        raise ValueError("invalid_static_encoding_manifest") from error


def _qualities(headers):
    fields = [value for key, value in headers if key.lower() == b"accept-encoding"]
    if sum(map(len, fields)) + max(0, len(fields) - 1) > 4096:
        return None, 431
    raw = b",".join(fields).decode("latin1")
    if not raw.strip():
        return {"identity": 1, "gzip": 0}, None
    values = {}
    for item in raw.split(","):
        if not item.strip():
            continue
        match = _QVALUE.fullmatch(item)
        if not match:
            return None, 400
        key, quality = match[1].lower(), float(match[2]) if match[2] else 1
        if key in values and values[key] != quality:
            return None, 400
        values[key] = quality
    return {"identity": values.get("identity", 0 if values.get("*") == 0 else 1),
            "gzip": values.get("gzip", values.get("*", 0))}, None


def _reserved(path):
    # Check both the original URL and StaticFiles-normalized paths.
    parts = path.replace("\\", "/").casefold().split("/")
    return any(part in {MANIFEST, ".encoded"} or part.endswith(".gz") for part in parts)


class EncodedStaticFiles(StaticFiles):
    def __init__(self, *, directory, **kwargs):
        super().__init__(directory=directory, **kwargs)
        self.root = Path(directory).resolve()
        self.assets = _load_manifest(self.root)

    async def __call__(self, scope, receive, send):
        if _reserved(scope["path"]):
            return await Response(status_code=404)(scope, receive, send)
        return await super().__call__(scope, receive, send)

    def lookup_path(self, path):
        full_path, info = super().lookup_path(path)
        if info is not None:
            try:
                relative = Path(full_path).resolve().relative_to(self.root).as_posix()
            except ValueError:
                return "", None
            if _reserved(relative):
                return "", None
        return full_path, info

    def _read(self, relative, cap):
        candidate = self.root
        for part in relative.split("/"):
            candidate = candidate / part
            if candidate.is_symlink():
                raise ValueError("static_asset_symlink")
        if not candidate.resolve().is_relative_to(self.root):
            raise ValueError("static_asset_outside_root")
        return _bounded(candidate, cap)

    def _snapshot(self, asset, quality):
        try:
            identity = self._read(asset.identity_path, asset.cap)
        except FileNotFoundError:
            return None, None, 404
        except (OSError, ValueError):
            return None, None, 503
        identity_tag = _digest(identity)
        if (quality["gzip"] > 0 and quality["gzip"] >= quality["identity"]
                and len(identity) == asset.identity_bytes and identity_tag == asset.identity_sha256):
            try:
                encoded = self._read(asset.gzip_path, asset.cap)
                tag = _digest(encoded)
                if len(encoded) == asset.gzip_bytes and tag == asset.gzip_sha256:
                    return encoded, tag, "gzip"
            except (OSError, ValueError):
                pass
        if quality["identity"] <= 0:
            return None, None, 406
        return identity, identity_tag, "identity"

    async def get_response(self, path, scope):
        if _reserved(path):
            return Response(status_code=404)
        # StaticFiles normalizes using platform paths; manifest paths use '/'.
        asset = self.assets.get(path.replace(os.sep, "/"))
        if asset is None:
            return await super().get_response(path, scope)
        headers = {"Vary": "Accept-Encoding", "Accept-Ranges": "none", "X-Content-Type-Options": "nosniff"}
        if scope["method"] not in ("GET", "HEAD"):
            return Response(status_code=405, headers={**headers, "Allow": "GET, HEAD"})
        quality, error = _qualities(scope["headers"])
        if error:
            return Response(status_code=error, headers=headers)
        content, tag, coding = await run_in_threadpool(self._snapshot, asset, quality)
        if isinstance(coding, int):
            return Response(status_code=coding, headers=headers)
        headers["ETag"] = f'"{tag}"'
        if coding == "gzip":
            headers["Content-Encoding"] = "gzip"
        conditions = b",".join(value for key, value in scope["headers"] if key.lower() == b"if-none-match").decode("latin1")
        if any(token.strip() in {"*", headers["ETag"], "W/" + headers["ETag"]} for token in conditions.split(",")):
            return Response(status_code=304, headers=headers)
        headers["Content-Length"] = str(len(content))
        return Response(b"" if scope["method"] == "HEAD" else content, headers=headers, media_type=asset.media_type)
