import logging
import uuid
from datetime import datetime

from file_sorter.undo_manager import UndoLogger, undo_execution
import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from file_sorter.classifier import classify_filename
from file_sorter.duplicate_detector import (
    DuplicateDetectionError,
    DuplicateGroup,
    detect_duplicates,
    move_duplicates,
)
from file_sorter.file_manager import manage_file
from file_sorter.register_loader import (
    RegisterError,
    load_project_register,
)

from file_sorter.reporter import (
    normalize_result,
    generate_summary,
    display_summary,
    display_exceptional_files,
)


@dataclass(frozen=True)
class PlannedOperation:
    """Represents one planned file movement."""

    source: Path
    destination: Path
    intended_destination: Path
    reason: str
    operation_type: str


@dataclass(frozen=True)
class ExecutionPlan:
    """Contains all operations required to sort the inbox."""

    duplicate_groups: tuple[DuplicateGroup, ...]
    operations: tuple[PlannedOperation, ...]


def get_unique_path(path: Path) -> Path:
    """Return a unique path without overwriting existing files."""

    if not path.exists():
        return path

    counter = 1

    while True:
        candidate = path.with_name(
            f"{path.stem} ({counter}){path.suffix}"
        )

        if not candidate.exists():
            return candidate

        counter += 1


def build_execution_plan(
    inbox: Path,
    register_path: Path,
) -> ExecutionPlan:
    """
    Build a complete file movement plan.

    This function never moves, creates, or deletes files.
    """

    if not inbox.exists():
        raise FileNotFoundError(f"Inbox directory not found: {inbox}")

    if not inbox.is_dir():
        raise NotADirectoryError(f"Inbox path is not a directory: {inbox}")

    project_register = load_project_register(register_path)

    files = sorted(
        (path for path in inbox.iterdir() if path.is_file()),
        key=lambda path: path.name.casefold(),
    )

    duplicate_groups = detect_duplicates(files)

    duplicate_files = {
        duplicate
        for group in duplicate_groups
        for duplicate in group.duplicate_files
    }

    output_root = inbox.resolve().parent

    operations = []

    # Plan duplicate movements first.
    duplicate_directory = output_root / "_duplicates"

    for group in duplicate_groups:
        for duplicate in group.duplicate_files:
            destination = get_unique_path(
                duplicate_directory / duplicate.name
            )

            operations.append(
                PlannedOperation(
                    source=duplicate,
                    destination=destination,
                    intended_destination=destination,
                    reason=(
                        f"Exact duplicate of "
                        f"{group.canonical_file.name}. "
                        "Canonical file will be retained."
                    ),
                    operation_type="duplicate",
                )
            )

    # Classify every non-duplicate file.
    for source in files:

        if source in duplicate_files:
            continue

        classification = classify_filename(
            source.name,
            project_register,
        )

        intended_destination = (
            output_root
            / classification.destination
            / source.name
        )

        if intended_destination.exists():
            destination = get_unique_path(
                output_root / "_unsorted" / source.name
            )

            reason = (
                f"{classification.reason} "
                "Destination filename already exists. "
                "File will be routed to _unsorted."
            )

        else:
            destination = intended_destination
            reason = classification.reason

        operations.append(
            PlannedOperation(
                source=source,
                destination=destination,
                intended_destination=intended_destination,
                reason=reason,
                operation_type="classified",
            )
        )

    return ExecutionPlan(
        duplicate_groups=tuple(duplicate_groups),
        operations=tuple(operations),
    )


def display_plan(plan: ExecutionPlan) -> None:
    """Display planned movements without modifying files."""

    print("\n========== FILE MOVEMENT PLAN ==========\n")

    if not plan.operations:
        print("No files found. Nothing to process.")
        return

    for index, operation in enumerate(plan.operations, start=1):

        print(f"{index}. {operation.source}")
        print(f"   Destination : {operation.destination}")
        print(f"   Operation   : {operation.operation_type}")
        print(f"   Reason      : {operation.reason}")
        print()

    print("----------------------------------------")
    print(f"Total planned movements: {len(plan.operations)}")
    print("----------------------------------------")


def execute_plan(plan, undo_logger):
    """Execute the plan and collect structured results."""

    successful = 0
    failed = 0
    report_results = []

    logger = logging.getLogger("file_sorter")

    output_root = (
        plan.operations[0].source.resolve().parent.parent
        if plan.operations
        else Path.cwd()
    )

    duplicate_directory = output_root / "_duplicates"
    unsorted_directory = output_root / "_unsorted"

    logger.info("Starting sorting execution.")
    logger.info("Planned operations: %d", len(plan.operations))
    logger.info(
        "Duplicate groups detected: %d",
        len(plan.duplicate_groups),
    )

    print("\n========== EXECUTION RESULTS ==========\n")

    # Process duplicate files first.
    if plan.duplicate_groups:

        duplicate_results = move_duplicates(
            plan.duplicate_groups,
            duplicate_directory,
            undo_logger=undo_logger,
        )

        for result in duplicate_results:

            print(f"Source      : {result.source}")
            print(f"Destination : {result.destination}")
            print(f"Status      : {result.status}")
            print(f"Reason      : {result.reason}")
            print()

            report_results.append(
                normalize_result(
                    result,
                    is_duplicate=True,
                )
            )

            if result.success:
                successful += 1

                logger.info(
                    "Duplicate moved: %s -> %s",
                    result.source,
                    result.destination,
                )

            else:
                failed += 1

                logger.error(
                    "Duplicate movement failed: %s | Reason: %s",
                    result.source,
                    result.reason,
                )

    # Process normally classified files.
    for operation in plan.operations:

        # Duplicates were already processed above.
        if operation.operation_type == "duplicate":
            continue

        result = manage_file(
            source=operation.source,
            intended_destination=operation.intended_destination,
            unsorted_directory=unsorted_directory,
            undo_logger=undo_logger,
        )

        print(f"Source      : {result.source}")
        print(f"Destination : {result.destination}")
        print(f"Status      : {result.status}")
        print(f"Reason      : {result.reason}")
        print()

        report_results.append(
            normalize_result(result)
        )

        if result.success:
            successful += 1

            logger.info(
                "File moved: %s -> %s | Status: %s",
                result.source,
                result.destination,
                result.status,
            )

        else:
            failed += 1

            logger.error(
                "File movement failed: %s | Reason: %s",
                result.source,
                result.reason,
            )

    print("----------------------------------------")
    print(f"Successful movements: {successful}")
    print(f"Failed movements    : {failed}")
    print("----------------------------------------")

    logger.info(
        "Execution finished. Successful: %d, Failed: %d",
        successful,
        failed,
    )

    return successful, failed, report_results


def create_parser():
    parser = argparse.ArgumentParser(
        description="Project File Sorter"
    )

    action_group = parser.add_mutually_exclusive_group()

    action_group.add_argument(
        "--apply",
        action="store_true",
        help="Execute the sorting operation.",
    )

    action_group.add_argument(
        "--undo",
        type=Path,
        metavar="LOG_FILE",
        help="Restore files using an undo log.",
    )

    parser.add_argument(
        "--inbox",
        type=Path,
        default=Path("inbox"),
        help="Input directory.",
    )

    parser.add_argument(
        "--register",
        type=Path,
        default=Path("data/project_register.csv"),
        help="Project register CSV.",
    )

    return parser

def create_undo_log():
    logs_directory = Path("logs")
    logs_directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]

    return logs_directory / f"undo_{timestamp}_{unique_id}.jsonl"

def setup_execution_logger():
    """Create a timestamped application log for one execution."""

    logs_directory = Path("logs")
    logs_directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]

    log_file = logs_directory / (
        f"sorter_{timestamp}_{unique_id}.log"
    )

    logger = logging.getLogger("file_sorter")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Prevent duplicate handlers if main() is called more than once.
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

    file_handler = logging.FileHandler(
        log_file,
        encoding="utf-8",
    )

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""

    parser = create_parser()
    args = parser.parse_args(argv)

    logger = setup_execution_logger()

    logger.info("File sorter started.")

    # Handle undo operation.
    if args.undo:

        try:
            logger.info(
                "Starting undo operation using log: %s",
                args.undo,
            )

            results = undo_execution(args.undo)

            successful = 0
            failed = 0

            for result in results:

                print(
                    f"{result.status.upper()}: "
                    f"{result.original_path} - {result.reason}"
                )

                if result.success:
                    successful += 1

                    logger.info(
                        "File restored: %s",
                        result.original_path,
                    )

                else:
                    failed += 1

                    logger.error(
                        "File restoration failed: %s | Reason: %s",
                        result.original_path,
                        result.reason,
                    )

            print("\nUndo Summary")
            print(f"Restored: {successful}")
            print(f"Failed: {failed}")

            logger.info(
                "Undo execution completed. Restored: %d, Failed: %d",
                successful,
                failed,
            )

            return 1 if failed else 0

        except Exception as error:

            logger.exception("Undo operation failed.")

            print(
                f"Undo failed: {error}",
                file=sys.stderr,
            )

            return 1

    try:

        # Build the execution plan.
        plan = build_execution_plan(
            inbox=args.inbox,
            register_path=args.register,
        )

        logger.info(
            "Files scanned: %d",
            len(plan.operations),
        )

        display_plan(plan)

        # Dry run is the default behavior.
        if not args.apply:

            print("\nDRY RUN: No files were moved or modified.")
            print("Use --apply to execute these operations.")

            logger.info("Dry run completed. No files were moved.")

            return 0

        # Create an undo log before actual execution.
        undo_log_path = create_undo_log()
        undo_logger = UndoLogger(undo_log_path)

        print(f"\nUndo log created: {undo_log_path}")

        logger.info(
            "Undo log created: %s",
            undo_log_path,
        )

        # Execute the plan.
        successful, failed, report_results = execute_plan(
            plan,
            undo_logger,
        )

        # Generate execution summary.
        summary = generate_summary(
            report_results,
            total_scanned=len(plan.operations),
        )

        display_summary(summary)

        # Explain files that did not reach active project folders.
        display_exceptional_files(report_results)

        logger.info(
            "Execution summary: %s",
            summary,
        )

        if failed:

            print(
                "\nExecution completed with errors.",
                file=sys.stderr,
            )

            logger.warning(
                "Execution completed with %d failed operations.",
                failed,
            )

            return 1

        print("\nExecution completed successfully.")

        logger.info("Execution completed successfully.")

        return 0

    except (
        RegisterError,
        DuplicateDetectionError,
        FileNotFoundError,
        NotADirectoryError,
        PermissionError,
        OSError,
        ValueError,
    ) as error:

        logger.exception("Sorting execution failed.")

        print(
            f"\nERROR: {error}",
            file=sys.stderr,
        )

        return 2

if __name__ == "__main__":
    raise SystemExit(main())