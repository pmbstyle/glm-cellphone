# GLM Cellphone

Local HTTP service for running AutoGLM phone-agent tasks against a connected Android
device.

The service wraps the Open-AutoGLM phone agent loop:

1. Capture the current phone screen over ADB.
2. Send the screenshot and task context to `autoglm-phone-multilingual`.
3. Execute the returned phone action over ADB.
4. Repeat until the model returns `finish(...)`, asks for takeover, or reaches the
   configured step limit.

<p align="center">
  <a href="https://www.youtube.com/watch?v=yzqvaPJY4t0">
    <img src="https://img.youtube.com/vi/yzqvaPJY4t0/maxresdefault.jpg" width="800">
  </a>
</p>


## Requirements

- Python 3.10+
- ADB available through `PATH` or `ADB_PATH`
- Android phone with USB debugging enabled
- ADB Keyboard installed and enabled for text input tasks
- Z.AI key in `.env`

Supported `.env` keys:

```bash
ZAI_KEY=your-key
PHONE_AGENT_BASE_URL=https://api.z.ai/api/coding/paas/v4
PHONE_AGENT_MODEL=autoglm-phone-multilingual
GLM_CELLPHONE_PUBLIC_BASE_URL=http://your-host:8787
GLM_CELLPHONE_MCP_ALLOWED_HOSTS=your-host:*
ADB_PATH=/absolute/path/to/adb
```

`ZAI_KEY` is enough for the current default config.

## Run

```bash
uv sync
uv run glm-cellphone
```

Open the dashboard:

```text
http://127.0.0.1:8787/
```

The default bind host is `0.0.0.0`. Override with `GLM_CELLPHONE_HOST` and
`GLM_CELLPHONE_PORT` if needed.

The MCP endpoint starts with the HTTP service:

```text
http://127.0.0.1:8787/mcp
```

Set `GLM_CELLPHONE_PUBLIC_BASE_URL` when MCP clients connect through another
host name, IP address, or private network name. Artifact URLs returned by MCP
tools will use that base URL.

The MCP transport validates `Host` headers. The host from
`GLM_CELLPHONE_PUBLIC_BASE_URL` is allowed automatically. Add comma-separated
extra values to `GLM_CELLPHONE_MCP_ALLOWED_HOSTS` when clients connect through
additional names or IP addresses, for example `phone-mac:*` or
`100.64.0.10:*`.

Run history is stored under `data/`:

- `data/glm-cellphone.sqlite3` keeps job metadata, status, results, and artifact
  records.
- `data/artifacts/{job_id}/` keeps `request.json`, `result.json`, `run.log`,
  and phone screenshots captured before and after each step.

## API

Health and device diagnostics:

```bash
curl http://127.0.0.1:8787/health
curl http://127.0.0.1:8787/devices
```

Run a task and wait for completion:

```bash
curl -X POST http://127.0.0.1:8787/tasks \
  -H 'content-type: application/json' \
  -d '{"task":"Open Chrome browser","max_steps":8}'
```

Start a background job:

```bash
curl -X POST http://127.0.0.1:8787/jobs \
  -H 'content-type: application/json' \
  -d '{"task":"Open Chrome browser","max_steps":8}'
```

Then poll:

```bash
curl http://127.0.0.1:8787/jobs/{job_id}
curl 'http://127.0.0.1:8787/jobs/{job_id}/logs?tail=20000'
```

List stored runs and stats:

```bash
curl http://127.0.0.1:8787/jobs
curl http://127.0.0.1:8787/stats
```

## MCP Tools

Connect an MCP client to `/mcp` on the same service. The server exposes:

- `start_phone_task`: start a background Android task and return a `job_id`.
- `get_phone_task_status`: poll concise progress, latest step/log lines, and
  artifact count.
- `get_phone_task_result`: fetch final result, steps summary, artifacts, and
  log tail once the run reaches a terminal status.
- `stop_phone_task`: request a cooperative stop for a queued or running task.

Agents should not provide runtime metrics such as duration or executed step
count. Those are produced by the service and returned in status/result tools.
