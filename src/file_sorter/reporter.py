from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class FileReport:
    """Normalized result of one file movement operation."""

    source: Path
    destination: Path | None
    status: str
    reason: str
    success: bool
    is_duplicate: bool = False


@dataclass(frozen=True)
class ExecutionSummary:
    """Summary of one sorting execution."""

    total_scanned: int
    total_moved: int
    duplicates: int
    unknown: int
    unsorted: int
    archived: int
    active_project: int
    conflicts: int
    failed: int


def normalize_result(result, is_duplicate=False) -> FileReport:
    """Convert a movement result into a consistent report record."""

    return FileReport(
        source=Path(result.source),
        destination=(
            Path(result.destination)
            if result.destination is not None
            else None
        ),
        status=result.status,
        reason=result.reason,
        success=result.success,
        is_duplicate=is_duplicate,
    )


def _get_destination_category(destination: Path | None) -> str:
    """Determine the destination category from the actual path."""

    if destination is None:
        return "failed"

    parent_name = destination.parent.name

    if parent_name == "_duplicates":
        return "duplicates"

    if parent_name == "_unknown":
        return "unknown"

    if parent_name == "_unsorted":
        return "unsorted"

    if parent_name == "_archive":
        return "archived"

    if destination.parent.parent.name == "_archive":
        return "archived"

    if parent_name.isdigit() and len(parent_name) == 6:
        return "active_project"

    return "other"


def generate_summary(
    results: Iterable[FileReport],
    total_scanned: int,
) -> ExecutionSummary:
    """Generate execution metrics from actual movement results."""

    results = list(results)

    total_moved = sum(
        1 for result in results if result.success
    )

    duplicates = sum(
        1
        for result in results
        if result.success and result.is_duplicate
    )

    unknown = 0
    unsorted = 0
    archived = 0
    active_project = 0
    conflicts = 0
    failed = 0

    for result in results:

        if not result.success:
            failed += 1
            continue

        category = _get_destination_category(result.destination)

        if category == "unknown":
            unknown += 1

        elif category == "unsorted":
            unsorted += 1

        elif category == "archived":
            archived += 1

        elif category == "active_project":
            active_project += 1

        if result.status == "conflict_routed":
            conflicts += 1

    return ExecutionSummary(
        total_scanned=total_scanned,
        total_moved=total_moved,
        duplicates=duplicates,
        unknown=unknown,
        unsorted=unsorted,
        archived=archived,
        active_project=active_project,
        conflicts=conflicts,
        failed=failed,
    )


def display_summary(summary: ExecutionSummary) -> None:
    """Print the execution summary."""

    print("\n" + "=" * 45)
    print("             EXECUTION SUMMARY")
    print("=" * 45)

    print(f"Total files scanned:       {summary.total_scanned}")
    print(f"Total files moved:         {summary.total_moved}")
    print(f"Duplicate files:           {summary.duplicates}")
    print(f"Unknown files:             {summary.unknown}")
    print(f"Unsorted files:            {summary.unsorted}")
    print(f"Archived files:            {summary.archived}")
    print(f"Active project files:      {summary.active_project}")
    print(f"Conflicts:                 {summary.conflicts}")
    print(f"Failed operations:         {summary.failed}")

    print("=" * 45)


def display_exceptional_files(
    results: Iterable[FileReport],
) -> None:
    """Explain every file that did not reach an active project folder."""

    print("\n" + "=" * 45)
    print("          EXCEPTIONAL FILE REPORT")
    print("=" * 45)

    found = False

    for result in results:

        category = _get_destination_category(result.destination)

        if result.success and category == "active_project":
            continue

        found = True

        print(f"\nFile: {result.source.name}")

        if result.destination is not None:
            print(f"Destination: {result.destination}")
        else:
            print("Destination: Not completed")

        print(f"Status: {result.status}")
        print(f"Reason: {result.reason}")

    if not found:
        print("No exceptional files.")

    print("=" * 45)