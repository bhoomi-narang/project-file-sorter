import pytest

from file_sorter.register_loader import (
    RegisterError,
    load_project_register,
)


def create_csv(tmp_path, content):
    file_path = tmp_path / "register.csv"
    file_path.write_text(content, encoding="utf-8")
    return file_path


def test_load_valid_register(tmp_path):
    file_path = create_csv(
        tmp_path,
        "project_no,status\n"
        "925173,active\n"
        "925180,active\n"
        "825104,closed\n"
    )

    result = load_project_register(file_path)

    assert result == {
        "925173": "active",
        "925180": "active",
        "825104": "closed",
    }


def test_missing_file(tmp_path):
    file_path = tmp_path / "missing.csv"

    with pytest.raises(RegisterError, match="not found"):
        load_project_register(file_path)


def test_invalid_headers(tmp_path):
    file_path = create_csv(
        tmp_path,
        "project,status\n925173,active\n"
    )

    with pytest.raises(RegisterError, match="headers"):
        load_project_register(file_path)


def test_invalid_project_number(tmp_path):
    file_path = create_csv(
        tmp_path,
        "project_no,status\n92517,active\n"
    )

    with pytest.raises(RegisterError, match="Invalid project number"):
        load_project_register(file_path)


def test_invalid_status(tmp_path):
    file_path = create_csv(
        tmp_path,
        "project_no,status\n925173,pending\n"
    )

    with pytest.raises(RegisterError, match="Invalid status"):
        load_project_register(file_path)


def test_duplicate_project_number(tmp_path):
    file_path = create_csv(
        tmp_path,
        "project_no,status\n"
        "925173,active\n"
        "925173,closed\n"
    )

    with pytest.raises(RegisterError, match="Duplicate"):
        load_project_register(file_path)


def test_empty_register(tmp_path):
    file_path = create_csv(
        tmp_path,
        "project_no,status\n"
    )

    with pytest.raises(RegisterError, match="no records"):
        load_project_register(file_path)


def test_whitespace_is_handled(tmp_path):
    file_path = create_csv(
        tmp_path,
        "project_no,status\n 925173 , ACTIVE \n"
    )

    result = load_project_register(file_path)

    assert result == {"925173": "active"}

def test_whitespace_in_headers(tmp_path):
    file_path = create_csv(
        tmp_path,
        " project_no , status \n"
        "925173,active\n"
    )

    result = load_project_register(file_path)

    assert result == {"925173": "active"}