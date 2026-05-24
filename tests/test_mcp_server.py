from datetime import datetime, timezone

from glm_cellphone.mcp_server import _artifact_payload, _summarize_logs
from glm_cellphone.schemas import ArtifactRecord


def test_summarize_logs_extracts_latest_step_and_action():
    summary = _summarize_logs(
        "\n".join(
            [
                "[time] step 1/20: begin",
                "[time] step 1/20: action={'_metadata': 'do', 'action': 'Launch'}",
                "[time] step 2/20: begin",
            ]
        )
    )

    assert summary["current_step"] == {"index": 2, "max": 20}
    assert summary["last_action"] == "{'_metadata': 'do', 'action': 'Launch'}"


def test_artifact_payload_keeps_relative_url_by_default():
    artifact = ArtifactRecord(
        id="artifact-1",
        job_id="job-1",
        kind="log",
        label="Run log",
        path="/tmp/run.log",
        url="/artifacts/job-1/run.log",
        content_type="text/plain",
        created_at=datetime.now(timezone.utc),
    )

    payload = _artifact_payload(artifact)

    assert payload["url"] == "/artifacts/job-1/run.log"
    assert "path" not in payload
