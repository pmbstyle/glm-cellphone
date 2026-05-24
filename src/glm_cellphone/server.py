from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.getenv("GLM_CELLPHONE_HOST", "0.0.0.0")
    port = int(os.getenv("GLM_CELLPHONE_PORT", "8787"))
    uvicorn.run("glm_cellphone.api:app", host=host, port=port)


if __name__ == "__main__":
    main()

