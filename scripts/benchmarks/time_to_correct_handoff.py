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
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
LANES = {"preparation", "answer", "grader", "jev-approval"}
COMPLETION_ATTESTATION = "completion-attestation.json"
COMPLETION_ATTESTATION_SCHEMA = "velgraphing-lane-completion-attestation-v1"


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


def read_bounded_regular_at(directory: int, name: str) -> bytes:
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
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def read_canonical_at(directory: int, name: str) -> tuple[bytes, dict[str, Any]]:
    raw = read_bounded_regular_at(directory, name)
    return raw, decode(raw)


def normalize_json_object(raw: bytes) -> bytes:
    if len(raw) > MAX_BYTES:
        raise HandoffError("handoff_file_invalid")

    def object_value(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError
            value[key] = item
        return value

    def reject_constant(_: str) -> None:
        raise ValueError

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=object_value,
            parse_constant=reject_constant,
        )
        if type(value) is not dict:
            raise ValueError
        normalized = canonical(value)
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError):
        raise HandoffError("invalid_json_object") from None
    if len(normalized) > MAX_BYTES:
        raise HandoffError("invalid_json_object")
    return normalized


def _execution_identity(
    trial_id: str, lane: str, thread_id: str, model: str, reasoning: str
) -> dict[str, str]:
    return {
        "trial_id": identifier(trial_id),
        "role": identifier(lane),
        "thread_id": identifier(thread_id),
        "model": identifier(model),
        "reasoning": identifier(reasoning),
    }


def bound_lane_identity(
    root: Path, trial_id: str, lane: str, manifest_sha256: str
) -> dict[str, str]:
    raw, manifest = read_canonical(root / "lane-manifest.json")
    entries = manifest.get("entries")
    if (
        not SHA256.fullmatch(manifest_sha256)
        or digest(raw) != manifest_sha256
        or manifest.get("schema_version") != "velgraphing-v4-luna-lane-manifest-v1"
        or type(entries) is not list
    ):
        raise HandoffError("lane_manifest_identity_invalid")
    matches = [
        entry for entry in entries if type(entry) is dict
        and entry.get("trial_id") == trial_id and entry.get("role") == lane
    ]
    if len(matches) != 1:
        raise HandoffError("lane_manifest_identity_invalid")
    entry = matches[0]
    command = entry.get("argv")
    if (
        set(entry) != {
            "trial_id", "role", "thread_id", "model", "reasoning", "argv",
            "argv_sha256",
        }
        or type(command) is not list
        or not command
        or not all(type(argument) is str and argument for argument in command)
        or entry.get("argv_sha256") != digest(canonical(command))
    ):
        raise HandoffError("lane_manifest_identity_invalid")
    return _execution_identity(
        trial_id, lane, entry["thread_id"], entry["model"], entry["reasoning"]
    )


def attest_draft(
    root: Path,
    trial_id: str,
    attempt: int,
    lane: str,
    draft_path: Path,
    *,
    thread_id: str,
    model: str,
    reasoning: str,
    lane_manifest_sha256: str,
) -> dict[str, Any]:
    directory_path = lane_root(root, trial_id, attempt, lane)
    if (
        not draft_path.is_absolute()
        or draft_path.parent != directory_path
        or draft_path.name in {"response.json", COMPLETION_ATTESTATION}
        or not SHA256.fullmatch(lane_manifest_sha256)
    ):
        raise HandoffError("response_draft_path_invalid")
    directory = _open_lane(root, trial_id, attempt, lane, create=False)
    try:
        raw = read_bounded_regular_at(directory, draft_path.name)
        attestation = {
            "schema_version": COMPLETION_ATTESTATION_SCHEMA,
            "owner": "parent",
            "thread_status": "completed",
            "draft_status": "stable_final",
            "trial_id": trial_id,
            "attempt": attempt,
            "role": lane,
            "thread_id": thread_id,
            "execution_identity": _execution_identity(
                trial_id, lane, thread_id, model, reasoning
            ),
            "lane_manifest_sha256": lane_manifest_sha256,
            "draft_path": str(draft_path),
            "draft_size_bytes": len(raw),
            "draft_sha256": digest(raw),
        }
        atomic_write_at(directory, COMPLETION_ATTESTATION, canonical(attestation))
        return attestation
    finally:
        os.close(directory)


def read_attested_draft(
    root: Path,
    trial_id: str,
    attempt: int,
    lane: str,
    draft_path: Path,
    *,
    thread_id: str,
    model: str,
    reasoning: str,
    lane_manifest_sha256: str,
) -> bytes:
    directory_path = lane_root(root, trial_id, attempt, lane)
    if (
        not draft_path.is_absolute()
        or draft_path.parent != directory_path
        or not SHA256.fullmatch(lane_manifest_sha256)
    ):
        raise HandoffError("response_draft_path_invalid")
    directory = _open_lane(root, trial_id, attempt, lane, create=False)
    try:
        _, attestation = read_canonical_at(directory, COMPLETION_ATTESTATION)
        expected_identity = _execution_identity(
            trial_id, lane, thread_id, model, reasoning
        )
        if (
            set(attestation) != {
                "schema_version", "owner", "thread_status", "draft_status",
                "trial_id", "attempt", "role", "thread_id", "execution_identity",
                "lane_manifest_sha256", "draft_path", "draft_size_bytes", "draft_sha256",
            }
            or attestation["schema_version"] != COMPLETION_ATTESTATION_SCHEMA
            or attestation["owner"] != "parent"
            or attestation["thread_status"] != "completed"
            or attestation["draft_status"] != "stable_final"
            or attestation["trial_id"] != trial_id
            or attestation["attempt"] != attempt
            or attestation["role"] != lane
            or attestation["thread_id"] != thread_id
            or attestation["execution_identity"] != expected_identity
            or attestation["lane_manifest_sha256"] != lane_manifest_sha256
            or attestation["draft_path"] != str(draft_path)
        ):
            raise HandoffError("completion_attestation_invalid")
        raw = read_bounded_regular_at(directory, draft_path.name)
        if (
            attestation["draft_size_bytes"] != len(raw)
            or attestation["draft_sha256"] != digest(raw)
        ):
            raise HandoffError("completion_attestation_draft_changed")
        return raw
    except HandoffError as error:
        if str(error) in {"handoff_file_missing", "invalid_canonical_json"}:
            raise HandoffError("completion_attestation_invalid") from None
        raise
    finally:
        os.close(directory)


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
        answer = f"fixture answer for {trial_id}"
        if request.get("schema_version") == "velgraphing-answer-model-input-v1":
            evidence = request.get("evidence", [])
            candidate_id = evidence[0].get("id") if evidence and type(evidence[0]) is dict else None
            answer = f"fixture answer [{candidate_id}]" if candidate_id else answer
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
        return {
            "schema_version": "velgraphing-grader-output-v1",
            "required_fact_score": 1,
            "required_fact_maximum": 1,
            "critical_facts_exact": True,
            "unsupported_material_claims": 0,
            "grader_id": f"fixture-grader-{trial_id}",
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
    for name in ("wait", "attest", "respond", "fixture-worker"):
        command = commands.add_parser(name)
        command.add_argument("--run-root", required=True)
        command.add_argument("--trial-id", required=True)
        command.add_argument("--attempt", type=int, required=True)
        command.add_argument("--lane", choices=sorted(LANES), required=True)
        if name in {"wait", "fixture-worker"}:
            command.add_argument("--wait-seconds", type=float, required=True)
        elif name == "respond":
            command.add_argument("--response-file")
            command.add_argument("--normalize-json", action="store_true")
            command.add_argument("--thread-id")
            command.add_argument("--model")
            command.add_argument("--reasoning")
            command.add_argument("--lane-manifest-sha256")
        else:
            command.add_argument("--draft-file", required=True)
            command.add_argument("--thread-id", required=True)
            command.add_argument("--model", required=True)
            command.add_argument("--reasoning", required=True)
            command.add_argument("--lane-manifest-sha256", required=True)
            command.add_argument("--thread-status", choices=["completed"], required=True)
            command.add_argument("--draft-status", choices=["stable-final"], required=True)
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
        elif args.command == "attest":
            expected_identity = bound_lane_identity(
                root, args.trial_id, args.lane, args.lane_manifest_sha256
            )
            if expected_identity != _execution_identity(
                args.trial_id, args.lane, args.thread_id, args.model, args.reasoning
            ):
                raise HandoffError("lane_manifest_identity_invalid")
            attestation = attest_draft(
                root, args.trial_id, args.attempt, args.lane, Path(args.draft_file),
                thread_id=args.thread_id, model=args.model, reasoning=args.reasoning,
                lane_manifest_sha256=args.lane_manifest_sha256,
            )
            sys.stdout.buffer.write(canonical({
                "status": "completion_attested",
                "attestation_sha256": digest(canonical(attestation)),
                "draft_sha256": attestation["draft_sha256"],
            }))
        elif args.command == "respond":
            if args.response_file:
                source = Path(args.response_file)
                if (
                    source.parent != directory
                    or source.name in {"response.json", COMPLETION_ATTESTATION}
                    or not all((
                        args.thread_id, args.model, args.reasoning,
                        args.lane_manifest_sha256,
                    ))
                ):
                    raise HandoffError("response_draft_path_invalid")
                expected_identity = bound_lane_identity(
                    root, args.trial_id, args.lane, args.lane_manifest_sha256
                )
                if expected_identity != _execution_identity(
                    args.trial_id, args.lane, args.thread_id, args.model, args.reasoning
                ):
                    raise HandoffError("lane_manifest_identity_invalid")
                raw = read_attested_draft(
                    root, args.trial_id, args.attempt, args.lane, source,
                    thread_id=args.thread_id, model=args.model, reasoning=args.reasoning,
                    lane_manifest_sha256=args.lane_manifest_sha256,
                )
            else:
                raw = sys.stdin.buffer.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise HandoffError("handoff_file_invalid")
            if args.normalize_json:
                raw = normalize_json_object(raw)
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
