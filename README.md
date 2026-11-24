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