import hashlib
import re

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_CHUNK_SIZE = 1024 * 1024

# Detects Windows-style duplicate suffixes such as:
# filename (1).pdf
# filename (2).dwg
COPY_SUFFIX_PATTERN = re.compile(r" \(\d+\)$")


class DuplicateDetectionError(Exception):
    """Raised when duplicate detection cannot complete safely."""


@dataclass(frozen=True)
class DuplicateGroup:
    """
    Represents a group of files with identical content.

    Attributes:
        file_hash: SHA-256 hash shared by all files.
        canonical_file: File selected to preserve.
        duplicate_files: Remaining identical files.
    """

    file_hash: str
    canonical_file: Path
    duplicate_files: tuple[Path, ...]


def calculate_file_hash(
    file_path: str | Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE
) -> str:
    """
    Calculate the SHA-256 hash of a file using chunked reading.
    """

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
    Return a deterministic sorting key.

    Files without copy suffixes are preferred.
    """

    stem = file_path.stem

    has_copy_suffix = bool(
        COPY_SUFFIX_PATTERN.search(stem)
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
    chunk_size: int = DEFAULT_CHUNK_SIZE
) -> bool:
    """
    Verify file contents byte-for-byte.

    Hash equality alone is not treated as absolute proof.
    """

    try:
        with first_file.open("rb") as first, second_file.open("rb") as second:

            while True:
                first_chunk = first.read(chunk_size)
                second_chunk = second.read(chunk_size)

                if first_chunk != second_chunk:
                    return False

                if not first_chunk:
                    return True

    except OSError as error:
        raise DuplicateDetectionError(
            f"Unable to compare '{first_file}' and '{second_file}': {error}"
        ) from error


def detect_duplicates(
    file_paths: Iterable[str | Path],
    chunk_size: int = DEFAULT_CHUNK_SIZE
) -> list[DuplicateGroup]:
    """
    Identify files with identical contents.

    Files are first grouped by SHA-256 hash. Files sharing
    a hash are then compared byte-for-byte.

    Returns:
        A list of DuplicateGroup objects.

    Raises:
        DuplicateDetectionError: If a file cannot be processed.
    """

    if chunk_size <= 0:
        raise ValueError("Chunk size must be greater than zero.")

    hash_groups = {}

    seen_paths = set()

    for file_path in file_paths:

        path = Path(file_path)

        # Avoid processing the same path more than once.
        if path in seen_paths:
            continue

        seen_paths.add(path)

        file_hash = calculate_file_hash(path, chunk_size)

        hash_groups.setdefault(file_hash, []).append(path)

    duplicate_groups = []

    for file_hash, files in hash_groups.items():

        if len(files) < 2:
            continue

        # Select a deterministic canonical candidate.
        sorted_files = sorted(files, key=_canonical_sort_key)

        canonical_file = sorted_files[0]

        confirmed_duplicates = []

        for candidate in sorted_files[1:]:

            if _files_are_identical(
                canonical_file,
                candidate,
                chunk_size
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