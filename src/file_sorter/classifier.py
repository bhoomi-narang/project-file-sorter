import re
from dataclasses import dataclass
from pathlib import Path


# Matches exactly six digits that are not adjacent to other digits.
PROJECT_NUMBER_PATTERN = re.compile(r"(?<!\d)\d{6}(?!\d)")


@dataclass(frozen=True)
class FileClassification:
    """
    Represents the classification result of a file.

    Attributes:
        project_numbers: All valid project numbers found.
        category: Classification category.
        destination: Relative destination directory.
        reason: Explanation for the classification.
    """

    project_numbers: tuple[str, ...]
    category: str
    destination: Path
    reason: str


def extract_project_numbers(filename: str) -> list[str]:
    """
    Extract valid six-digit project numbers from a filename.

    A valid project number must contain exactly six digits
    and must not be adjacent to another digit.
    """

    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("Filename must be a non-empty string.")

    basename = Path(filename).name

    return PROJECT_NUMBER_PATTERN.findall(basename)


def classify_filename(
    filename: str,
    project_register: dict[str, str]
) -> FileClassification:
    """
    Classify a filename based on the project register.

    Returns:
        FileClassification containing the category,
        destination and classification reason.
    """

    project_numbers = extract_project_numbers(filename)

    # Case 1: No valid project number.
    if len(project_numbers) == 0:
        return FileClassification(
            project_numbers=(),
            category="unsorted",
            destination=Path("_unsorted"),
            reason="No valid six-digit project number found."
        )

    # Case 2: Multiple project numbers.
    if len(project_numbers) > 1:
        return FileClassification(
            project_numbers=tuple(project_numbers),
            category="unsorted",
            destination=Path("_unsorted"),
            reason="Multiple project numbers detected."
        )

    project_no = project_numbers[0]

    # Case 3: Project number does not exist in register.
    if project_no not in project_register:
        return FileClassification(
            project_numbers=(project_no,),
            category="unknown",
            destination=Path("_unknown"),
            reason=f"Project number {project_no} is not registered."
        )

    status = project_register[project_no]

    # Case 4: Project is closed.
    if status == "closed":
        return FileClassification(
            project_numbers=(project_no,),
            category="archive",
            destination=Path("_archive") / project_no,
            reason=f"Project {project_no} is closed."
        )

    # Case 5: Project is active.
    if status == "active":
        return FileClassification(
            project_numbers=(project_no,),
            category="project",
            destination=Path(project_no),
            reason=f"Project {project_no} is active."
        )

    # Defensive validation in case an invalid register dictionary
    # is supplied directly instead of using the register loader.
    raise ValueError(
        f"Invalid status '{status}' for project {project_no}."
    )