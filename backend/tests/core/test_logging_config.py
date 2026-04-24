import logging

from app.core.logging_config import configure_logging


def test_configure_logging_emits_app_info_logs_to_stdout(capsys) -> None:  # noqa: ANN001
    configure_logging(level="INFO")

    logger = logging.getLogger("app.services.transcription.nemo_provider")
    logger.info("backend logging is visible")

    captured = capsys.readouterr()
    assert "backend logging is visible" in captured.out


def test_configure_logging_is_idempotent(capsys) -> None:  # noqa: ANN001
    configure_logging(level="INFO")
    configure_logging(level="INFO")

    logger = logging.getLogger("app.api.routes.session")
    logger.info("log once")

    captured = capsys.readouterr()
    assert captured.out.count("log once") == 1
