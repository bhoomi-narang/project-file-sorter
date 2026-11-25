import pytest

import file_sorter.file_manager as file_manager

from file_sorter.file_manager import (
    FileMoveResult,
    calculate_file_hash,
    manage_file,
)


def create_source(tmp_path, content="sample content"):
    source = tmp_path / "inbox" / "sample.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content, encoding="utf-8")
    return source


def test_successful_file_movement(tmp_path):
    source = create_source(tmp_path)

    destination = tmp_path / "925173" / "sample.txt"
    unsorted = tmp_path / "_unsorted"

    result = manage_file(source, destination, unsorted)

    assert result.success
    assert result.status == "moved"
    assert result.destination == destination
    assert destination.read_text(encoding="utf-8") == "sample content"
    assert not source.exists()


def test_existing_destination_routes_to_unsorted(tmp_path):
    source = create_source(tmp_path, "incoming content")

    destination = tmp_path / "925173" / "sample.txt"
    destination.parent.mkdir(parents=True)

    destination.write_text("older version", encoding="utf-8")

    unsorted = tmp_path / "_unsorted"

    result = manage_file(source, destination, unsorted)

    fallback = unsorted / "sample.txt"

    assert result.success
    assert result.status == "conflict_routed"
    assert result.destination == fallback

    assert destination.read_text(encoding="utf-8") == "older version"
    assert fallback.read_text(encoding="utf-8") == "incoming content"
    assert not source.exists()


def test_existing_fallback_filename_generates_unique_name(tmp_path):
    source = create_source(tmp_path, "incoming content")

    destination = tmp_path / "925173" / "sample.txt"
    destination.parent.mkdir(parents=True)
    destination.write_text("existing project file", encoding="utf-8")

    unsorted = tmp_path / "_unsorted"
    unsorted.mkdir()

    existing_fallback = unsorted / "sample.txt"
    existing_fallback.write_text(
        "existing unsorted file",
        encoding="utf-8",
    )

    result = manage_file(source, destination, unsorted)

    unique_file = unsorted / "sample (1).txt"

    assert result.success
    assert result.destination == unique_file
    assert unique_file.read_text(encoding="utf-8") == "incoming content"

    assert existing_fallback.read_text(
        encoding="utf-8"
    ) == "existing unsorted file"

    assert destination.read_text(
        encoding="utf-8"
    ) == "existing project file"


def test_missing_source_returns_error(tmp_path):
    source = tmp_path / "missing.txt"

    result = manage_file(
        source,
        tmp_path / "925173" / "missing.txt",
        tmp_path / "_unsorted",
    )

    assert not result.success
    assert result.status == "error"
    assert "does not exist" in result.reason


def test_directory_cannot_be_moved_as_file(tmp_path):
    source = tmp_path / "folder"
    source.mkdir()

    result = manage_file(
        source,
        tmp_path / "925173" / "folder",
        tmp_path / "_unsorted",
    )

    assert not result.success
    assert "regular file" in result.reason


def test_empty_file_moves_successfully(tmp_path):
    source = create_source(tmp_path, "")
    source.write_bytes(b"")

    destination = tmp_path / "925173" / "sample.txt"

    result = manage_file(
        source,
        destination,
        tmp_path / "_unsorted",
    )

    assert result.success
    assert destination.read_bytes() == b""
    assert not source.exists()


def test_file_integrity_is_preserved(tmp_path):
    source = create_source(tmp_path, "A" * 10000)

    original_hash = calculate_file_hash(source)

    destination = tmp_path / "925173" / "sample.txt"

    result = manage_file(
        source,
        destination,
        tmp_path / "_unsorted",
        chunk_size=128,
    )

    assert result.success
    assert calculate_file_hash(destination) == original_hash


def test_source_and_destination_cannot_be_same(tmp_path):
    source = create_source(tmp_path)

    result = manage_file(
        source,
        source,
        tmp_path / "_unsorted",
    )

    assert not result.success
    assert "same" in result.reason
    assert source.exists()


def test_destination_directories_are_created(tmp_path):
    source = create_source(tmp_path)

    destination = (
        tmp_path / "nested" / "project" / "sample.txt"
    )

    unsorted = tmp_path / "nested" / "_unsorted"

    result = manage_file(source, destination, unsorted)

    assert result.success
    assert destination.exists()
    assert not source.exists()


def test_result_contains_expected_fields(tmp_path):
    source = create_source(tmp_path)

    destination = tmp_path / "925173" / "sample.txt"

    result = manage_file(
        source,
        destination,
        tmp_path / "_unsorted",
    )

    assert isinstance(result, FileMoveResult)
    assert result.source == source
    assert result.destination == destination
    assert result.status == "moved"
    assert result.success
    assert result.reason


def test_permission_error_during_copy_preserves_source(
    tmp_path,
    monkeypatch,
):
    source = create_source(tmp_path)

    destination = tmp_path / "925173" / "sample.txt"

    def fail_copy(*args, **kwargs):
        raise PermissionError("Access denied")

    monkeypatch.setattr(
        file_manager.shutil,
        "copyfileobj",
        fail_copy,
    )

    result = manage_file(
        source,
        destination,
        tmp_path / "_unsorted",
    )

    assert not result.success
    assert "Permission denied" in result.reason
    assert source.exists()
    assert not destination.exists()


def test_inaccessible_destination_directory(
    tmp_path,
    monkeypatch,
):
    source = create_source(tmp_path)

    destination = tmp_path / "925173" / "sample.txt"

    original_mkdir = file_manager.Path.mkdir

    def fail_destination_mkdir(path, *args, **kwargs):
        if path == destination.parent:
            raise PermissionError("Directory access denied")

        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(
        file_manager.Path,
        "mkdir",
        fail_destination_mkdir,
    )

    result = manage_file(
        source,
        destination,
        tmp_path / "_unsorted",
    )

    assert not result.success
    assert "Permission denied" in result.reason
    assert source.exists()
    assert not destination.exists()


def test_integrity_failure_preserves_source(
    tmp_path,
    monkeypatch,
):
    source = create_source(tmp_path)

    destination = tmp_path / "925173" / "sample.txt"

    original_hash = file_manager._calculate_hash

    calls = {"count": 0}

    def corrupted_hash(path, chunk_size):
        calls["count"] += 1

        if calls["count"] == 2:
            return "incorrect-hash"

        return original_hash(path, chunk_size)

    monkeypatch.setattr(
        file_manager,
        "_calculate_hash",
        corrupted_hash,
    )

    result = manage_file(
        source,
        destination,
        tmp_path / "_unsorted",
    )

    assert not result.success
    assert "integrity verification failed" in result.reason.lower()
    assert source.exists()
    assert not destination.exists()


def test_source_is_preserved_if_deletion_fails(
    tmp_path,
    monkeypatch,
):
    source = create_source(tmp_path)

    destination = tmp_path / "925173" / "sample.txt"

    original_unlink = file_manager.Path.unlink

    def fail_source_unlink(path, *args, **kwargs):
        if path == source:
            raise PermissionError("Cannot delete source")

        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(
        file_manager.Path,
        "unlink",
        fail_source_unlink,
    )

    result = manage_file(
        source,
        destination,
        tmp_path / "_unsorted",
    )

    assert not result.success
    assert "source deletion" in result.reason.lower()

    assert source.exists()
    assert destination.exists()

    assert source.read_text(encoding="utf-8") == (
        destination.read_text(encoding="utf-8")
    )


def test_invalid_chunk_size_raises_error(tmp_path):
    source = create_source(tmp_path)

    with pytest.raises(ValueError):
        manage_file(
            source,
            tmp_path / "925173" / "sample.txt",
            tmp_path / "_unsorted",
            chunk_size=0,
        )


def test_existing_destination_is_never_overwritten(tmp_path):
    source = create_source(tmp_path, "incoming")

    destination = tmp_path / "925173" / "sample.txt"
    destination.parent.mkdir(parents=True)

    destination.write_text("existing", encoding="utf-8")

    unsorted = tmp_path / "_unsorted"

    result = manage_file(
        source,
        destination,
        unsorted,
    )

    fallback = unsorted / "sample.txt"

    assert result.success is True
    assert result.status == "conflict_routed"

    # Existing destination must remain unchanged.
    assert destination.read_text(encoding="utf-8") == "existing"

    # Incoming file must be preserved in _unsorted.
    assert fallback.exists()
    assert fallback.read_text(encoding="utf-8") == "incoming"

    # Original source must no longer exist after successful movement.
    assert not source.exists()