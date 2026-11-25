"""Filesystem path checks shared by planning and execution."""

from pathlib import Path


class PathSafetyError(ValueError):
    """Raised when a path traverses a symbolic link or junction."""


def is_link_or_junction(path: str | Path) -> bool:
    candidate = Path(path)
    if candidate.is_symlink():
        return True

    # pathlib added is_junction in newer Python versions. Keep support for
    # the project's declared Python 3.10 minimum.
    junction_check = getattr(candidate, "is_junction", None)
    return bool(junction_check and junction_check())


def is_occupied(path: str | Path) -> bool:
    """Treat dangling symbolic links as occupied directory entries."""
    candidate = Path(path)
    return candidate.exists() or is_link_or_junction(candidate)


def ensure_no_link_components(path: str | Path) -> None:
    """Reject links/junctions in every existing component of a path."""
    candidate = Path(path).absolute()
    components = [*reversed(candidate.parents), candidate]

    for component in components:
        if is_link_or_junction(component):
            raise PathSafetyError(
                f"Symbolic links and junctions are not supported in managed paths: {component}"
            )
