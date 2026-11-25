from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from file_sorter.undo_manager import UndoLogger
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path


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
) -> tuple[Path, str, str, str | None]:
    """
    Select a destination and copy the file without overwriting.

    If the intended destination is occupied, use _unsorted.
    If the fallback filename is occupied, generate a unique name.

    Exclusive file creation handles collisions that occur between
    checking the destination and actually creating it.
    """

    conflict_routed = intended_destination.exists()

    if conflict_routed:
        destination_base = unsorted_directory / source.name

        status = "conflict_routed"
        reason = (
            "Intended destination filename already exists. "
            "Incoming file routed to _unsorted."
        )
    else:
        destination_base = intended_destination

        status = "moved"
        reason = "File moved successfully."

    counter = 0

    while True:
        candidate = _unique_destination(destination_base, counter)

        operation_id = None

        try:
            if undo_logger is not None:
                operation_id = undo_logger.start_operation(
                    source,
                    candidate,
                )

            operation_id = None

            if undo_logger is not None:
                operation_id = undo_logger.start_operation(
                    source,
                    candidate,
                )

            try:
                _copy_and_verify(source, candidate, chunk_size)

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
                    "the original destination filename was occupied."
                )

            return candidate, status, reason, operation_id

        except FileExistsError:
            if not conflict_routed:
                # The intended destination became occupied after
                # the initial existence check.
                conflict_routed = True
                destination_base = unsorted_directory / source.name
                status = "conflict_routed"
                reason = (
                    "Intended destination became occupied during "
                    "processing. Incoming file routed to _unsorted."
                )
                counter = 0
                continue

            counter += 1


def manage_file(
    source: str | Path,
    intended_destination: str | Path,
    unsorted_directory: str | Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    undo_logger=None,
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

    except PermissionError as error:
        return failure(
            f"Permission denied while creating destination directories: {error}"
        )

    except OSError as error:
        return failure(
            f"Unable to prepare destination directories: {error}"
        )

    # Copy and verify before deleting the source.
    try:
        final_destination, status, reason, operation_id = (
    _copy_to_available_destination(
        source=source_path,
        intended_destination=intended_path,
        unsorted_directory=unsorted_path,
        chunk_size=chunk_size,
        undo_logger=undo_logger,
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
        if operation_id is not None:
            undo_logger.update_status(
                operation_id,
                "completed",
                "File successfully moved.",
            )

    except OSError as error:
        if operation_id is not None:
            undo_logger.update_status(
                operation_id,
                "failed",
                "Destination copy exists, but original deletion failed.",
            )

        return failure(
            f"Destination copy was verified, but source deletion failed: "
            f"{error}. Both files have been preserved.",
            destination=final_destination,
        )



    return FileMoveResult(
        source=source_path,
        destination=final_destination,
        status=status,
        reason=reason,
        success=True,
    )

