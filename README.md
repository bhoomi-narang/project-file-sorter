# Project File Sorter

A Python-based utility that automatically organizes project files
according to project numbers and project status.

## Features

- Extract project numbers from filenames.
- Classify files using a project register.
- Identify exact duplicate files.
- Separate unknown and unsorted files.
- Archive files belonging to closed projects.
- Support dry-run execution.
- Prevent accidental file overwrites.
- Maintain an undo log for file restoration.
- Generate execution summaries.

## Technology Stack

- Python
- CSV
- Pytest
- Git

## Project Structure

```text
src/file_sorter/  Application source code
tests/            Automated tests
data/             Project register
inbox/            Input files
logs/             Execution and undo logs

## Development Progress

### Phase 0 — Project Setup
- Initialized Python project structure.
- Configured virtual environment and Git.
- Added project register.

### Phase 1 — Project Register Loader

- Implemented CSV-based project register loading.
- Added validation for CSV headers.
- Added six-digit project number validation.
- Added active/closed status validation.
- Added duplicate project number detection.
- Added handling for missing and malformed CSV files.
- Added UTF-8 BOM support.
- Added automated tests using pytest.
- Verified the loader against the actual project register.

**Test Results:** 9 tests passed.

### Phase 2 — Filename Parsing and Classification

- Implemented six-digit project number extraction using regular expressions.
- Added digit-boundary validation to prevent partial number matching.
- Implemented classification based on project register status.
- Added support for active, closed, unknown and unsorted categories.
- Added structured classification results using dataclasses.
- Added meaningful classification reasons.
- Added automated tests for filename extraction and classification.
- Verified edge cases involving multiple numbers and seven-digit numbers.

**Test Results:** 26 tests passed across Phases 1 and 2.

### ## Phase 3 — Duplicate Detection

Implemented duplicate detection using SHA-256 file hashing.

### Features
- Calculates SHA-256 hashes using chunk-based file reading.
- Identifies files with identical content.
- Uses deterministic canonical-file selection.
- Preserves files with similar names but different contents.
- Moves duplicate files into the `_duplicates` directory.
- Never deletes a duplicate before verifying that its copy is complete and valid.
- Handles destination filename collisions without overwriting existing files.
- Returns structured results for duplicate movement operations.

### Testing
- Unit tests cover hashing, duplicate identification, canonical selection, file movement, filename collisions, and error handling.
- All 20 Phase 3 tests pass.

##### Phase 4 — Safe File Movement

Implemented safe file movement according to the destination determined by the classification logic.

### Features
- Creates destination directories when required.
- Moves files without overwriting existing files.
- Routes filename conflicts to `_unsorted`.
- Generates unique destination names when fallback filenames already exist.
- Verifies file integrity using SHA-256 hashes.
- Preserves the source file when copying or verification fails.
- Handles missing files, permission errors, inaccessible directories, and failed source deletion.
- Returns structured movement results with status and reason information.

### Testing
- Unit tests cover successful movement, conflicts, integrity verification, missing files, permission failures, and error handling.
- All 16 Phase 4 tests pass.

##### Phase 5 — Dry Run and Command-Line Interface

Implemented a command-line interface using Python's argparse module.

### Features

- Dry-run is the default execution mode.
- Actual file movement requires the `--apply` argument.
- Displays planned source and destination paths.
- Displays classification reasons for planned movements.
- Integrates duplicate detection and duplicate movement.
- Supports custom inbox and project register paths.
- Uses the same execution planning and classification logic for dry-run and apply.
- Provides useful error messages for invalid arguments and missing paths.
- Displays execution results and movement counts.

### Usage

Dry-run:

    python -m file_sorter.main

Actual execution:

    python -m file_sorter.main --apply

Help:

    python -m file_sorter.main --help

Custom inbox:

    python -m file_sorter.main --inbox custom_folder

Custom register:

    python -m file_sorter.main --register custom.csv

### Testing

- Added CLI tests for dry-run behaviour.
- Added tests for actual file movement.
- Tested active, closed, unknown and duplicate files.
- Tested existing destination conflicts.
- Tested missing paths and invalid arguments.

### Phase 6 — Undo and Recovery Mechanism

Implemented an undo and recovery mechanism that allows users to reverse file-sorting operations.

### Implementation

- Generates a unique JSONL undo log for every real execution.
- Records original file paths, destination paths, file hashes, operation IDs, timestamps, and operation statuses.
- Tracks operations through `pending`, `completed`, `failed`, `restoring`, `restored`, and `restore_failed` states.
- Restores files to their original locations.
- Uses exclusive file creation to prevent overwriting existing files.
- Verifies file integrity using SHA-256 before and after restoration.
- Processes undo operations in reverse execution order.
- Handles interrupted operations using recorded operation states.
- Preserves conflicting files when safe restoration cannot be established.
- Supports retrying failed or interrupted restoration operations.

### Usage

Undo a previous sorting execution:

```cmd
python -m file_sorter.main --undo logs/undo_<timestamp>_<id>.jsonl
```

Replace the example log filename with the actual undo log generated during execution.

### Recovery and Safety

- Existing files are never blindly overwritten.
- Files with unexpected hashes are not restored.
- If both original and destination files exist during a normal undo operation, both are preserved.
- If restoration was interrupted after copying the original file back, the application can verify both copies and safely remove the redundant destination copy.
- Undo operations are recorded using append-only JSONL events.

**Limitation:** Filesystem operations and undo-log writes are not one atomic transaction. The recovery mechanism handles identified interruption scenarios but cannot guarantee recovery from every possible hardware, filesystem, or power failure.

### Testing

Added unit and integration tests covering restoration, duplicate restoration, multiple-file restoration, hash verification, overwrite prevention, and interrupted-operation recovery.

**Test result:** 89 tests passed.

## Phase 7 — Reporting, Logging and Integration Testing

### Execution Reporting

The application generates an execution summary containing:

- Total files scanned.
- Total files successfully moved.
- Number of duplicate files.
- Number of unknown project files.
- Number of unsorted files.
- Number of archived files.
- Number of active-project files.
- Number of conflicts.
- Number of failed operations.

The summary is calculated using actual movement results rather than planned operations.

### Exceptional File Reporting

Every file that does not successfully reach an active project folder is included in the exceptional-file report.

The report displays:
- Original filename.
- Actual destination, if available.
- Operation status.
- Reason for the outcome.

### Application Logging

Implemented timestamped application logging using Python's built-in `logging` module.

Application logs are stored in:

`logs/sorter_<timestamp>_<id>.log`

Logs record:
- Execution start and completion.
- Number of planned operations.
- Duplicate detection information.
- Successful file movements.
- Failed operations and error reasons.
- Execution summary.
- Undo execution details.

Application logs are maintained separately from JSONL undo logs. Existing undo logs are preserved.

### Integration Testing

Implemented `tests/test_integration.py` to test the complete assignment dataset using an isolated temporary directory.

The integration test verifies:
- Active project file movement.
- Closed project archival.
- Unknown project handling.
- Unsorted file handling.
- Exact duplicate detection and movement.
- Existing filename conflict handling.
- Preservation of existing files.
- Undo log generation.
- Application log generation.
- Execution summary accuracy.
- Removal of successfully moved files from the inbox.

### Test Results

- Reporter unit tests: 3 passed.
- Logging tests: 2 passed.
- Complete integration test: 1 passed.
- Full project test suite: **95 passed**.

All integration tests operate on temporary test data and do not modify the original assignment dataset.