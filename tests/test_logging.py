from pathlib import Path

from file_sorter.main import setup_execution_logger


def test_setup_execution_logger_creates_log_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    logger = setup_execution_logger()

    logger.info("Test execution started.")
    logger.error("Test error.")

    handlers = logger.handlers

    for handler in handlers:
        handler.flush()

    log_files = list((tmp_path / "logs").glob("sorter_*.log"))

    assert len(log_files) == 1

    content = log_files[0].read_text(encoding="utf-8")

    assert "Test execution started." in content
    assert "Test error." in content
    assert "INFO" in content
    assert "ERROR" in content
    assert "202" in content


def test_execution_logger_does_not_overwrite_existing_logs(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    first_logger = setup_execution_logger()
    first_logger.info("First execution.")

    first_files = list((tmp_path / "logs").glob("sorter_*.log"))

    second_logger = setup_execution_logger()
    second_logger.info("Second execution.")

    second_files = list((tmp_path / "logs").glob("sorter_*.log"))

    assert len(first_files) == 1
    assert len(second_files) == 2