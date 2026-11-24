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

### Phase 3 — Duplicate Detection

- Implemented SHA-256 file hashing.
- Added chunk-based file reading to reduce memory consumption.
- Implemented duplicate grouping based on file hashes.
- Added byte-for-byte verification for matching hashes.
- Added deterministic canonical-file selection.
- Prioritized filenames without Windows copy suffixes.
- Ensured duplicate detection never modifies or deletes files.
- Added automated tests for duplicate detection and hash calculation.

**Test Results:** 39 tests passed across Phases 1–3.