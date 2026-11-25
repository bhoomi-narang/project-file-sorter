
import pytest

from file_sorter.duplicate_detector import (
    DuplicateDetectionError,
    DuplicateMoveResult,
    calculate_file_hash,
    detect_duplicates,
    move_duplicates,
)


def test_calculate_file_hash(tmp_path):
    file = tmp_path / "sample.txt"
    file.write_text("hello world", encoding="utf-8")

    result = calculate_file_hash(file)

    assert len(result) == 64


def test_same_content_produces_same_hash(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"

    first.write_text("same content", encoding="utf-8")
    second.write_text("same content", encoding="utf-8")

    assert calculate_file_hash(first) == calculate_file_hash(second)


def test_different_content_produces_different_hash(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"

    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    assert calculate_file_hash(first) != calculate_file_hash(second)


def test_missing_file_raises_error(tmp_path):
    with pytest.raises(DuplicateDetectionError):
        calculate_file_hash(tmp_path / "missing.txt")


def test_invalid_chunk_size():
    with pytest.raises(ValueError):
        calculate_file_hash("sample.txt", chunk_size=0)


def test_detect_exact_duplicates(tmp_path):
    first = tmp_path / "report.txt"
    second = tmp_path / "report (1).txt"

    first.write_text("identical", encoding="utf-8")
    second.write_text("identical", encoding="utf-8")

    groups = detect_duplicates([first, second])

    assert len(groups) == 1
    assert groups[0].canonical_file == first
    assert second in groups[0].duplicate_files


def test_different_content_not_duplicate(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"

    first.write_text("content one", encoding="utf-8")
    second.write_text("content two", encoding="utf-8")

    assert detect_duplicates([first, second]) == []


def test_no_duplicates_in_single_file(tmp_path):
    file = tmp_path / "single.txt"
    file.write_text("content", encoding="utf-8")

    assert detect_duplicates([file]) == []


def test_canonical_file_preferred_over_copy_suffix(tmp_path):
    original = tmp_path / "report.txt"
    copy = tmp_path / "report (1).txt"

    original.write_text("same", encoding="utf-8")
    copy.write_text("same", encoding="utf-8")

    groups = detect_duplicates([copy, original])

    assert groups[0].canonical_file == original


def test_multiple_duplicate_files(tmp_path):
    first = tmp_path / "report.txt"
    second = tmp_path / "report (1).txt"
    third = tmp_path / "report (2).txt"

    for file in [first, second, third]:
        file.write_text("same content", encoding="utf-8")

    groups = detect_duplicates([first, second, third])

    assert len(groups) == 1
    assert len(groups[0].duplicate_files) == 2


def test_empty_files_are_duplicates(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"

    first.write_bytes(b"")
    second.write_bytes(b"")

    groups = detect_duplicates([first, second])

    assert len(groups) == 1


def test_duplicate_detection_does_not_modify_files(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"

    first.write_text("same", encoding="utf-8")
    second.write_text("same", encoding="utf-8")

    detect_duplicates([first, second])

    assert first.exists()
    assert second.exists()


def test_repeated_path_is_not_treated_as_duplicate(tmp_path):
    file = tmp_path / "sample.txt"
    file.write_text("content", encoding="utf-8")

    assert detect_duplicates([file, file]) == []


def test_invalid_chunk_size_for_detection():
    with pytest.raises(ValueError):
        detect_duplicates([], chunk_size=0)


def test_duplicate_files_are_moved(tmp_path):
    original = tmp_path / "report.txt"
    duplicate = tmp_path / "report (1).txt"
    duplicate_directory = tmp_path / "_duplicates"

    original.write_text("same content", encoding="utf-8")
    duplicate.write_text("same content", encoding="utf-8")

    groups = detect_duplicates([original, duplicate])

    results = move_duplicates(groups, duplicate_directory)

    moved_file = duplicate_directory / duplicate.name

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].status == "moved"

    assert original.exists()
    assert moved_file.exists()
    assert not duplicate.exists()

    assert moved_file.read_text(encoding="utf-8") == "same content"


def test_duplicate_movement_does_not_overwrite_existing_file(tmp_path):
    original = tmp_path / "report.txt"
    duplicate = tmp_path / "report (1).txt"
    duplicate_directory = tmp_path / "_duplicates"

    original.write_text("same content", encoding="utf-8")
    duplicate.write_text("same content", encoding="utf-8")

    duplicate_directory.mkdir()

    existing = duplicate_directory / duplicate.name
    existing.write_text("existing file", encoding="utf-8")

    groups = detect_duplicates([original, duplicate])

    results = move_duplicates(groups, duplicate_directory)

    unique_destination = duplicate_directory / "report (1) (1).txt"

    assert results[0].success is True
    assert unique_destination.exists()
    assert unique_destination.read_text(encoding="utf-8") == "same content"

    assert existing.read_text(encoding="utf-8") == "existing file"
    assert original.exists()
    assert not duplicate.exists()


def test_different_content_files_are_not_moved(tmp_path):
    original = tmp_path / "report.txt"
    second = tmp_path / "report (1).txt"
    duplicate_directory = tmp_path / "_duplicates"

    original.write_text("version one", encoding="utf-8")
    second.write_text("version two", encoding="utf-8")

    groups = detect_duplicates([original, second])

    results = move_duplicates(groups, duplicate_directory)

    assert results == []
    assert original.exists()
    assert second.exists()
    assert not duplicate_directory.exists()


def test_duplicate_movement_creates_directory(tmp_path):
    original = tmp_path / "report.txt"
    duplicate = tmp_path / "report (1).txt"
    duplicate_directory = tmp_path / "nested" / "_duplicates"

    original.write_text("same content", encoding="utf-8")
    duplicate.write_text("same content", encoding="utf-8")

    groups = detect_duplicates([original, duplicate])

    results = move_duplicates(groups, duplicate_directory)

    assert results[0].success is True
    assert duplicate_directory.exists()
    assert (duplicate_directory / duplicate.name).exists()


def test_duplicate_move_result_structure(tmp_path):
    original = tmp_path / "report.txt"
    duplicate = tmp_path / "report (1).txt"

    original.write_text("same content", encoding="utf-8")
    duplicate.write_text("same content", encoding="utf-8")

    groups = detect_duplicates([original, duplicate])

    results = move_duplicates(groups, tmp_path / "_duplicates")

    result = results[0]

    assert isinstance(result, DuplicateMoveResult)
    assert result.source == duplicate
    assert result.success is True
    assert result.status == "moved"
    assert result.destination is not None
    assert result.reason


def test_invalid_chunk_size_for_movement(tmp_path):
    with pytest.raises(ValueError):
        move_duplicates([], tmp_path / "_duplicates", chunk_size=0)
