from glm_cellphone.outcome import classify_step_outcome


def test_takeover_maps_to_needs_takeover():
    outcome = classify_step_outcome(
        action={"_metadata": "do", "action": "Take_over", "message": "captcha"},
        success=True,
        finished=False,
        message="captcha",
        takeover_requested=False,
        stop_on_takeover=True,
    )

    assert outcome.status == "needs_takeover"
    assert not outcome.retryable


def test_unsuccessful_finish_maps_to_failed():
    outcome = classify_step_outcome(
        action={"_metadata": "finish", "message": "Could not find a matching result."},
        success=True,
        finished=True,
        message="Could not find a matching result.",
        takeover_requested=False,
        stop_on_takeover=True,
    )

    assert outcome.status == "failed"


def test_normal_finish_maps_to_completed():
    outcome = classify_step_outcome(
        action={"_metadata": "finish", "message": "Task completed."},
        success=True,
        finished=True,
        message="Task completed.",
        takeover_requested=False,
        stop_on_takeover=True,
    )

    assert outcome.status == "completed"

