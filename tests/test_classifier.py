from pathlib import Path

import pytest

from file_sorter.classifier import (
    extract_project_numbers,
    classify_filename,
)


PROJECT_REGISTER = {
    "925173": "active",
    "925180": "active",
    "925181": "active",
    "825104": "closed",
    "825110": "active",
    "724112": "closed",
    "624130": "active",
    "625101": "active",
}


# -------------------------------
# Project number extraction tests
# -------------------------------

def test_extract_single_project_number():
    result = extract_project_numbers(
        "925173_Lighting_Layout_RevA.dwg"
    )

    assert result == ["925173"]


def test_extract_multiple_project_numbers():
    result = extract_project_numbers(
        "invoice_724112_and_925180.pdf"
    )

    assert result == ["724112", "925180"]


def test_extract_no_project_number():
    result = extract_project_numbers(
        "Site visit 12-03-2025.jpg"
    )

    assert result == []


def test_reject_seven_digit_number():
    result = extract_project_numbers(
        "PO-9251800.pdf"
    )

    assert result == []


def test_reject_six_digit_substring_inside_seven_digits():
    result = extract_project_numbers(
        "1925180_report.pdf"
    )

    assert result == []


def test_extract_number_next_to_letters():
    result = extract_project_numbers(
        "PO-925180.pdf"
    )

    assert result == ["925180"]


def test_repeated_project_number_occurrences():
    result = extract_project_numbers(
        "925173_revision_925173.dwg"
    )

    assert result == ["925173", "925173"]


def test_invalid_filename():
    with pytest.raises(ValueError):
        extract_project_numbers("")


# -------------------------------
# Classification tests
# -------------------------------

def test_classify_active_project():
    result = classify_filename(
        "925173_Lighting_Layout_RevA.dwg",
        PROJECT_REGISTER
    )

    assert result.category == "project"
    assert result.destination == Path("925173")
    assert result.project_numbers == ("925173",)


def test_classify_closed_project():
    result = classify_filename(
        "825104_concept_v3.psd",
        PROJECT_REGISTER
    )

    assert result.category == "archive"
    assert result.destination == Path("_archive") / "825104"


def test_classify_unknown_project():
    result = classify_filename(
        "925042_draft.dwg",
        PROJECT_REGISTER
    )

    assert result.category == "unknown"
    assert result.destination == Path("_unknown")


def test_classify_filename_without_project_number():
    result = classify_filename(
        "Fixture_catalogue_2025.pdf",
        PROJECT_REGISTER
    )

    assert result.category == "unsorted"
    assert result.destination == Path("_unsorted")


def test_classify_multiple_project_numbers():
    result = classify_filename(
        "invoice_724112_and_925180.pdf",
        PROJECT_REGISTER
    )

    assert result.category == "unsorted"
    assert result.destination == Path("_unsorted")


def test_classify_seven_digit_number():
    result = classify_filename(
        "PO-9251800.pdf",
        PROJECT_REGISTER
    )

    assert result.category == "unsorted"
    assert result.destination == Path("_unsorted")


def test_classification_reason():
    result = classify_filename(
        "825104.pdf",
        PROJECT_REGISTER
    )

    assert result.reason == "Project 825104 is closed."


def test_invalid_register_status():
    invalid_register = {
        "925173": "pending"
    }

    with pytest.raises(ValueError, match="Invalid status"):
        classify_filename(
            "925173_layout.dwg",
            invalid_register
        )