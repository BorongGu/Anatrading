"""Local filesystem locks work across processes without replacing the lock inode."""
import io
import multiprocessing
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

import anatrading.store as module
from anatrading.store import EvidenceStore, StoreError, _DirectoryLock


def _hold_lock(root, connection):
    with _DirectoryLock(Path(root)):
        connection.send("locked")
        if connection.recv() == "crash":
            os._exit(73)
    connection.send("released")
    connection.close()


@pytest.mark.parametrize("finish", ["close", "crash"])
def test_lock_excludes_other_process_and_preserves_inode_after_release(tmp_path, finish):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=_hold_lock, args=(str(tmp_path), child))
    process.start()
    child.close()
    try:
        assert parent.poll(20), "Child did not acquire the directory lock"
        assert parent.recv() == "locked"
        path = tmp_path / ".operation.lock"
        inode = path.stat().st_ino
        with pytest.raises(StoreError, match="data_directory_busy"):
            _DirectoryLock(tmp_path)
        assert path.stat().st_ino == inode
        parent.send(finish)
        process.join(20)
        assert not process.is_alive()
        assert process.exitcode == (73 if finish == "crash" else 0)
        with _DirectoryLock(tmp_path):
            assert path.stat().st_ino == inode
            with pytest.raises(StoreError, match="data_directory_busy"):
                _DirectoryLock(tmp_path)
        assert path.exists() and path.stat().st_ino == inode
    finally:
        if process.is_alive():
            process.kill()
            process.join(20)
        parent.close()
        process.close()


def test_store_initialization_failure_releases_directory_lock(tmp_path, monkeypatch):
    def fail_initialize(self):
        raise RuntimeError("synthetic initialization failure")

    with monkeypatch.context() as patch:
        patch.setattr(EvidenceStore, "_initialize", fail_initialize)
        with pytest.raises(RuntimeError, match="synthetic initialization"):
            EvidenceStore(tmp_path)
    with EvidenceStore(tmp_path) as store:
        assert store.list_snapshots() == []
    store.close()


class _LockStream(io.BytesIO):
    def __init__(self, fail=None):
        super().__init__()
        self.fail = fail

    def fileno(self):
        return 42

    def seek(self, *args):
        if self.fail == "seek":
            raise OSError("synthetic seek failure")
        return super().seek(*args)

    def write(self, content):
        if self.fail == "write":
            raise OSError("synthetic write failure")
        return super().write(content)

    def flush(self):
        if self.fail == "flush":
            raise OSError("synthetic flush failure")
        return super().flush()


class _LockRoot:
    def __init__(self, stream):
        self.stream = stream

    def __truediv__(self, name):
        assert name == ".operation.lock"
        return self

    def open(self, mode):
        assert mode == "a+b"
        return self.stream


@pytest.mark.parametrize("platform", ["nt", "posix"])
@pytest.mark.parametrize("failure", ["seek", "lock", "interrupt", "unlock", "close_seek", None])
def test_lock_closes_handle_on_all_paths(monkeypatch, platform, failure):
    stream = _LockStream(failure)
    calls = []

    def lock(fd, operation, *args):
        assert fd == 42
        calls.append((operation, args))
        if failure == "lock" and operation != 8:
            raise OSError("synthetic lock failure")
        if failure == "interrupt":
            raise KeyboardInterrupt
        if failure == "unlock" and operation == 8:
            raise OSError("synthetic unlock failure")

    monkeypatch.setattr(module, "os", SimpleNamespace(name=platform, SEEK_END=2))
    monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(locking=lock, LK_NBLCK=6, LK_UNLCK=8))
    monkeypatch.setitem(sys.modules, "fcntl", SimpleNamespace(flock=lock, LOCK_EX=2, LOCK_NB=4, LOCK_UN=8))
    root = _LockRoot(stream)
    if failure in {"seek", "lock", "interrupt"}:
        with pytest.raises(KeyboardInterrupt if failure == "interrupt" else StoreError):
            _DirectoryLock(root)
    else:
        guard = _DirectoryLock(root)
        assert not stream.closed
        assert calls == [(6, (1,) if platform == "nt" else ())]
        if failure == "close_seek":
            stream.fail = "seek"
        if failure in {"unlock", "close_seek"}:
            with pytest.raises(OSError):
                guard.close()
        else:
            guard.close()
        guard.close()
        if failure != "close_seek":
            assert calls[-1] == (8, (1,) if platform == "nt" else ())
    assert stream.closed


@pytest.mark.parametrize("failure", ["write", "flush"])
def test_windows_lock_initial_byte_failure_closes_handle(monkeypatch, failure):
    stream = _LockStream(failure)
    monkeypatch.setattr(module, "os", SimpleNamespace(name="nt", SEEK_END=2))
    monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(LK_NBLCK=6, LK_UNLCK=8))
    with pytest.raises(StoreError, match="data_directory_busy"):
        _DirectoryLock(_LockRoot(stream))
    assert stream.closed
