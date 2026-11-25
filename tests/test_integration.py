from pathlib import Path

from file_sorter.main import (
    build_execution_plan,
    execute_plan,
    setup_execution_logger,
)
from file_sorter.reporter import (
    generate_summary,
    normalize_result,
)
from file_sorter.undo_manager import UndoLogger


PROJECT_REGISTER = """project_no,status
925173,active
925180,active
925181,active
825104,closed
825110,active
724112,closed
624130,active
625101,active
"""


ASSIGNMENT_FILES = [
    "925181_Lighting_Layout_RevB (1).dwg",
    "125173_old_layout.dwg",
    "624130_render_01.jpg",
    "624130_render_02.jpg",
    "625101_kickoff.pptx",
    "724112_DIALux_export.pdf",
    "724112_Lighting Calc.pdf",
    "825104.pdf",
    "825104_concept_v3.psd",
    "825110 section details.pdf",
    "825110_section.dwg",
    "925042_draft.dwg",
    "925173 - Fixture Schedule.xlsx",
    "925173_Lighting_Layout_RevA (1).dwg",
    "925173_Lighting_Layout_RevA.dwg",
    "925180-site-photos.zip",
    "925181_Lighting_Layout_RevB.dwg",
    "925190-final-FINAL.pdf",
    "9251_misc.txt",
    "client email 925173.eml",
    "concept_v4_825104.psd",
    "Fixture_catalogue_2025.pdf",
    "invoice_724112_and_925180.pdf",
    "LCPL 925181 BOQ final.xlsx",
    "Meeting notes 925181.docx",
    "Ph 9822012345 contact.txt",
    "PO-9251800.pdf",
    "Proposal_925180_Client.docx",
    "README.txt",
    "Rev2_Elevation_925173.pdf",
    "Site visit 12-03-2025.jpg",
]


def create_assignment_dataset(root: Path):
    """Create the complete assignment dataset in a temporary directory."""

    inbox = root / "inbox"
    inbox.mkdir(parents=True)

    data_directory = root / "data"
    data_directory.mkdir()

    register_path = data_directory / "project_register.csv"
    register_path.write_text(
        PROJECT_REGISTER,
        encoding="utf-8",
    )

    # Create all 31 files with unique contents.
    for filename in ASSIGNMENT_FILES:
        content = f"Content of {filename}".encode("utf-8")

        (inbox / filename).write_bytes(content)

    # Make the two RevB drawings exact duplicates.
    canonical = inbox / "925181_Lighting_Layout_RevB.dwg"
    duplicate = inbox / "925181_Lighting_Layout_RevB (1).dwg"

    duplicate.write_bytes(canonical.read_bytes())

    # Create a same-name, different-content destination conflict.
    conflict_directory = root / "925180"
    conflict_directory.mkdir()

    existing_file = conflict_directory / "Proposal_925180_Client.docx"
    existing_file.write_bytes(b"Existing different file content")

    return inbox, register_path


def test_complete_assignment_integration(tmp_path, monkeypatch):
    """Test the complete assignment sorting workflow."""

    # Arrange: create an isolated assignment dataset.
    inbox, register_path = create_assignment_dataset(tmp_path)

    monkeypatch.chdir(tmp_path)

    # Configure application logging.
    logger = setup_execution_logger()

    # Build the actual execution plan.
    plan = build_execution_plan(
        inbox=inbox,
        register_path=register_path,
    )

    # Verify all input files were included in the plan.
    assert len(plan.operations) == 31

    # Verify the duplicate was detected.
    assert len(plan.duplicate_groups) == 1

    # Create a separate undo log.
    logs_directory = tmp_path / "logs"

    undo_log_path = logs_directory / "undo_test.jsonl"
    undo_logger = UndoLogger(undo_log_path)

    # Act: execute the real sorting operations.
    successful, failed, report_results = execute_plan(
        plan,
        undo_logger,
    )

    # Generate the actual execution summary.
    summary = generate_summary(
        report_results,
        total_scanned=len(plan.operations),
    )

    # Assert: execution results.
    assert failed == 0
    assert successful == 31

    # Assert: summary metrics.
    assert summary.total_scanned == 31
    assert summary.total_moved == 31
    assert summary.duplicates == 1
    assert summary.unknown == 3
    assert summary.unsorted == 8
    assert summary.archived == 5
    assert summary.active_project == 14
    assert summary.failed == 0

    # Assert: active project destinations.
    assert (tmp_path / "624130" / "624130_render_01.jpg").exists()
    assert (tmp_path / "625101" / "625101_kickoff.pptx").exists()
    assert (tmp_path / "925173" / "925173_Lighting_Layout_RevA.dwg").exists()
    assert (tmp_path / "925180" / "925180-site-photos.zip").exists()
    assert (tmp_path / "925181" / "925181_Lighting_Layout_RevB.dwg").exists()

    # Assert: closed projects go to archive.
    assert (
        tmp_path / "_archive" / "724112" / "724112_DIALux_export.pdf"
    ).exists()

    assert (
        tmp_path / "_archive" / "825104" / "825104.pdf"
    ).exists()

    # Assert: unknown projects.
    assert (
        tmp_path / "_unknown" / "125173_old_layout.dwg"
    ).exists()

    assert (
        tmp_path / "_unknown" / "925042_draft.dwg"
    ).exists()

    assert (
        tmp_path / "_unknown" / "925190-final-FINAL.pdf"
    ).exists()

    # Assert: exact duplicate was moved, not deleted.
    assert (
        tmp_path
        / "_duplicates"
        / "925181_Lighting_Layout_RevB (1).dwg"
    ).exists()

    # Canonical file must be retained in the active project folder.
    assert (
        tmp_path
        / "925181"
        / "925181_Lighting_Layout_RevB.dwg"
    ).exists()

    # Assert: multiple project numbers go to unsorted.
    assert (
        tmp_path
        / "_unsorted"
        / "invoice_724112_and_925180.pdf"
    ).exists()

    # Assert: conflicting file is preserved in unsorted.
    assert (
        tmp_path
        / "_unsorted"
        / "Proposal_925180_Client.docx"
    ).exists()

    assert (
        tmp_path
        / "925180"
        / "Proposal_925180_Client.docx"
    ).read_bytes() == b"Existing different file content"

    # Assert: every original file was removed from inbox after successful move.
    assert list(inbox.iterdir()) == []

    # Assert: undo log was generated and contains records.
    assert undo_log_path.exists()
    assert undo_log_path.stat().st_size > 0

    # Assert: application log was generated.
    log_files = list(logs_directory.glob("sorter_*.log"))

    assert len(log_files) == 1

    log_content = log_files[0].read_text(encoding="utf-8")

    assert "Starting sorting execution." in log_content
    assert "Execution finished." in log_content

    logger.info("Integration test completed.")