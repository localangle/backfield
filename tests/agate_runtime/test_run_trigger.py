"""Tests for shared run trigger helpers."""

from __future__ import annotations

import json

import pytest
from agate_runtime.run_graph_spec import parse_run_result_payload
from agate_runtime.run_trigger import (
    PUBLIC_ALIAS_PARAM,
    apply_inputs_to_spec,
    find_public_ingress_node,
    trigger_agate_run,
)
from agate_runtime.types import GraphSpec, NodeConfig
from backfield_db import AgateGraph, AgateRun
from sqlmodel import Session, SQLModel, create_engine


def _text_spec(*, alias: str = "article", text: str = "Hello") -> GraphSpec:
    return GraphSpec(
        name="flow",
        nodes=[
            NodeConfig(
                id="n1",
                type="TextInput",
                params={"text": text, PUBLIC_ALIAS_PARAM: alias},
            ),
            NodeConfig(id="n2", type="Output", params={}),
        ],
        edges=[],
    )


def _s3_spec(*, alias: str = "batch") -> GraphSpec:
    return GraphSpec(
        name="batch",
        nodes=[
            NodeConfig(
                id="s1",
                type="S3Input",
                params={
                    "bucket": "saved-bucket",
                    "folder_path": "saved/prefix/",
                    "max_files": 500,
                    PUBLIC_ALIAS_PARAM: alias,
                },
            ),
            NodeConfig(id="n2", type="Output", params={}),
        ],
        edges=[],
    )


def test_find_public_ingress_node_single() -> None:
    node = find_public_ingress_node(_text_spec())
    assert node.type == "TextInput"


def test_find_public_ingress_node_rejects_none() -> None:
    spec = GraphSpec(name="x", nodes=[NodeConfig(id="o", type="Output", params={})], edges=[])
    with pytest.raises(ValueError, match="exactly one"):
        find_public_ingress_node(spec)


def test_apply_inputs_to_spec_text_override() -> None:
    effective = apply_inputs_to_spec(
        _text_spec(),
        {"article": {"text": "Override body"}},
    )
    ingress = find_public_ingress_node(effective)
    assert ingress.params["text"] == "Override body"


def test_apply_inputs_to_spec_no_inputs_returns_copy() -> None:
    original = _text_spec(text="Saved")
    effective = apply_inputs_to_spec(original, None)
    assert effective.nodes[0].params["text"] == "Saved"


def test_apply_inputs_to_spec_bad_alias() -> None:
    with pytest.raises(ValueError, match="Unknown input alias"):
        apply_inputs_to_spec(_text_spec(), {"wrong": {"text": "x"}})


def test_apply_inputs_to_spec_s3_merge_and_cap() -> None:
    effective = apply_inputs_to_spec(
        _s3_spec(),
        {"batch": {"bucket": "run-bucket", "prefix": "run/prefix/", "max_files": 999_999}},
    )
    ingress = find_public_ingress_node(effective)
    assert ingress.params["bucket"] == "run-bucket"
    assert ingress.params["folder_path"] == "run/prefix/"
    assert ingress.params["max_files"] == 10_000


def test_trigger_agate_run_pins_effective_spec_and_enqueues() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    enqueued: list[tuple[str, list[object]]] = []

    def enqueue(name: str, args: list[object]) -> None:
        enqueued.append((name, args))

    with Session(engine) as session:
        graph = AgateGraph(
            id="g1",
            name="Flow",
            spec_json=_text_spec().model_dump_json(),
            project_id=1,
            public_run_enabled=True,
        )
        session.add(graph)
        session.commit()

        result = trigger_agate_run(
            session,
            graph=graph,
            inputs={"article": {"text": "From API"}},
            enqueue=enqueue,
        )
        assert result.processed_item is not None
        assert result.run.status == "running"
        item_id = int(result.processed_item.id)
        assert enqueued == [("worker.tasks.execute_processed_item", [item_id])]

        run = session.get(AgateRun, result.run.id)
        assert run is not None
        snap = json.loads(str(parse_run_result_payload(run.result_json)["graph_spec_json"]))
        text_node = next(n for n in snap["nodes"] if n["type"] == "TextInput")
        assert text_node["params"]["text"] == "From API"

        item = result.processed_item
        assert item.input_json is not None
        assert "From API" in item.input_json
