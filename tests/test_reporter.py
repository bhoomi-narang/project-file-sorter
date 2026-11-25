from pathlib import Path
from types import SimpleNamespace

from file_sorter.reporter import (
    normalize_result,
    generate_summary,
    display_summary,
    display_exceptional_files,
)


def make_result(
    source,
    destination,
    status="moved",
    reason="File moved successfully.",
    success=True,
):
    return SimpleNamespace(
        source=Path(source),
        destination=Path(destination) if destination else None,
        status=status,
        reason=reason,
        success=success,
    )


def test_generate_summary_counts_actual_destinations(tmp_path):
    root = tmp_path

    results = [
        normalize_result(
            make_result(
                root / "active.pdf",
                root / "925173" / "active.pdf",
            )
        ),
        normalize_result(
            make_result(
                root / "unknown.pdf",
                root / "_unknown" / "unknown.pdf",
            )
        ),
        normalize_result(
            make_result(
                root / "unsorted.pdf",
                root / "_unsorted" / "unsorted.pdf",
            )
        ),
        normalize_result(
            make_result(
                root / "archive.pdf",
                root / "_archive" / "825104" / "archive.pdf",
            )
        ),
        normalize_result(
            make_result(
                root / "duplicate.pdf",
                root / "_duplicates" / "duplicate.pdf",
            ),
            is_duplicate=True,
        ),
        normalize_result(
            make_result(
                root / "conflict.pdf",
                root / "_unsorted" / "conflict.pdf",
                status="conflict_routed",
            )
        ),
        normalize_result(
            make_result(
                root / "failed.pdf",
                None,
                status="error",
                reason="Permission denied.",
                success=False,
            )
        ),
    ]

    summary = generate_summary(results, total_scanned=8)

    assert summary.total_scanned == 8
    assert summary.total_moved == 6
    assert summary.duplicates == 1
    assert summary.unknown == 1
    assert summary.unsorted == 2
    assert summary.archived == 1
    assert summary.active_project == 1
    assert summary.conflicts == 1
    assert summary.failed == 1


def test_display_summary(capsys):
    results = []

    summary = generate_summary(results, total_scanned=5)

    display_summary(summary)

    output = capsys.readouterr().out

    assert "Total files scanned:       5" in output
    assert "Failed operations:         0" in output


def test_exceptional_files_include_reasons(tmp_path, capsys):
    results = [
        normalize_result(
            make_result(
                tmp_path / "active.pdf",
                tmp_path / "925173" / "active.pdf",
            )
        ),
        normalize_result(
            make_result(
                tmp_path / "unknown.pdf",
                tmp_path / "_unknown" / "unknown.pdf",
                reason="Project number is not registered.",
            )
        ),
    ]

    display_exceptional_files(results)

    output = capsys.readouterr().out

    assert "unknown.pdf" in output
    assert "Project number is not registered." in output
    assert "active.pdf" not in output