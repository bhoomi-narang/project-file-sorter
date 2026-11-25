import json
from pathlib import Path

from file_sorter.main import main

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

def create_test_environment(tmp_path):
    """Create an isolated sorter environment for integration tests."""

    inbox = tmp_path / "inbox"
    inbox.mkdir()

    data_directory = tmp_path / "data"
    data_directory.mkdir()

    register = data_directory / "project_register.csv"
    register.write_text(
        "project_no,status\n"
        "925173,active\n",
        encoding="utf-8",
    )

    return inbox, register

def test_apply_and_undo_normal_file(tmp_path, monkeypatch):
    inbox, register = create_test_environment(tmp_path)

    source = inbox / "925173_report.pdf"
    source.write_text("Important project report")

    monkeypatch.chdir(tmp_path)

    # Execute sorting.
    result = main([
        "--apply",
        "--inbox", "inbox",
        "--register", "data/project_register.csv",
    ])

    assert result == 0

    sorted_file = tmp_path / "925173" / source.name
    assert sorted_file.exists()
    assert not source.exists()

    # Find generated undo log.
    log_files = list((tmp_path / "logs").glob("*.jsonl"))

    assert len(log_files) == 1

    # Verify operation was recorded.
    with log_files[0].open(encoding="utf-8") as file:
        events = [json.loads(line) for line in file]

    assert any(
        event.get("event") == "operation"
        and event.get("original_path") == str(source.resolve())
        for event in events
    )

    # Undo sorting.
    result = main(["--undo", str(log_files[0])])

    assert result == 0
    assert source.exists()
    assert not sorted_file.exists()
    assert source.read_text() == "Important project report"

def test_apply_and_undo_duplicate_file(tmp_path, monkeypatch):
    inbox, register = create_test_environment(tmp_path)

    original = inbox / "925173_report.pdf"
    duplicate = inbox / "925173_report (1).pdf"

    original.write_text("Identical report")
    duplicate.write_text("Identical report")

    monkeypatch.chdir(tmp_path)

    # Execute sorting.
    result = main([
        "--apply",
        "--inbox", "inbox",
        "--register", "data/project_register.csv",
    ])

    assert result == 0

    sorted_original = tmp_path / "925173" / original.name
    sorted_duplicate = tmp_path / "_duplicates" / duplicate.name

    assert sorted_original.exists()
    assert sorted_duplicate.exists()

    assert not original.exists()
    assert not duplicate.exists()

    log_files = list((tmp_path / "logs").glob("*.jsonl"))
    assert len(log_files) == 1

    # Undo sorting.
    result = main(["--undo", str(log_files[0])])

    assert result == 0

    assert original.exists()
    assert duplicate.exists()

    assert original.read_text() == duplicate.read_text()

    assert not sorted_original.exists()
    assert not sorted_duplicate.exists()

def test_apply_and_undo_multiple_files(tmp_path, monkeypatch):
    inbox, register = create_test_environment(tmp_path)

    files = {
        "925173_report.pdf": "Report content",
        "925173_layout.dwg": "Layout content",
        "925173_schedule.xlsx": "Schedule content",
    }

    for filename, content in files.items():
        (inbox / filename).write_text(content)

    monkeypatch.chdir(tmp_path)

    # Execute sorting.
    result = main([
        "--apply",
        "--inbox", "inbox",
        "--register", "data/project_register.csv",
    ])

    assert result == 0

    # Verify all files were sorted.
    for filename in files:
        assert (tmp_path / "925173" / filename).exists()
        assert not (inbox / filename).exists()

    log_files = list((tmp_path / "logs").glob("*.jsonl"))
    assert len(log_files) == 1

    # Undo sorting.
    result = main(["--undo", str(log_files[0])])

    assert result == 0

    # Verify every file was restored.
    for filename, content in files.items():
        restored_file = inbox / filename

        assert restored_file.exists()
        assert restored_file.read_text() == content

        assert not (tmp_path / "925173" / filename).exists()

def test_undo_does_not_overwrite_existing_original(tmp_path, monkeypatch):
    inbox, register = create_test_environment(tmp_path)

    source = inbox / "925173_report.pdf"
    source.write_text("Original content")

    monkeypatch.chdir(tmp_path)

    assert main([
        "--apply",
        "--inbox", "inbox",
        "--register", "data/project_register.csv",
    ]) == 0

    log_files = list((tmp_path / "logs").glob("*.jsonl"))
    assert len(log_files) == 1

    sorted_file = tmp_path / "925173" / source.name

    # Simulate another file appearing at the original location.
    source.write_text("Different content")

    result = main(["--undo", str(log_files[0])])

    assert result == 1

    # Neither file should be overwritten or deleted.
    assert source.read_text() == "Different content"
    assert sorted_file.read_text() == "Original content"

def test_file_symlink_in_inbox_is_rejected(tmp_path):
    inbox, register = setup_project(tmp_path)

    external_file = tmp_path / "external.txt"
    external_file.write_text(
        "Do not move this file",
        encoding="utf-8",
    )

    inbox.mkdir()

    link = inbox / "925173_external.txt"

    try:
        link.symlink_to(external_file)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"File symlinks are unavailable: {error}")

    with pytest.raises(
        ValueError,
        match="Symbolic links are not supported",
    ):
        build_execution_plan(inbox, register)

    assert external_file.exists()
    assert external_file.read_text(encoding="utf-8") == (
        "Do not move this file"
    )


def test_directory_symlink_in_inbox_is_rejected(tmp_path):
    inbox, register = setup_project(tmp_path)

    external_directory = tmp_path / "external"
    external_directory.mkdir()

    (external_directory / "important.txt").write_text(
        "External content",
        encoding="utf-8",
    )

    inbox.mkdir()

    link = inbox / "external_link"

    try:
        link.symlink_to(external_directory, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"Directory symlinks are unavailable: {error}")

    with pytest.raises(
        ValueError,
        match="Symbolic links are not supported",
    ):
        build_execution_plan(inbox, register)

    assert (
        external_directory / "important.txt"
    ).exists()


def test_inbox_itself_cannot_be_a_symlink(tmp_path):
    real_inbox = tmp_path / "real_inbox"
    real_inbox.mkdir()

    register = tmp_path / "project_register.csv"
    create_register(register)

    inbox_link = tmp_path / "inbox_link"

    try:
        inbox_link.symlink_to(
            real_inbox,
            target_is_directory=True,
        )
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"Directory symlinks are unavailable: {error}")

    with pytest.raises(
        ValueError,
        match="Inbox cannot be a symbolic link",
    ):
        build_execution_plan(inbox_link, register)

    assert real_inbox.is_dir()

def test_dry_run_routes_identical_existing_file_to_duplicates(tmp_path):
    inbox, register = setup_project(tmp_path)

    source = create_file(
        inbox,
        "925173_layout.dwg",
        "same content",
    )

    existing_destination = (
        tmp_path / "925173" / source.name
    )
    existing_destination.parent.mkdir(parents=True)
    existing_destination.write_text(
        "same content",
        encoding="utf-8",
    )

    plan = build_execution_plan(inbox, register)

    expected_destination = (
        tmp_path / "_duplicates" / source.name
    )

    assert len(plan.operations) == 1
    assert plan.operations[0].destination == expected_destination

    # Dry-run must not modify either file.
    assert source.exists()
    assert existing_destination.exists()
    assert not expected_destination.exists()

def test_dry_run_routes_different_existing_file_to_unsorted(tmp_path):
    inbox, register = setup_project(tmp_path)

    source = create_file(
        inbox,
        "925173_layout.dwg",
        "incoming content",
    )

    existing_destination = (
        tmp_path / "925173" / source.name
    )
    existing_destination.parent.mkdir(parents=True)
    existing_destination.write_text(
        "existing content",
        encoding="utf-8",
    )

    plan = build_execution_plan(inbox, register)

    expected_destination = (
        tmp_path / "_unsorted" / source.name
    )

    assert len(plan.operations) == 1
    assert plan.operations[0].destination == expected_destination

    # Dry-run must preserve both files.
    assert source.exists()
    assert existing_destination.exists()
    assert not expected_destination.exists()

def test_repeated_execution_routes_identical_file_to_duplicates(tmp_path):
    inbox, register = setup_project(tmp_path)

    source = create_file(
        inbox,
        "925173_layout.dwg",
        "same content",
    )

    existing_destination = tmp_path / "925173" / source.name
    existing_destination.parent.mkdir(parents=True)
    existing_destination.write_text("same content", encoding="utf-8")

    # Verify the dry-run decision.
    plan = build_execution_plan(inbox, register)

    expected_destination = tmp_path / "_duplicates" / source.name

    assert plan.operations[0].destination == expected_destination

    # Execute the same operation.
    result = main([
        "--apply",
        "--inbox", str(inbox),
        "--register", str(register),
    ])

    assert result == 0
    assert existing_destination.read_text(encoding="utf-8") == "same content"
    assert expected_destination.read_text(encoding="utf-8") == "same content"
    assert not source.exists()

def test_repeated_execution_routes_conflicting_file_to_unsorted(tmp_path):
    inbox, register = setup_project(tmp_path)

    source = create_file(
        inbox,
        "925173_layout.dwg",
        "incoming content",
    )

    existing_destination = tmp_path / "925173" / source.name
    existing_destination.parent.mkdir(parents=True)
    existing_destination.write_text("existing content", encoding="utf-8")

    # Verify the dry-run decision.
    plan = build_execution_plan(inbox, register)

    expected_destination = tmp_path / "_unsorted" / source.name

    assert plan.operations[0].destination == expected_destination

    # Execute the same operation.
    result = main([
        "--apply",
        "--inbox", str(inbox),
        "--register", str(register),
    ])

    assert result == 0
    assert existing_destination.read_text(encoding="utf-8") == "existing content"
    assert expected_destination.read_text(encoding="utf-8") == "incoming content"
    assert not source.exists()