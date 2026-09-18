#!/usr/bin/env python3
"""Canonical file handoff for native benchmark lanes. No model launcher."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import uuid
from typing import Any


MAX_BYTES = 1024 * 1024
ID = re.compile(r"[A-Za-z0-9_.:@+-]{1,128}\Z")
LANES = {"preparation", "answer", "grader", "jev-approval"}


class HandoffError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def decode(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise HandoffError("invalid_canonical_json") from None
    if type(value) is not dict or raw != canonical(value):
        raise HandoffError("invalid_canonical_json")
    return value


def identifier(value: str) -> str:
    if type(value) is not str or not ID.fullmatch(value):
        raise HandoffError("invalid_identifier")
    return value


def run_root(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or ".velgraphing-local" not in path.parts:
        raise HandoffError("run_root_not_ignored")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise HandoffError("run_root_invalid")
    return path


def lane_root(root: Path, trial_id: str, attempt: int, lane: str) -> Path:
    identifier(trial_id)
    if type(attempt) is not int or attempt < 0 or lane not in LANES:
        raise HandoffError("invalid_lane")
    return root / "trials" / trial_id / f"attempt-{attempt}" / lane


def open_contained_directory(root: Path, parts: tuple[str, ...], *, create: bool) -> int:
    """Open a run-root child through no-follow directory descriptors."""
    root = run_root(str(root))
    if not parts or any(
        type(part) is not str or part in {"", ".", ".."} or Path(part).name != part
        for part in parts
    ):
        raise HandoffError("handoff_lane_invalid")
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise HandoffError("secure_handoff_unsupported")
    if create:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
    run_root(str(root))
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        directory = os.open(root, flags)
    except FileNotFoundError:
        raise HandoffError("handoff_lane_missing") from None
    except OSError:
        raise HandoffError("handoff_lane_invalid") from None
    try:
        for part in parts:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=directory)
                except FileExistsError:
                    pass
                except OSError:
                    raise HandoffError("handoff_lane_invalid") from None
            try:
                child = os.open(part, flags, dir_fd=directory)
            except FileNotFoundError:
                raise HandoffError("handoff_lane_missing") from None
            except OSError:
                raise HandoffError("handoff_lane_invalid") from None
            os.close(directory)
            directory = child
        return directory
    except Exception:
        os.close(directory)
        raise


def _open_lane(root: Path, trial_id: str, attempt: int, lane: str, *, create: bool) -> int:
    lane_root(root, trial_id, attempt, lane)
    return open_contained_directory(
        root, ("trials", trial_id, f"attempt-{attempt}", lane), create=create)


def _file_name(value: str) -> str:
    if type(value) is not str or value in {"", ".", ".."} or Path(value).name != value:
        raise HandoffError("handoff_file_invalid")
    return value


def read_canonical_at(directory: int, name: str) -> tuple[bytes, dict[str, Any]]:
    name = _file_name(name)
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    except FileNotFoundError:
        raise HandoffError("handoff_file_missing") from None
    except OSError:
        raise HandoffError("handoff_file_invalid") from None
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size > MAX_BYTES):
            raise HandoffError("handoff_file_invalid")
        chunks, size = [], 0
        while size <= MAX_BYTES:
            chunk = os.read(descriptor, min(65536, MAX_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        after = os.fstat(descriptor)
        identity = lambda item: (item.st_dev, item.st_ino, item.st_size,
                                 item.st_mtime_ns, item.st_ctime_ns, item.st_nlink)
        if size > MAX_BYTES or identity(before) != identity(after):
            raise HandoffError("handoff_file_invalid")
        raw = b"".join(chunks)
        return raw, decode(raw)
    finally:
        os.close(descriptor)


def read_lane(root: Path, trial_id: str, attempt: int, lane: str,
              name: str) -> tuple[bytes, dict[str, Any]]:
    directory = _open_lane(root, trial_id, attempt, lane, create=False)
    try:
        return read_canonical_at(directory, name)
    finally:
        os.close(directory)


def atomic_write_at(directory: int, name: str, raw: bytes, *, replace: bool = False) -> None:
    name = _file_name(name)
    temporary = f".{name}.{uuid.uuid4().hex}.tmp"
    try:
        if not replace:
            try:
                os.stat(name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise HandoffError("handoff_file_exists")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                             0o600, dir_fd=directory)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if not replace:
            try:
                os.stat(name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise HandoffError("handoff_file_exists")
        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode):
            raise HandoffError("handoff_file_invalid")
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass


def _write_lane(root: Path, trial_id: str, attempt: int, lane: str,
                name: str, raw: bytes, *, create: bool = False,
                replace: bool = False) -> None:
    directory = _open_lane(root, trial_id, attempt, lane, create=create)
    try:
        atomic_write_at(directory, name, raw, replace=replace)
    finally:
        os.close(directory)


def atomic_write(path: Path, raw: bytes, *, replace: bool = False) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists() and not replace:
        raise HandoffError("handoff_file_exists")
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists() and not replace:
            raise HandoffError("handoff_file_exists")
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()


def read_canonical(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_BYTES:
            raise HandoffError("handoff_file_invalid")
        raw = path.read_bytes()
    except FileNotFoundError:
        raise HandoffError("handoff_file_missing") from None
    if len(raw) > MAX_BYTES:
        raise HandoffError("handoff_file_invalid")
    return raw, decode(raw)


def receipt(root: Path, *, trial_id: str, attempt: int, lane: str, status: str,
            request_sha256: str, response_sha256: str | None, wait_ns: int) -> None:
    _write_lane(root, trial_id, attempt, lane, "receipt.json", canonical({
        "schema_version": "velgraphing-file-handoff-receipt-v1",
        "trial_id": trial_id,
        "attempt": attempt,
        "lane": lane,
        "status": status,
        "request_sha256": request_sha256,
        "response_sha256": response_sha256,
        "wait_ns": wait_ns,
    }), replace=True)


def wait_for_response(root: Path, trial_id: str, attempt: int, lane: str,
                      wait_seconds: float, request_raw: bytes) -> bytes:
    request = decode(request_raw)
    del request
    request_hash = digest(request_raw)
    _write_lane(root, trial_id, attempt, lane, "request.json", request_raw, create=True)
    start = time.monotonic_ns()
    receipt(root, trial_id=trial_id, attempt=attempt, lane=lane,
            status="request_written", request_sha256=request_hash,
            response_sha256=None, wait_ns=0)
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        try:
            response_raw, _ = read_lane(root, trial_id, attempt, lane, "response.json")
        except HandoffError as error:
            if str(error) in {"handoff_file_missing", "handoff_lane_missing"}:
                time.sleep(min(0.05, max(0.001, wait_seconds / 20)))
                continue
            if str(error) in {"handoff_file_invalid", "invalid_canonical_json"}:
                receipt(root, trial_id=trial_id, attempt=attempt, lane=lane,
                        status="response_invalid", request_sha256=request_hash,
                        response_sha256=None, wait_ns=time.monotonic_ns() - start)
            raise
        receipt(root, trial_id=trial_id, attempt=attempt, lane=lane,
                status="completed", request_sha256=request_hash,
                response_sha256=digest(response_raw), wait_ns=time.monotonic_ns() - start)
        return response_raw
    receipt(root, trial_id=trial_id, attempt=attempt, lane=lane,
            status="response_timeout", request_sha256=request_hash,
            response_sha256=None, wait_ns=time.monotonic_ns() - start)
    raise HandoffError("response_timeout")


def write_response(root: Path, trial_id: str, attempt: int, lane: str, raw: bytes) -> None:
    decode(raw)
    _write_lane(root, trial_id, attempt, lane, "response.json", raw)


def fixture_response(lane: str, trial_id: str, request: dict[str, Any]) -> dict[str, Any]:
    if lane == "preparation":
        packet = request.get("payload", {}).get("fixture_candidate_packet")
        if type(packet) is not dict:
            raise HandoffError("fixture_candidate_packet_missing")
        return {
            "schema_version": "velgraphing-preparation-output-v1",
            "candidate_packet": packet,
            "usage": None,
            "model_calls_complete": False,
            "context_deliveries_complete": True,
        }
    if lane == "answer":
        answer = request.get("payload", {}).get("fixture_answer", f"fixture answer for {trial_id}")
        if type(answer) is not str:
            raise HandoffError("fixture_answer_invalid")
        return {
            "schema_version": "velgraphing-answer-output-v1",
            "answer_text": answer,
            "usage": None,
            "model_calls_complete": False,
            "context_deliveries_complete": True,
        }
    if lane == "grader":
        identity = request.get("identity", {})
        return {
            "schema_version": "velgraphing-grader-output-v1",
            "required_fact_score": 1,
            "required_fact_maximum": 1,
            "critical_facts_exact": True,
            "unsupported_material_claims": 0,
            "grader_id": f"fixture-grader-{trial_id}",
            "rubric_sha256": identity.get("rubric_sha256"),
            "usage": None,
            "model_calls_complete": False,
        }
    raise HandoffError("fixture_lane_forbidden")


def wait_for_request(root: Path, trial_id: str, attempt: int, lane: str,
                     wait_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        try:
            return read_lane(root, trial_id, attempt, lane, "request.json")[1]
        except HandoffError as error:
            if str(error) not in {"handoff_file_missing", "handoff_lane_missing"}:
                raise
        time.sleep(min(0.05, max(0.001, wait_seconds / 20)))
    raise HandoffError("request_timeout")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("wait", "respond", "fixture-worker"):
        command = commands.add_parser(name)
        command.add_argument("--run-root", required=True)
        command.add_argument("--trial-id", required=True)
        command.add_argument("--attempt", type=int, required=True)
        command.add_argument("--lane", choices=sorted(LANES), required=True)
        if name != "respond":
            command.add_argument("--wait-seconds", type=float, required=True)
        else:
            command.add_argument("--response-file")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        root = run_root(args.run_root)
        directory = lane_root(root, args.trial_id, args.attempt, args.lane)
        if args.command == "wait":
            if not (0 < args.wait_seconds <= 86400):
                raise HandoffError("invalid_wait_seconds")
            raw = sys.stdin.buffer.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise HandoffError("handoff_file_invalid")
            sys.stdout.buffer.write(wait_for_response(
                root, args.trial_id, args.attempt, args.lane, args.wait_seconds, raw))
        elif args.command == "respond":
            if args.response_file:
                source = Path(args.response_file)
                if source.parent != directory or source.name == "response.json":
                    raise HandoffError("response_draft_path_invalid")
                raw = read_lane(root, args.trial_id, args.attempt, args.lane, source.name)[0]
            else:
                raw = sys.stdin.buffer.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise HandoffError("handoff_file_invalid")
            write_response(root, args.trial_id, args.attempt, args.lane, raw)
            sys.stdout.buffer.write(canonical({"status": "response_written", "sha256": digest(raw)}))
        else:
            if args.lane == "jev-approval" or not (0 < args.wait_seconds <= 300):
                raise HandoffError("fixture_lane_forbidden")
            request = wait_for_request(root, args.trial_id, args.attempt, args.lane,
                                       args.wait_seconds)
            write_response(root, args.trial_id, args.attempt, args.lane,
                           canonical(fixture_response(args.lane, args.trial_id, request)))
        return 0
    except HandoffError as error:
        print(str(error), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
