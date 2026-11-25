from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from file_sorter.undo_manager import UndoLogger
import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from file_sorter.path_safety import (
    PathSafetyError,
    ensure_no_link_components,
    is_occupied,
)


DEFAULT_CHUNK_SIZE = 1024 * 1024


class FileManagerError(Exception):
    """Base exception for file management operations."""


@dataclass(frozen=True)
class FileMoveResult:
    """Stores the result of a file movement operation."""

    source: Path
    destination: Path | None
    status: str
    reason: str
    success: bool


def calculate_file_hash(
    file_path: str | Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> str:
    """Calculate SHA-256 hash using memory-efficient chunk reading."""

    path = Path(file_path)

    if chunk_size <= 0:
        raise ValueError("Chunk size must be greater than zero.")

    if not path.is_file():
        raise FileManagerError(
            f"File does not exist or is not a regular file: {path}"
        )

    hasher = hashlib.sha256()

    try:
        with path.open("rb") as file:
            while chunk := file.read(chunk_size):
                hasher.update(chunk)

    except OSError as error:
        raise FileManagerError(
            f"Unable to read file '{path}': {error}"
        ) from error

    return hasher.hexdigest()


def _calculate_hash(path: Path, chunk_size: int) -> str:
    """Internal hash function that preserves filesystem exceptions."""

    hasher = hashlib.sha256()

    with path.open("rb") as file:
        while chunk := file.read(chunk_size):
            hasher.update(chunk)

    return hasher.hexdigest()


def _unique_destination(destination: Path, counter: int) -> Path:
    """Generate a collision-resistant alternative filename."""

    if counter == 0:
        return destination

    return destination.with_name(
        f"{destination.stem} ({counter}){destination.suffix}"
    )


def _copy_and_verify(
    source: Path,
    destination: Path,
    chunk_size: int,
) -> None:
    """
    Copy a file exclusively and verify its contents.

    The source hash is checked before and after copying.
    The destination hash must match the original source hash.
    """

    destination_created = False

    try:
        original_hash = _calculate_hash(source, chunk_size)

        with source.open("rb") as source_file:
            with destination.open("xb") as destination_file:
                destination_created = True

                shutil.copyfileobj(
                    source_file,
                    destination_file,
                    length=chunk_size,
                )

                destination_file.flush()
                os.fsync(destination_file.fileno())

        copied_hash = _calculate_hash(destination, chunk_size)

        if copied_hash != original_hash:
            raise FileManagerError(
                "File integrity verification failed: "
                "source and destination hashes do not match."
            )

        current_source_hash = _calculate_hash(source, chunk_size)

        if current_source_hash != original_hash:
            raise FileManagerError(
                "Source file changed during the copy operation."
            )

    except Exception as error:
        if destination_created:
            try:
                destination.unlink(missing_ok=True)

            except OSError as cleanup_error:
                raise FileManagerError(
                    f"Copy failed: {error}. "
                    f"Cleanup also failed: {cleanup_error}. "
                    f"Source: {source}. Destination: {destination}. "
                    "Both files may need manual inspection."
                ) from error

        raise



def _copy_to_available_destination(
    source: Path,
    intended_destination: Path,
    unsorted_directory: Path,
    chunk_size: int,
    undo_logger=None,
    duplicate_directory: Path | None = None,
) -> tuple[Path, str, str, str | None]:
    """
    Select a safe destination without overwriting existing files.

    Existing identical files are routed to _duplicates.
    Existing files with different contents are routed to _unsorted.
    """

    if duplicate_directory is None:
        duplicate_directory = (
            unsorted_directory.parent / "_duplicates"
        )

    def choose_destination():
        if not is_occupied(intended_destination):
            return (
                intended_destination,
                "moved",
                "File moved successfully.",
            )

        if (
            intended_destination.is_file()
            and not intended_destination.is_symlink()
        ):
            source_hash = _calculate_hash(source, chunk_size)
            existing_hash = _calculate_hash(
                intended_destination,
                chunk_size,
            )

            if source_hash == existing_hash:
                duplicate_directory.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                return (
                    duplicate_directory / source.name,
                    "duplicate_existing",
                    "Identical file already exists at the intended "
                    "destination. Incoming copy routed to _duplicates.",
                )

        return (
            unsorted_directory / source.name,
            "conflict_routed",
            "Destination filename already exists with different "
            "content. Incoming file routed to _unsorted.",
        )

    destination_base, status, reason = choose_destination()

    counter = 0

    while True:
        candidate = _unique_destination(
            destination_base,
            counter,
        )

        operation_id = None

        try:
            if undo_logger is not None:
                operation_id = undo_logger.start_operation(
                    source,
                    candidate,
                )

            try:
                _copy_and_verify(
                    source,
                    candidate,
                    chunk_size,
                )

            except Exception as error:
                if operation_id is not None:
                    undo_logger.update_status(
                        operation_id,
                        "failed",
                        f"Copy failed: {error}",
                    )
                raise

            if counter > 0:
                reason += (
                    " A unique filename was generated because "
                    "the destination filename was occupied."
                )

            return candidate, status, reason, operation_id

        except FileExistsError:
            # The attempted copy failed because the destination
            # became occupied. The inner exception handler has
            # already recorded the failed undo operation.

            if candidate == intended_destination:
                destination_base, status, reason = choose_destination()
                counter = 0
            else:
                counter += 1



def manage_file(
    source: str | Path,
    intended_destination: str | Path,
    unsorted_directory: str | Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    undo_logger=None,
    duplicate_directory: str | Path | None = None,
) -> FileMoveResult:
    """
    Safely move a file to its intended destination.

    Rules:
    - Never overwrite an existing file.
    - Route destination conflicts to _unsorted.
    - Generate unique names when fallback filenames exist.
    - Verify copied content before deleting the source.
    - Preserve the source if copying or verification fails.
    - Preserve both copies if source deletion fails.
    """

    source_path = Path(source)
    intended_path = Path(intended_destination)
    unsorted_path = Path(unsorted_directory)

    def failure(
        reason: str,
        destination: Path | None = None,
    ) -> FileMoveResult:
        return FileMoveResult(
            source=source_path,
            destination=destination,
            status="error",
            reason=reason,
            success=False,
        )

    if chunk_size <= 0:
        raise ValueError("Chunk size must be greater than zero.")

    # Validate the source file.
    try:
        if source_path.is_symlink():
            return failure("Symbolic-link sources are not supported.")

        if not source_path.exists():
            return failure("Source file does not exist.")

        if not source_path.is_file():
            return failure("Source path is not a regular file.")

        resolved_source = source_path.resolve()

        if resolved_source == intended_path.resolve():
            return failure(
                "Source and intended destination cannot be the same."
            )

        if resolved_source == unsorted_path.resolve():
            return failure(
                "Source cannot be the unsorted directory."
            )

    except PermissionError as error:
        return failure(f"Permission denied while accessing source: {error}")

    except OSError as error:
        return failure(f"Unable to access source: {error}")

    # Prepare destination directories.
    try:
        ensure_no_link_components(source_path)
        ensure_no_link_components(intended_path.parent)
        ensure_no_link_components(unsorted_path)

        intended_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        unsorted_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not intended_path.parent.is_dir():
            return failure(
                "Intended destination parent is not a directory."
            )

        if not unsorted_path.is_dir():
            return failure(
                "Unsorted destination is not a directory."
            )

    except PathSafetyError as error:
        return failure(str(error))

    except PermissionError as error:
        return failure(
            f"Permission denied while creating destination directories: {error}"
        )

    except OSError as error:
        return failure(
            f"Unable to prepare destination directories: {error}"
        )

    duplicate_path = (
        Path(duplicate_directory)
        if duplicate_directory is not None
        else unsorted_path.parent / "_duplicates"
    )

    try:
        ensure_no_link_components(duplicate_path)
    except PathSafetyError as error:
        return failure(str(error))

    # Copy and verify before deleting the source.
    try:
        final_destination, status, reason, operation_id = (
    _copy_to_available_destination(
        source=source_path,
        intended_destination=intended_path,
        unsorted_directory=unsorted_path,
        chunk_size=chunk_size,
        undo_logger=undo_logger,
        duplicate_directory=duplicate_path,
    )
)

    except PermissionError as error:
        return failure(f"Permission denied during file movement: {error}")

    except FileManagerError as error:
        return failure(f"File integrity or copy error: {error}")

    except OSError as error:
        return failure(f"Filesystem operation failed: {error}")

    # Delete the source only after successful copy and verification.
    try:
        source_path.unlink()
    except OSError as error:
        if operation_id is not None:
            try:
                undo_logger.update_status(
                    operation_id,
                    "failed",
                    "Destination copy exists, but original deletion failed.",
                )
            except Exception:
                pass

        return failure(
            f"Destination copy was verified, but source deletion failed: "
            f"{error}. Both files have been preserved.",
            destination=final_destination,
        )

    log_warning = None
    if operation_id is not None:
        try:
            undo_logger.update_status(
                operation_id,
                "completed",
                "File successfully moved.",
            )
        except Exception as error:
            # The file move has completed. Preserve the destination and
            # leave the durable pending record for recovery.
            log_warning = (
                f" Undo-log completion update failed: {error}. "
                "The pending record can be recovered during undo."
            )



    return FileMoveResult(
        source=source_path,
        destination=final_destination,
        status=status,
        reason=reason + (log_warning or ""),
        success=True,
    )

