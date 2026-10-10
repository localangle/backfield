"""Decision-model calls. These do not use chat completions."""

from __future__ import annotations

import litellm

_CONNECTION_TEST_QUESTIONS: dict[str, dict[str, object]] = {
    "ping": {
        "type": "choice",
        "instructions": "Choose ok.",
        "criteria": {
            "ok": "The connection works.",
            "none": "No answer.",
        },
    }
}


def decision_connection_test_sync(
    *,
    litellm_model: str,
    api_key: str | None,
    api_base: str | None,
    timeout: float,
) -> None:
    """One cheap choice call proving the decision model accepts the credential."""
    model = litellm_model.strip()
    if not model:
        raise RuntimeError("Decision model id is empty.")
    response = litellm.decisions(
        model=model,
        state="Connection check.",
        questions=_CONNECTION_TEST_QUESTIONS,
        api_key=api_key,
        api_base=(api_base or "").strip() or None,
        timeout=timeout,
    )
    answers = getattr(response, "answers", None)
    if not answers or "ping" not in answers:
        raise RuntimeError("Decision model check returned no answer.")
