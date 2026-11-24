import hashlib

import pytest

from pathlib import Path

from file_sorter.duplicate_detector import (
    calculate_file_hash,
    detect_duplicates,
    DuplicateDetectionError,
)


def create_file(directory, filename, content):
    file_path = directory / filename
    file_path.write_bytes(content)
    return file_path


# --------------------------------
# Hash calculation tests
# --------------------------------

def test_calculate_file_hash(tmp_path):

    file_path = create_file(
        tmp_path,
        "sample.txt",
        b"hello world"
    )

    expected_hash = hashlib.sha256(
        b"hello world"
    ).hexdigest()

    assert calculate_file_hash(file_path) == expected_hash


def test_same_content_produces_same_hash(tmp_path):

    first = create_file(
        tmp_path,
        "first.txt",
        b"identical content"
    )

    second = create_file(
        tmp_path,
        "second.txt",
        b"identical content"
    )

    assert calculate_file_hash(first) == calculate_file_hash(second)


def test_different_content_produces_different_hash(tmp_path):

    first = create_file(
        tmp_path,
        "first.txt",
        b"content one"
    )

    second = create_file(
        tmp_path,
        "second.txt",
        b"content two"
    )

    assert calculate_file_hash(first) != calculate_file_hash(second)


def test_missing_file_raises_error(tmp_path):

    file_path = tmp_path / "missing.txt"

    with pytest.raises(DuplicateDetectionError):
        calculate_file_hash(file_path)


def test_invalid_chunk_size(tmp_path):

    file_path = create_file(
        tmp_path,
        "sample.txt",
        b"hello"
    )

    with pytest.raises(ValueError):
        calculate_file_hash(file_path, chunk_size=0)


# --------------------------------
# Duplicate detection tests
# --------------------------------

def test_detect_exact_duplicates(tmp_path):

    first = create_file(
        tmp_path,
        "first.txt",
        b"same content"
    )

    second = create_file(
        tmp_path,
        "second.txt",
        b"same content"
    )

    result = detect_duplicates([first, second])

    assert len(result) == 1
    assert set(result[0].duplicate_files) == {second}


def test_different_content_not_duplicate(tmp_path):

    first = create_file(
        tmp_path,
        "first.txt",
        b"content one"
    )

    second = create_file(
        tmp_path,
        "second.txt",
        b"content two"
    )

    result = detect_duplicates([first, second])

    assert result == []


def test_no_duplicates_in_single_file(tmp_path):

    first = create_file(
        tmp_path,
        "first.txt",
        b"unique content"
    )

    result = detect_duplicates([first])

    assert result == []


def test_canonical_file_preferred_over_copy_suffix(tmp_path):

    original = create_file(
        tmp_path,
        "layout.dwg",
        b"same content"
    )

    copy = create_file(
        tmp_path,
        "layout (1).dwg",
        b"same content"
    )

    result = detect_duplicates([copy, original])

    assert len(result) == 1
    assert result[0].canonical_file == original
    assert result[0].duplicate_files == (copy,)


def test_multiple_duplicate_files(tmp_path):

    first = create_file(
        tmp_path,
        "layout.dwg",
        b"same content"
    )

    second = create_file(
        tmp_path,
        "layout (1).dwg",
        b"same content"
    )

    third = create_file(
        tmp_path,
        "layout (2).dwg",
        b"same content"
    )

    result = detect_duplicates([third, second, first])

    assert len(result) == 1
    assert result[0].canonical_file == first

    assert set(result[0].duplicate_files) == {
        second,
        third
    }


def test_empty_files_are_duplicates(tmp_path):

    first = create_file(
        tmp_path,
        "empty1.txt",
        b""
    )

    second = create_file(
        tmp_path,
        "empty2.txt",
        b""
    )

    result = detect_duplicates([first, second])

    assert len(result) == 1


def test_duplicate_detection_does_not_modify_files(tmp_path):

    first = create_file(
        tmp_path,
        "first.txt",
        b"same content"
    )

    second = create_file(
        tmp_path,
        "second.txt",
        b"same content"
    )

    detect_duplicates([first, second])

    assert first.exists()
    assert second.exists()

    assert first.read_bytes() == b"same content"
    assert second.read_bytes() == b"same content"


def test_repeated_path_is_not_treated_as_duplicate(tmp_path):

    first = create_file(
        tmp_path,
        "first.txt",
        b"same content"
    )

    result = detect_duplicates([first, first])

    assert result == []


def test_invalid_chunk_size_for_detection(tmp_path):

    first = create_file(
        tmp_path,
        "first.txt",
        b"hello"
    )

    with pytest.raises(ValueError):
        detect_duplicates([first], chunk_size=0)