import json

import pytest

from file_sorter.undo_manager import (
    UndoError,
    UndoLogger,
    UndoLogError,
    read_undo_log,
    undo_execution,
)


def test_start_operation_records_pending_status(tmp_path):
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    log = tmp_path / "undo.jsonl"

    source.write_text("important data")

    logger = UndoLogger(log)

    operation_id = logger.start_operation(source, destination)

    operations = read_undo_log(log)

    assert len(operations) == 1
    assert operations[0]["operation_id"] == operation_id
    assert operations[0]["status"] == "pending"
    assert operations[0]["original_path"] == str(source.resolve())
    assert operations[0]["destination_path"] == str(destination.resolve())


def test_restore_completed_operation(tmp_path):
    source = tmp_path / "source.txt"
    destination = tmp_path / "sorted" / "source.txt"
    log = tmp_path / "undo.jsonl"

    source.write_text("important data")
    destination.parent.mkdir()

    logger = UndoLogger(log)
    operation_id = logger.start_operation(source, destination)

    destination.write_text(source.read_text())
    source.unlink()

    logger.update_status(operation_id, "completed")

    results = undo_execution(log)

    assert len(results) == 1
    assert results[0].success is True
    assert source.read_text() == "important data"
    assert not destination.exists()


def test_pending_operation_recovers_after_interruption(tmp_path):
    source = tmp_path / "source.txt"
    destination = tmp_path / "sorted" / "source.txt"
    log = tmp_path / "undo.jsonl"

    source.write_text("important data")
    destination.parent.mkdir()

    logger = UndoLogger(log)
    logger.start_operation(source, destination)

    # Simulate application interruption after source deletion.
    destination.write_text(source.read_text())
    source.unlink()

    results = undo_execution(log)

    assert results[0].success is True
    assert source.read_text() == "important data"
    assert not destination.exists()


def test_pending_operation_with_original_still_present(tmp_path):
    source = tmp_path / "source.txt"
    destination = tmp_path / "sorted" / "source.txt"
    log = tmp_path / "undo.jsonl"

    source.write_text("important data")

    logger = UndoLogger(log)
    logger.start_operation(source, destination)

    results = undo_execution(log)

    assert results[0].success is True
    assert source.exists()
    assert not destination.exists()


def test_existing_original_is_never_overwritten(tmp_path):
    source = tmp_path / "source.txt"
    destination = tmp_path / "sorted" / "source.txt"
    log = tmp_path / "undo.jsonl"

    source.write_text("original data")
    destination.parent.mkdir()

    logger = UndoLogger(log)
    operation_id = logger.start_operation(source, destination)

    destination.write_text("original data")
    logger.update_status(operation_id, "completed")

    # Simulate another file appearing at the original path.
    source.write_text("different user data")

    results = undo_execution(log)

    assert results[0].success is False
    assert source.read_text() == "different user data"
    assert destination.read_text() == "original data"


def test_missing_destination_is_reported(tmp_path):
    source = tmp_path / "source.txt"
    destination = tmp_path / "sorted" / "source.txt"
    log = tmp_path / "undo.jsonl"

    source.write_text("important data")

    logger = UndoLogger(log)
    logger.start_operation(source, destination)

    source.unlink()

    results = undo_execution(log)

    assert results[0].success is False
    assert results[0].status == "restore_failed"


def test_corrupt_json_log_is_rejected(tmp_path):
    log = tmp_path / "undo.jsonl"
    log.write_text("{invalid json}\n")

    with pytest.raises(UndoLogError):
        read_undo_log(log)


def test_missing_log_is_rejected(tmp_path):
    log = tmp_path / "missing.jsonl"

    with pytest.raises(UndoLogError):
        read_undo_log(log)


def test_invalid_status_is_rejected(tmp_path):
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"

    source.write_text("data")

    logger = UndoLogger(tmp_path / "undo.jsonl")

    operation_id = logger.start_operation(source, destination)

    with pytest.raises(ValueError):
        logger.update_status(operation_id, "unknown_status")


def test_hash_mismatch_prevents_restoration(tmp_path):
    source = tmp_path / "source.txt"
    destination = tmp_path / "sorted" / "source.txt"
    log = tmp_path / "undo.jsonl"

    source.write_text("correct data")
    destination.parent.mkdir()

    logger = UndoLogger(log)
    operation_id = logger.start_operation(source, destination)

    destination.write_text("modified data")
    source.unlink()

    logger.update_status(operation_id, "completed")

    results = undo_execution(log)

    assert results[0].success is False
    assert not source.exists()
    assert destination.read_text() == "modified data"

def test_both_existing_files_are_preserved(tmp_path):
    source = tmp_path / "source.txt"
    destination = tmp_path / "sorted" / "source.txt"
    log = tmp_path / "undo.jsonl"

    source.write_text("same content")
    destination.parent.mkdir()
    destination.write_text("same content")

    logger = UndoLogger(log)

    operation_id = logger.start_operation(source, destination)
    logger.update_status(operation_id, "completed")

    results = undo_execution(log)

    assert results[0].success is False
    assert results[0].status == "restore_failed"

    assert source.read_text() == "same content"
    assert destination.read_text() == "same content"

def test_recovery_when_both_files_exist_with_matching_hash(tmp_path):
    original = tmp_path / "inbox" / "report.pdf"
    destination = tmp_path / "925173" / "report.pdf"
    log_path = tmp_path / "logs" / "undo.jsonl"

    original.parent.mkdir(parents=True)
    destination.parent.mkdir(parents=True)

    content = b"Original file content"

    original.write_bytes(content)

    logger = UndoLogger(log_path)

    operation_id = logger.start_operation(
        original,
        destination
    )

    logger.update_status(
        operation_id,
        "restoring",
        "Restoration started."
    )

    # Simulate an interrupted restoration:
    # the original has been copied back, but the destination
    # copy has not yet been deleted.
    destination.write_bytes(content)

    operations = read_undo_log(log_path)

    results = undo_execution(log_path)

    assert len(results) == 1
    assert results[0].operation_id == operation_id
    assert results[0].success is True
    assert results[0].status == "restored"

    assert original.exists()
    assert original.read_bytes() == content

    assert not destination.exists()

def test_recovery_preserves_both_files_when_hashes_differ(tmp_path):
    original = tmp_path / "inbox" / "report.pdf"
    destination = tmp_path / "925173" / "report.pdf"
    log_path = tmp_path / "logs" / "undo.jsonl"

    original.parent.mkdir(parents=True)
    destination.parent.mkdir(parents=True)

    original_content = b"Original file content"
    destination_content = b"Modified file content"

    original.write_bytes(original_content)

    logger = UndoLogger(log_path)

    logger.start_operation(
        original,
        destination
    )

    destination.write_bytes(destination_content)

    results = undo_execution(log_path)

    assert len(results) == 1
    assert results[0].success is False
    assert results[0].status == "restore_failed"

    # Neither file should be deleted or overwritten.
    assert original.read_bytes() == original_content
    assert destination.read_bytes() == destination_content

def test_incomplete_final_jsonl_record_is_ignored_and_repaired(tmp_path):
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    log = tmp_path / "undo.jsonl"
    source.write_text("recoverable data", encoding="utf-8")

    logger = UndoLogger(log)
    operation_id = logger.start_operation(source, destination)

    with log.open("ab") as file:
        file.write(b'{"event":"status","operation_id":"truncated')

    operations = read_undo_log(log)
    assert len(operations) == 1
    assert operations[0]["operation_id"] == operation_id
    assert operations[0]["status"] == "pending"

    # Opening the logger repairs the partial tail before the next append.
    repaired_logger = UndoLogger(log)
    repaired_logger.update_status(operation_id, "failed", "test event")

    operations = read_undo_log(log)
    assert operations[0]["status"] == "failed"
    assert operations[0]["reason"] == "test event"


def test_complete_malformed_jsonl_record_is_rejected(tmp_path):
    log = tmp_path / "undo.jsonl"
    log.write_bytes(b'{invalid json}\n')

    with pytest.raises(UndoLogError):
        read_undo_log(log)
