import csv
from pathlib import Path


class RegisterError(Exception):
    """Raised when the project register is missing or invalid."""


VALID_STATUSES = {"active", "closed"}


def load_project_register(file_path: str | Path) -> dict[str, str]:
    """
    Load and validate the project register CSV.

    Returns:
        Dictionary mapping project numbers to their statuses.

    Raises:
        RegisterError: If the file is missing, malformed,
                       or contains invalid project information.
    """

    path = Path(file_path)

    if not path.exists():
        raise RegisterError(f"Project register not found: {path}")

    if not path.is_file():
        raise RegisterError(f"Register path is not a file: {path}")

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)

            expected_headers = {"project_no", "status"}

            if reader.fieldnames is None:
                raise RegisterError("Project register is empty.")

            headers = [header.strip() for header in reader.fieldnames]

            if (
                len(headers) != len(set(headers))
                or set(headers) != expected_headers
            ):
                raise RegisterError(
                    "Invalid CSV headers. Expected: project_no,status"
                )

            register = {}

            for row_number, row in enumerate(reader, start=2):

                if None in row or any(value is None for value in row.values()):
                    raise RegisterError(
                        f"Malformed CSV row at line {row_number}."
                    )

                project_no = row["project_no"].strip()
                status = row["status"].strip().lower()

                if not project_no or not status:
                    raise RegisterError(
                        f"Empty project number or status at line {row_number}."
                    )

                if not project_no.isdigit() or len(project_no) != 6:
                    raise RegisterError(
                        f"Invalid project number '{project_no}' "
                        f"at line {row_number}. Expected six digits."
                    )

                if status not in VALID_STATUSES:
                    raise RegisterError(
                        f"Invalid status '{status}' at line {row_number}. "
                        f"Allowed statuses: active, closed."
                    )

                if project_no in register:
                    raise RegisterError(
                        f"Duplicate project number '{project_no}' "
                        f"at line {row_number}."
                    )

                register[project_no] = status

            if not register:
                raise RegisterError("Project register contains no records.")

            return register

    except UnicodeDecodeError as error:
        raise RegisterError("Project register must use UTF-8 encoding.") from error

    except csv.Error as error:
        raise RegisterError(f"Invalid CSV format: {error}") from error

    except OSError as error:
        raise RegisterError(f"Unable to read project register: {error}") from error