import logging

from glm_cellphone.logs import TaskLog, capture_prints


def test_capture_prints_captures_print_without_logging_noise(caplog):
    task_log = TaskLog()

    with capture_prints(task_log):
        print("model", "output", end="")
        logging.getLogger("test").warning("server log")

    assert task_log.text() == "model output"
    assert "server log" in caplog.text
