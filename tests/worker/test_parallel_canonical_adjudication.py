"""Parallel DBOutput canonical adjudication: runner and handler integration."""

from __future__ import annotations

import threading
import time
from decimal import Decimal
from typing import Any

import pytest
from backfield_ai.tracking_context import (
    LlmAttemptTrackingContext,
    attach_llm_tracking_context,
    persist_llm_attempt,
    reset_llm_tracking_context,
)
from backfield_db import (
    AgateRun,
    BackfieldOrganization,
    BackfieldProject,
    StylebookPersonCanonical,
    SubstratePerson,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.entities.person.persist import upsert_alias_for_canonical_text
from sqlmodel import Session, SQLModel, create_engine, select
from worker.substrate import persist_from_consolidated
from worker.substrate.canonical.parallel_llm import (
    canonical_adjudication_max_concurrent,
    run_callables_parallel,
)

from tests.worker.test_substrate_persistence import _bootstrap_project, _empty_places


def test_canonical_adjudication_max_concurrent_defaults_to_eight(monkeypatch) -> None:
    monkeypatch.delenv("CANONICAL_ADJUDICATION_MAX_CONCURRENT", raising=False)
    assert canonical_adjudication_max_concurrent() == 8


def test_canonical_adjudication_max_concurrent_respects_env(monkeypatch) -> None:
    monkeypatch.setenv("CANONICAL_ADJUDICATION_MAX_CONCURRENT", "3")
    assert canonical_adjudication_max_concurrent() == 3
    monkeypatch.setenv("CANONICAL_ADJUDICATION_MAX_CONCURRENT", "0")
    assert canonical_adjudication_max_concurrent() == 1


def test_run_callables_parallel_serial_when_max_workers_one() -> None:
    order: list[int] = []

    def task(i: int) -> int:
        order.append(i)
        return i

    out = run_callables_parallel([lambda i=i: task(i) for i in range(4)], max_workers=1)
    assert out == [0, 1, 2, 3]
    assert order == [0, 1, 2, 3]


def test_run_callables_parallel_preserves_order() -> None:
    out = run_callables_parallel(
        [lambda i=i: i * 2 for i in range(5)],
        max_workers=4,
    )
    assert out == [0, 2, 4, 6, 8]


def test_run_callables_parallel_preserves_none_results() -> None:
    """Adjudication LLM helpers return None on failure; do not drop them from the batch."""
    out = run_callables_parallel(
        [lambda i=i: None if i % 2 else i for i in range(4)],
        max_workers=4,
    )
    assert out == [0, None, 2, None]


def test_run_callables_parallel_runs_concurrently() -> None:
    active = 0
    peak = 0
    lock = threading.Lock()

    def slow_task() -> int:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.08)
        with lock:
            active -= 1
        return 1

    start = time.monotonic()
    run_callables_parallel([slow_task] * 6, max_workers=4)
    elapsed = time.monotonic() - start

    assert peak >= 2
    assert elapsed < 0.45


def test_run_callables_parallel_propagates_tracking_context(
    memory_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backfield_ai.tracking_context.get_engine", lambda: memory_engine)
    tok = attach_llm_tracking_context(
        LlmAttemptTrackingContext(project_id=1, run_id="run-par-llm"),
    )
    try:

        def _record(i: int) -> int:
            persist_llm_attempt(
                provider="openai",
                provider_model_id="gpt-test",
                status="succeeded",
                attempt_number=1,
                model_config_id=None,
                model_config_snapshot_json=None,
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
                estimated_cost=Decimal("0.001"),
                currency="USD",
                cost_estimate_incomplete=False,
                latency_ms=10,
                provider_request_id=f"req-{i}",
                error_type=None,
                error_message=None,
            )
            return i

        run_callables_parallel([lambda i=i: _record(i) for i in range(6)], max_workers=4)
    finally:
        reset_llm_tracking_context(tok)

    from backfield_db import BackfieldAiCallRecord

    with Session(memory_engine) as session:
        rows = list(session.exec(select(BackfieldAiCallRecord)).all())
    assert len(rows) == 6


@pytest.fixture
def memory_engine():
    from backfield_db import BackfieldAiCallRecord
    from sqlmodel.pool import StaticPool

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    BackfieldAiCallRecord.metadata.create_all(engine)
    return engine


@pytest.fixture
def memory_session(memory_engine) -> Session:
    with Session(memory_engine) as session:
        yield session


def _seed_ambiguous_person_stylebook(session: Session, project_id: int) -> int:
    proj = session.get(BackfieldProject, project_id)
    assert proj is not None
    org = session.get(BackfieldOrganization, proj.organization_id)
    assert org is not None
    sb = ensure_default_stylebook_for_organization(session, int(org.id))  # type: ignore[arg-type]
    sb_id = int(sb.id)  # type: ignore[arg-type]
    for label, slug, affiliation in (
        ("John Smith", "john-smith-a", "Chicago"),
        ("John Smith", "john-smith-b", "Evanston"),
    ):
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label=label,
            slug=slug,
            affiliation=affiliation,
        )
        session.add(canon)
        session.flush()
        upsert_alias_for_canonical_text(
            session,
            canon_id=str(canon.id),
            alias_text="John Smith",
            normalized_alias="john smith",
            provenance="seed",
        )
    session.commit()
    return sb_id


def _person_entry(*, suffix: str) -> dict[str, Any]:
    return {
        "name": "John Smith",
        "title": "Resident",
        "affiliation": f"Town {suffix}",
        "public_figure": False,
        "type": "",
        "role_in_story": "Quoted",
        "nature": "source",
        "nature_secondary_tags": [],
        "review_handling": "none",
        "mentions": [{"text": f"John Smith of Town {suffix} spoke.", "quote": False}],
    }


def _run_parallel_person_persist(
    *,
    monkeypatch: pytest.MonkeyPatch,
    max_concurrent: int,
    llm_side_effect: Any,
) -> list[tuple[str | None, str | None]]:
    monkeypatch.setenv("CANONICAL_ADJUDICATION_MAX_CONCURRENT", str(max_concurrent))
    monkeypatch.setattr(
        "worker.substrate.entities.person.adjudication.call_llm",
        llm_side_effect,
    )

    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-par", project_slug="proj-par")
        _seed_ambiguous_person_stylebook(session, project_id)
        session.add(AgateRun(id="run-par", graph_id="graph-par", status="pending"))
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-par",
            run_id="run-par",
            consolidated={
                "text": "John Smith stories.",
                "places": _empty_places(),
                "people": [
                    _person_entry(suffix="A"),
                    _person_entry(suffix="B"),
                    _person_entry(suffix="C"),
                ],
            },
            db_output_params={
                "canonicalization_mode": "ai_assisted",
                "auto_apply_canonicalization": True,
            },
        )
        session.commit()

    with Session(engine) as session:
        people = list(session.exec(select(SubstratePerson).order_by(SubstratePerson.id)).all())
        return [
            (p.stylebook_person_canonical_id, p.canonical_link_status) for p in people
        ]


def test_parallel_person_adjudication_matches_serial_outcomes(monkeypatch) -> None:
    def _deterministic_reject(prompt: str, **_kwargs: Any) -> str:
        if "Candidates" not in prompt:
            return '{"variant_names": []}'
        return '{"canonical_id": null, "confidence": 0.2, "rationale": "unsure"}'

    def _outcome_signature(
        rows: list[tuple[str | None, str | None]],
    ) -> list[tuple[str | None, bool]]:
        return sorted((status, canon_id is not None) for canon_id, status in rows)

    serial = _run_parallel_person_persist(
        monkeypatch=monkeypatch,
        max_concurrent=1,
        llm_side_effect=_deterministic_reject,
    )
    parallel = _run_parallel_person_persist(
        monkeypatch=monkeypatch,
        max_concurrent=8,
        llm_side_effect=_deterministic_reject,
    )
    assert _outcome_signature(serial) == _outcome_signature(parallel)
    assert len(serial) == 3


def test_parallel_person_adjudication_faster_than_serial(monkeypatch) -> None:
    active = 0
    peak = 0
    lock = threading.Lock()

    def _slow_llm(prompt: str, **_kwargs: Any) -> str:
        if "Candidates" not in prompt:
            return '{"variant_names": []}'
        with lock:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
        time.sleep(0.06)
        with lock:
            active -= 1
        return '{"canonical_id": null, "confidence": 0.0, "rationale": "unsure"}'

    monkeypatch.setattr(
        "worker.substrate.entities.person.adjudication.call_llm",
        _slow_llm,
    )

    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    def _elapsed(max_concurrent: int) -> float:
        monkeypatch.setenv("CANONICAL_ADJUDICATION_MAX_CONCURRENT", str(max_concurrent))
        eng = create_engine("sqlite://", echo=False)
        SQLModel.metadata.create_all(eng)
        with Session(eng) as session:
            project_id = _bootstrap_project(
                session,
                org_slug=f"org-t{max_concurrent}",
                project_slug=f"proj-t{max_concurrent}",
            )
            _seed_ambiguous_person_stylebook(session, project_id)
            session.add(AgateRun(id=f"run-t{max_concurrent}", graph_id="graph-t", status="pending"))
            session.commit()
            start = time.monotonic()
            persist_from_consolidated(
                session,
                project_id=project_id,
                graph_id="graph-t",
                run_id=f"run-t{max_concurrent}",
                consolidated={
                    "text": "John Smith stories.",
                    "places": _empty_places(),
                    "people": [_person_entry(suffix=str(i)) for i in range(4)],
                },
                db_output_params={
                    "canonicalization_mode": "ai_assisted",
                    "auto_apply_canonicalization": False,
                },
            )
            session.commit()
            return time.monotonic() - start

    serial_elapsed = _elapsed(1)
    parallel_elapsed = _elapsed(8)

    assert parallel_elapsed < serial_elapsed * 0.75
    assert peak >= 2
