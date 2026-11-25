from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from file_sorter.undo_manager import UndoLogger
import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_CHUNK_SIZE = 1024 * 1024

COPY_SUFFIX_PATTERN = re.compile(r" \(\d+\)$")


class DuplicateDetectionError(Exception):
    """Raised when duplicate detection or movement fails."""


@dataclass(frozen=True)
class DuplicateGroup:
    """Represents files having identical content."""

    file_hash: str
    canonical_file: Path
    duplicate_files: tuple[Path, ...]


@dataclass(frozen=True)
class DuplicateMoveResult:
    """Represents the result of moving a duplicate file."""

    source: Path
    destination: Path | None
    status: str
    reason: str
    success: bool


def calculate_file_hash(
    file_path: str | Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> str:
    """Calculate a file's SHA-256 hash using chunk-based reading."""

    path = Path(file_path)

    if chunk_size <= 0:
        raise ValueError("Chunk size must be greater than zero.")

    if not path.is_file():
        raise DuplicateDetectionError(
            f"File does not exist or is not a regular file: {path}"
        )

    hasher = hashlib.sha256()

    try:
        with path.open("rb") as file:
            while chunk := file.read(chunk_size):
                hasher.update(chunk)

    except OSError as error:
        raise DuplicateDetectionError(
            f"Unable to read file '{path}': {error}"
        ) from error

    return hasher.hexdigest()


def _canonical_sort_key(file_path: Path) -> tuple:
    """
    Prefer original filenames over copied filenames.

    Example preference:
        report.pdf
        report (1).pdf
        report (2).pdf
    """

    has_copy_suffix = bool(
        COPY_SUFFIX_PATTERN.search(file_path.stem)
    )

    return (
        has_copy_suffix,
        file_path.name.casefold(),
        str(file_path).casefold(),
        str(file_path),
    )


def _files_are_identical(
    first_file: Path,
    second_file: Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> bool:
    """Compare file contents byte by byte."""

    try:
        with first_file.open("rb") as first:
            with second_file.open("rb") as second:

                while True:
                    first_chunk = first.read(chunk_size)
                    second_chunk = second.read(chunk_size)

                    if first_chunk != second_chunk:
                        return False

                    if not first_chunk:
                        return True

    except OSError as error:
        raise DuplicateDetectionError(
            f"Unable to compare '{first_file}' and "
            f"'{second_file}': {error}"
        ) from error


def detect_duplicates(
    file_paths: Iterable[str | Path],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[DuplicateGroup]:
    """
    Detect files having exactly identical contents.

    The canonical file is selected deterministically.
    Duplicate files are returned but not moved or deleted.
    """

    if chunk_size <= 0:
        raise ValueError("Chunk size must be greater than zero.")

    hash_groups: dict[str, list[Path]] = {}
    seen_paths: set[Path] = set()

    for file_path in file_paths:
        path = Path(file_path)

        if path in seen_paths:
            continue

        seen_paths.add(path)

        file_hash = calculate_file_hash(path, chunk_size)

        hash_groups.setdefault(file_hash, []).append(path)

    duplicate_groups = []

    for file_hash, files in hash_groups.items():

        if len(files) < 2:
            continue

        sorted_files = sorted(
            files,
            key=_canonical_sort_key,
        )

        canonical_file = sorted_files[0]

        confirmed_duplicates = []

        for candidate in sorted_files[1:]:

            if _files_are_identical(
                canonical_file,
                candidate,
                chunk_size,
            ):
                confirmed_duplicates.append(candidate)

        if confirmed_duplicates:
            duplicate_groups.append(
                DuplicateGroup(
                    file_hash=file_hash,
                    canonical_file=canonical_file,
                    duplicate_files=tuple(confirmed_duplicates),
                )
            )

    return duplicate_groups


def _get_unique_destination(destination: Path) -> Path:
    """
    Generate a unique destination filename.

    Example:
        report.pdf
        report (1).pdf
        report (2).pdf
    """

    if not destination.exists():
        return destination

    counter = 1

    while True:
        candidate = destination.with_name(
            f"{destination.stem} ({counter}){destination.suffix}"
        )

        if not candidate.exists():
            return candidate

        counter += 1


def _move_duplicate(
    source: Path,
    destination_directory: Path,
    chunk_size: int,
    undo_logger=None,
) -> DuplicateMoveResult:
    """
    Safely move one duplicate file.

    Records the operation before copying.
    Verifies the destination before deleting the source.
    """

    destination = None
    destination_created = False
    operation_id = None

    try:
        if not source.is_file():
            return DuplicateMoveResult(
                source=source,
                destination=None,
                status="error",
                reason="Duplicate source file is missing or inaccessible.",
                success=False,
            )

        # Calculate original file hash.
        original_hash = calculate_file_hash(
            source,
            chunk_size,
        )

        destination_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Generate a unique destination.
        destination = _get_unique_destination(
            destination_directory / source.name
        )

        # Record the operation BEFORE copying.
        if undo_logger is not None:
            operation_id = undo_logger.start_operation(
                source,
                destination,
            )

        # Copy without overwriting.
        with source.open("rb") as source_file:
            with destination.open("xb") as destination_file:
                destination_created = True

                shutil.copyfileobj(
                    source_file,
                    destination_file,
                    length=chunk_size,
                )

        shutil.copystat(source, destination)

        # Verify destination hash.
        copied_hash = calculate_file_hash(
            destination,
            chunk_size,
        )

        if copied_hash != original_hash:
            raise DuplicateDetectionError(
                "SHA-256 verification failed after copying."
            )

        # Ensure source has not changed.
        current_source_hash = calculate_file_hash(
            source,
            chunk_size,
        )

        if current_source_hash != original_hash:
            raise DuplicateDetectionError(
                "Source file changed during duplicate movement."
            )

        # Delete source only after successful verification.
        try:
            source.unlink()

        except OSError as error:

            if operation_id is not None:
                undo_logger.update_status(
                    operation_id,
                    "failed",
                    "Destination copy exists, but source deletion failed.",
                )

            return DuplicateMoveResult(
                source=source,
                destination=destination,
                status="error",
                reason=(
                    f"Destination copy verified, but source deletion "
                    f"failed: {error}. Both copies have been preserved."
                ),
                success=False,
            )

        # Record successful movement.
        if operation_id is not None:
            undo_logger.update_status(
                operation_id,
                "completed",
                "Duplicate successfully moved.",
            )

        return DuplicateMoveResult(
            source=source,
            destination=destination,
            status="moved",
            reason="Exact duplicate moved to _duplicates.",
            success=True,
        )

    except Exception as error:

        # Record failed operation.
        if operation_id is not None:
            undo_logger.update_status(
                operation_id,
                "failed",
                str(error),
            )

        # Clean incomplete destination copies.
        if destination_created and destination is not None:
            try:
                destination.unlink(missing_ok=True)

            except OSError as cleanup_error:
                return DuplicateMoveResult(
                    source=source,
                    destination=destination,
                    status="error",
                    reason=(
                        f"Movement failed: {error}. "
                        f"Destination cleanup also failed: "
                        f"{cleanup_error}. Source was preserved."
                    ),
                    success=False,
                )

        return DuplicateMoveResult(
            source=source,
            destination=destination,
            status="error",
            reason=str(error),
            success=False,
        )


def move_duplicates(
    duplicate_groups: Iterable[DuplicateGroup],
    duplicate_directory: str | Path = "_duplicates",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    undo_logger=None,
) -> list[DuplicateMoveResult]:
    """
    Move every detected duplicate into the duplicate directory.

    Canonical files are never moved.
    Every duplicate movement can be recorded for undo.
    """

    if chunk_size <= 0:
        raise ValueError("Chunk size must be greater than zero.")

    duplicate_directory = Path(duplicate_directory)

    results = []

    for group in duplicate_groups:

        for duplicate_file in group.duplicate_files:

            if duplicate_file == group.canonical_file:
                continue

            result = _move_duplicate(
                source=duplicate_file,
                destination_directory=duplicate_directory,
                chunk_size=chunk_size,
                undo_logger=undo_logger,
            )

            results.append(result)

    return results
