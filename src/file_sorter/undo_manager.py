import hashlib
import json
import os
import shutil
import uuid

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_CHUNK_SIZE = 1024 * 1024

VALID_STATUSES = {
    "pending",
    "completed",
    "failed",
    "restoring",
    "restored",
    "restore_failed",
}


class UndoError(Exception):
    """Base exception for undo operations."""


class UndoLogError(UndoError, ValueError):
    """Raised when an undo log is invalid or inaccessible."""


@dataclass(frozen=True)
class UndoResult:
    operation_id: str
    original_path: Path
    destination_path: Path
    status: str
    reason: str
    success: bool


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


def calculate_hash(path, chunk_size=DEFAULT_CHUNK_SIZE):
    path = Path(path)
    hasher = hashlib.sha256()

    with path.open("rb") as file:
        while chunk := file.read(chunk_size):
            hasher.update(chunk)

    return hasher.hexdigest()


class UndoLogger:

    def __init__(self, log_path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        self.log_path.touch(exist_ok=True)

    def _append(self, event):
        try:
            with self.log_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(event) + "\n")
                file.flush()
                os.fsync(file.fileno())

        except OSError as error:
            raise UndoLogError(
                f"Unable to write undo log: {error}"
            ) from error

    def start_operation(self, original_path, destination_path):
        original = Path(original_path).resolve()
        destination = Path(destination_path).resolve()

        if original == destination:
            raise UndoLogError(
                "Original and destination paths cannot be identical."
            )

        if not original.is_file():
            raise UndoLogError(
                f"Original file does not exist: {original}"
            )

        operation_id = str(uuid.uuid4())

        event = {
            "event": "operation",
            "operation_id": operation_id,
            "original_path": str(original),
            "destination_path": str(destination),
            "file_hash": calculate_hash(original),
            "status": "pending",
            "timestamp": _timestamp(),
        }

        self._append(event)

        return operation_id

    def update_status(self, operation_id, status, reason=""):
        if status not in VALID_STATUSES:
            raise UndoLogError(
                f"Invalid operation status: {status}"
            )

        self._append({
            "event": "status",
            "operation_id": operation_id,
            "status": status,
            "reason": reason,
            "timestamp": _timestamp(),
        })


def read_undo_log(log_path):
    path = Path(log_path)

    if not path.is_file():
        raise UndoLogError(
            f"Undo log does not exist: {path}"
        )

    operations = {}

    try:
        with path.open("r", encoding="utf-8") as file:
            lines = file.readlines()

        for line_number, line in enumerate(lines, start=1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise UndoLogError(
                    f"Invalid JSON at line {line_number}."
                ) from error

            if event.get("event") == "operation":
                required = {
                    "operation_id",
                    "original_path",
                    "destination_path",
                    "file_hash",
                    "status",
                }

                if not required.issubset(event):
                    raise UndoLogError(
                        f"Missing operation fields at line {line_number}."
                    )

                if event["status"] not in VALID_STATUSES:
                    raise UndoLogError(
                        f"Invalid status at line {line_number}."
                    )

                operation_id = event["operation_id"]

                if operation_id in operations:
                    raise UndoLogError(
                        f"Duplicate operation ID: {operation_id}"
                    )

                operations[operation_id] = event.copy()

            elif event.get("event") == "status":
                operation_id = event.get("operation_id")
                status = event.get("status")

                if operation_id not in operations:
                    raise UndoLogError(
                        f"Unknown operation ID at line {line_number}."
                    )

                if status not in VALID_STATUSES:
                    raise UndoLogError(
                        f"Invalid status at line {line_number}."
                    )

                operations[operation_id]["status"] = status
                operations[operation_id]["reason"] = event.get(
                    "reason", ""
                )

            else:
                raise UndoLogError(
                    f"Unknown event at line {line_number}."
                )

    except OSError as error:
        raise UndoLogError(
            f"Unable to read undo log: {error}"
        ) from error

    return list(operations.values())


def _copy_exclusively(source, destination):
    """
    Restore a file without overwriting an existing destination.
    """

    created = False

    try:
        with source.open("rb") as source_file:
            with destination.open("xb") as destination_file:
                created = True
                shutil.copyfileobj(source_file, destination_file)
                destination_file.flush()
                os.fsync(destination_file.fileno())

    except Exception:
        if created:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def restore_operation(operation, logger):
    operation_id = operation["operation_id"]

    original = Path(operation["original_path"])
    destination = Path(operation["destination_path"])
    expected_hash = operation["file_hash"]

    def result(status, reason, success):
        return UndoResult(
            operation_id=operation_id,
            original_path=original,
            destination_path=destination,
            status=status,
            reason=reason,
            success=success,
        )

    def update(status, reason):
        logger.update_status(operation_id, status, reason)
        return result(status, reason, status == "restored")

    try:
        original_exists = original.exists()
        destination_exists = destination.exists()

        # CASE 1: Both files exist.
        if original_exists and destination_exists:

            # Automatic recovery is permitted only if restoration
            # had already started before the interruption.
            if operation["status"] == "restoring":

                original_hash = calculate_hash(original)
                destination_hash = calculate_hash(destination)

                if (
                    original_hash == expected_hash
                    and destination_hash == expected_hash
                ):
                    destination.unlink()

                    return update(
                        "restored",
                        "Recovery completed. Both files matched the "
                        "expected hash; redundant destination copy "
                        "was removed."
                    )

            # For all other statuses, preserve both files.
            return update(
                "restore_failed",
                "Both paths exist. Neither file was modified."
            )

        # CASE 2: Original exists, destination is missing.
        # The original may already have been restored before interruption.
        if original_exists and not destination_exists:

            if calculate_hash(original) != expected_hash:
                return update(
                    "restore_failed",
                    "Original file content has changed."
                )

            return update(
                "restored",
                "Original file is already present."
            )

        # CASE 3: Neither file exists.
        if not original_exists and not destination_exists:
            return update(
                "restore_failed",
                "Both original and destination files are missing."
            )

        # CASE 4: Original is missing, destination exists.
        # Verify the destination before restoring it.
        if calculate_hash(destination) != expected_hash:
            return update(
                "restore_failed",
                "Destination hash does not match the original file."
            )

        original.parent.mkdir(parents=True, exist_ok=True)

        # Record restoration intent before copying.
        logger.update_status(
            operation_id,
            "restoring",
            "Restoration started."
        )

        # Create the original file exclusively.
        _copy_exclusively(destination, original)

        # Verify the restored file.
        if calculate_hash(original) != expected_hash:
            original.unlink(missing_ok=True)

            return update(
                "restore_failed",
                "Restored file failed SHA-256 verification."
            )

        # Delete destination only after successful verification.
        destination.unlink()

        return update(
            "restored",
            "File successfully restored."
        )

    except FileExistsError:
        return update(
            "restore_failed",
            "Original path became occupied during restoration."
        )

    except OSError as error:
        return update(
            "restore_failed",
            f"Filesystem error during restoration: {error}"
        )


def undo_execution(log_path):
    operations = read_undo_log(log_path)
    logger = UndoLogger(log_path)

    results = []

    # Reverse execution order is important.
    for operation in reversed(operations):

        # Already restored operations do not need another restoration.
        if operation["status"] == "restored":
            continue

        # Do not skip failed operations. Inspect their actual paths.
        result = restore_operation(operation, logger)
        results.append(result)

    return results