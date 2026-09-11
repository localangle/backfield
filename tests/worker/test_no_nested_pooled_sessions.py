"""The worker must never open a pooled Session while it already holds one.

The worker runs with ``pool_size=1`` and ``max_overflow=0``
(``infra/docker-compose.yml``), so a second ``Session(engine)`` opened while an
outer one is still held can never be served: it blocks for the pool timeout and
raises ``TimeoutError``.

That is not a theoretical hazard. It silently broke run failure reporting. When
``execute_s3_batch_setup`` raised, the ``except`` block that marks the run
``failed`` opened a nested ``Session(engine)``, timed out, and the run stayed
``running`` forever with ``error_message`` NULL -- so the original error survived
only in the worker log and ``status == "running"`` stopped meaning "still
working".

``null_pool_session()`` exists for exactly this case and says so in its
docstring. This test enforces the rule across the whole module rather than
pinning the two handlers that were wrong, so a future nested session anywhere in
``tasks.py`` fails here instead of in production.
"""

from __future__ import annotations

import ast
import pathlib

TASKS = (
    pathlib.Path(__file__).resolve().parents[2]
    / "apps"
    / "worker"
    / "src"
    / "worker"
    / "tasks.py"
)


def _opens_pooled_session(node: ast.With) -> bool:
    """True when this ``with`` opens ``Session(engine)`` from the process pool."""
    for item in node.items:
        call = item.context_expr
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != "Session":
            continue
        # ``Session(engine)`` uses the shared pool; ``Session(some_other_engine)``
        # does not necessarily, so only flag the pooled one.
        for arg in call.args:
            if isinstance(arg, ast.Name) and arg.id == "engine":
                return True
    return False


def _nested_pooled_sessions(tree: ast.AST) -> list[tuple[str, int, int]]:
    """Every (function, outer line, inner line) where a pooled Session nests."""
    found: list[tuple[str, int, int]] = []

    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        def visit(node: ast.AST, outer_line: int | None) -> None:
            for child in ast.iter_child_nodes(node):
                # Do not descend into a nested function: it runs with its own
                # call stack and may legitimately open its own session.
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if isinstance(child, ast.With) and _opens_pooled_session(child):
                    if outer_line is not None:
                        found.append((func.name, outer_line, child.lineno))
                    visit(child, child.lineno)
                else:
                    visit(child, outer_line)

        visit(func, None)

    return found


def test_tasks_module_is_parseable() -> None:
    """Guards the guard: a parse failure must not read as 'no violations'."""
    assert TASKS.is_file(), f"{TASKS} not found"
    tree = ast.parse(TASKS.read_text())
    functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    assert len(functions) > 20, "parsed far fewer functions than expected"


def test_no_pooled_session_is_opened_inside_another() -> None:
    tree = ast.parse(TASKS.read_text())
    violations = _nested_pooled_sessions(tree)
    assert not violations, (
        "a pooled Session(engine) is opened while another is still held; on the "
        "worker (pool_size=1, max_overflow=0) that cannot be served and will time "
        "out. Use null_pool_session() for the inner one. Offenders "
        "(function, outer line, inner line): " + repr(violations)
    )


def test_the_detector_finds_a_known_nested_case() -> None:
    """Proves the check above is not vacuous by giving it a violation to find."""
    source = """
def handler():
    with Session(engine) as outer:
        try:
            work(outer)
        except Exception:
            with Session(engine) as inner:
                mark_failed(inner)
"""
    violations = _nested_pooled_sessions(ast.parse(source))
    assert [v[0] for v in violations] == ["handler"]

    fixed = source.replace(
        "with Session(engine) as inner:", "with null_pool_session() as inner:"
    )
    assert _nested_pooled_sessions(ast.parse(fixed)) == []


def test_the_detector_allows_sequential_pooled_sessions() -> None:
    """Opening one after another closes is fine and must not be flagged."""
    source = """
def handler():
    with Session(engine) as first:
        work(first)
    with Session(engine) as second:
        work(second)
"""
    assert _nested_pooled_sessions(ast.parse(source)) == []
