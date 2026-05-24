# GLM Cellphone

Local HTTP service for running AutoGLM phone-agent tasks against a connected Android
device.

The service wraps the Open-AutoGLM phone agent loop:

1. Capture the current phone screen over ADB.
2. Send the screenshot and task context to `autoglm-phone-multilingual`.
3. Execute the returned phone action over ADB.
4. Repeat until the model returns `finish(...)`, asks for takeover, or reaches the
   configured step limit.

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
