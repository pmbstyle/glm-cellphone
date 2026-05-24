from datetime import datetime, timezone

from fastapi.testclient import TestClient

from glm_cellphone import api
from glm_cellphone.artifacts import ArtifactRecorder
from glm_cellphone.schemas import JobRecord


def test_artifact_recorder_snapshot_is_a_copy(tmp_path):
    recorder = ArtifactRecorder(tmp_path, "job-1")
    first = recorder.add_text("one.txt", "one", kind="log", label="One")

    snapshot = recorder.snapshot()
    snapshot.clear()

    assert recorder.snapshot() == [first]


def test_live_job_artifacts_endpoint_reads_recorder(tmp_path):
    client = TestClient(api.app)
    job_id = "live-artifacts-test"
    now = datetime.now(timezone.utc)
    recorder = ArtifactRecorder(tmp_path, job_id)
    recorder.add_text("request.txt", "hello", kind="request", label="Request")
    api.jobs[job_id] = JobRecord(
        id=job_id,
        status="running",
        task="test",
        created_at=now,
        updated_at=now,
    )
    api.job_artifacts[job_id] = recorder

    try:
        response = client.get(f"/jobs/{job_id}/artifacts")
    finally:
        api.jobs.pop(job_id, None)
        api.job_artifacts.pop(job_id, None)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert data["artifacts"][0]["label"] == "Request"
