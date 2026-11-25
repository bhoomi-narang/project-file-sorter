from pathlib import Path

import pytest

from file_sorter.main import (
    build_execution_plan,
    main,
)


def create_register(path: Path) -> Path:
    path.write_text(
        "project_no,status\n"
        "925173,active\n"
        "925181,active\n"
        "825104,closed\n",
        encoding="utf-8",
    )
    return path


def create_file(inbox: Path, name: str, content: str) -> Path:
    inbox.mkdir(parents=True, exist_ok=True)

    file_path = inbox / name
    file_path.write_text(content, encoding="utf-8")

    return file_path


def setup_project(tmp_path: Path):
    inbox = tmp_path / "inbox"
    register = tmp_path / "data" / "project_register.csv"

    register.parent.mkdir(parents=True)
    create_register(register)

    return inbox, register


def test_build_execution_plan(tmp_path):
    inbox, register = setup_project(tmp_path)

    create_file(
        inbox,
        "925173_layout.dwg",
        "layout",
    )

    plan = build_execution_plan(inbox, register)

    assert len(plan.operations) == 1
    assert plan.operations[0].destination == (
        tmp_path / "925173" / "925173_layout.dwg"
    )


def test_dry_run_does_not_move_files(tmp_path):
    inbox, register = setup_project(tmp_path)

    source = create_file(
        inbox,
        "925173_layout.dwg",
        "layout",
    )

    result = main([
        "--inbox", str(inbox),
        "--register", str(register),
    ])

    assert result == 0
    assert source.exists()
    assert not (tmp_path / "925173").exists()


def test_apply_moves_active_project_file(tmp_path):
    inbox, register = setup_project(tmp_path)

    source = create_file(
        inbox,
        "925173_layout.dwg",
        "layout",
    )

    result = main([
        "--apply",
        "--inbox", str(inbox),
        "--register", str(register),
    ])

    destination = (
        tmp_path / "925173" / "925173_layout.dwg"
    )

    assert result == 0
    assert not source.exists()
    assert destination.exists()
    assert destination.read_text(encoding="utf-8") == "layout"


def test_apply_archives_closed_project_file(tmp_path):
    inbox, register = setup_project(tmp_path)

    source = create_file(
        inbox,
        "825104_concept.psd",
        "concept",
    )

    result = main([
        "--apply",
        "--inbox", str(inbox),
        "--register", str(register),
    ])

    destination = (
        tmp_path / "_archive" / "825104" / "825104_concept.psd"
    )

    assert result == 0
    assert not source.exists()
    assert destination.exists()


def test_apply_routes_unknown_project(tmp_path):
    inbox, register = setup_project(tmp_path)

    source = create_file(
        inbox,
        "925999_layout.dwg",
        "unknown",
    )

    result = main([
        "--apply",
        "--inbox", str(inbox),
        "--register", str(register),
    ])

    destination = tmp_path / "_unknown" / source.name

    assert result == 0
    assert not source.exists()
    assert destination.exists()


def test_apply_moves_exact_duplicates(tmp_path):
    inbox, register = setup_project(tmp_path)

    original = create_file(
        inbox,
        "925181_layout.dwg",
        "same content",
    )

    duplicate = create_file(
        inbox,
        "925181_layout (1).dwg",
        "same content",
    )

    result = main([
        "--apply",
        "--inbox", str(inbox),
        "--register", str(register),
    ])

    canonical_destination = (
        tmp_path / "925181" / original.name
    )

    duplicate_destination = (
        tmp_path / "_duplicates" / duplicate.name
    )

    assert result == 0

    # Canonical file must be sorted into its project folder.
    assert canonical_destination.exists()
    assert canonical_destination.read_text(
        encoding="utf-8"
    ) == "same content"

    # Exact duplicate must be moved to _duplicates.
    assert duplicate_destination.exists()
    assert duplicate_destination.read_text(
        encoding="utf-8"
    ) == "same content"

    # Neither file should remain in the inbox.
    assert not original.exists()
    assert not duplicate.exists()


def test_existing_destination_is_not_overwritten(tmp_path):
    inbox, register = setup_project(tmp_path)

    source = create_file(
        inbox,
        "925173_layout.dwg",
        "incoming",
    )

    destination = tmp_path / "925173" / source.name
    destination.parent.mkdir(parents=True)
    destination.write_text("existing", encoding="utf-8")

    result = main([
        "--apply",
        "--inbox", str(inbox),
        "--register", str(register),
    ])

    fallback = tmp_path / "_unsorted" / source.name

    assert result == 0
    assert destination.read_text(encoding="utf-8") == "existing"
    assert fallback.read_text(encoding="utf-8") == "incoming"
    assert not source.exists()


def test_missing_inbox_returns_error(tmp_path):
    register = tmp_path / "project_register.csv"
    create_register(register)

    result = main([
        "--inbox", str(tmp_path / "missing"),
        "--register", str(register),
    ])

    assert result == 2


def test_missing_register_returns_error(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    result = main([
        "--inbox", str(inbox),
        "--register", str(tmp_path / "missing.csv"),
    ])

    assert result == 2


def test_invalid_argument_is_rejected():
    with pytest.raises(SystemExit) as error:
        main(["--invalid-option"])

    assert error.value.code == 2


def test_empty_inbox_dry_run(tmp_path):
    inbox, register = setup_project(tmp_path)
    inbox.mkdir()

    result = main([
        "--inbox", str(inbox),
        "--register", str(register),
    ])

    assert result == 0