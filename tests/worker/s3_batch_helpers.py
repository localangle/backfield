"""Shared fakes for the S3 batch worker tests."""

from __future__ import annotations

import io
import json


def spec_with_s3() -> str:
    return json.dumps(
        {
            "name": "s3_flow",
            "nodes": [
                {
                    "id": "s3n",
                    "type": "S3Input",
                    "params": {"bucket": "my-bucket", "folder_path": "p", "max_files": 10},
                },
                {"id": "out", "type": "Output", "params": {}},
            ],
            "edges": [
                {"source": "s3n", "target": "out", "sourceHandle": "text", "targetHandle": "data"},
            ],
        }
    )


class FakeBody:
    def __init__(self, payload: bytes) -> None:
        self._buf = io.BytesIO(payload)

    def read(self) -> bytes:
        return self._buf.read()
