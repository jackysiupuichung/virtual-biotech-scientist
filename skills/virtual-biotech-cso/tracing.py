#!/usr/bin/env python
"""tracing.py — an in-tree span recorder for the virtual-biotech-cso loop.

The harness already prints an emoji ``Trace`` and writes findings to the knowledge
graph, but neither captures the *execution*: which agent role
ran, how long it took, how many tokens it cost, and how the brief→plan→execute→
review-loop→synthesize spans nest (including re-route iterations). This module
adds that, staying true to the project's ethos:

  * **Zero hard deps** — the source of truth is a ``trace.jsonl`` written into the
    run's ``out_dir``, alongside ``report.md`` / ``result.json``. Stdlib only.
  * **Inspectable in-repo** — one JSON object per line, parent/child linked by
    span id, so the existing React UI (or ``jq``) can render the span tree.
  * **Langfuse mirror (optional)** — if ``LANGFUSE_PUBLIC_KEY`` /
    ``LANGFUSE_SECRET_KEY`` are set *and* the ``langfuse`` SDK (v4) is importable,
    the whole span tree is mirrored to a hosted nested trace on ``close()``.
    Absent either, the exporter is a no-op — the JSONL trace is unaffected. Never
    a hard dependency, never fabricates timing. Install with::

        pip install 'langfuse>=4.0'   # or: pip install -e '.[tracing]'

    then set LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY (and LANGFUSE_HOST for a
    self-hosted instance). See _LangfuseExporter for the v4 API specifics.

Usage::

    rec = TraceRecorder(out_dir, run_name=case, backend=runner.name, model=runner.model)
    with rec.span("plan", kind="agent") as sp:
        ...
        sp.record_usage(input_tokens=..., output_tokens=...)
    rec.close()  # flush JSONL + langfuse

Spans nest via a context-local stack, so ``with rec.span(...)`` inside another
open span is automatically a child. Timing uses ``time.perf_counter`` for
durations and ``time.time`` for wall-clock stamps (both stdlib; the harness's
``Math.random``-free constraint is a Claude-Code-script rule, not a Python one).
"""
from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator


@dataclass
class Span:
    """One node in the execution trace — an agent role, a routed step, or the run."""

    name: str
    span_id: str
    parent_id: str | None
    kind: str  # "run" | "agent" | "tool" | "loop"
    started_at: float  # wall-clock epoch seconds
    _t0: float  # perf_counter at start (for duration)
    run_id: str
    attrs: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, int] = field(default_factory=dict)
    duration_ms: float | None = None
    status: str = "ok"  # "ok" | "error" | "stub"
    error: str | None = None

    def set(self, **attrs: Any) -> "Span":
        """Attach arbitrary metadata (role source, verdict, backend, …)."""
        self.attrs.update(attrs)
        return self

    def record_usage(self, *, input_tokens: int = 0, output_tokens: int = 0,
                     **_ignore: int) -> "Span":
        """Accumulate token usage for this span (and roll up to the run total).

        Extra keys (e.g. a backend's ``total_tokens`` or cache splits) are ignored
        so a runner's ``last_usage`` can be splatted in directly without coupling."""
        self.usage["input_tokens"] = self.usage.get("input_tokens", 0) + int(input_tokens)
        self.usage["output_tokens"] = self.usage.get("output_tokens", 0) + int(output_tokens)
        self.usage["total_tokens"] = (
            self.usage.get("input_tokens", 0) + self.usage.get("output_tokens", 0))
        return self

    def to_record(self) -> dict[str, Any]:
        """The JSONL line for this span — flat, parent-linked, self-describing."""
        return {
            "run_id": self.run_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "kind": self.kind,
            "status": self.status,
            "started_at": self.started_at,
            "duration_ms": round(self.duration_ms, 2) if self.duration_ms is not None else None,
            "usage": self.usage or None,
            "attrs": self.attrs or None,
            "error": self.error,
        }


class TraceRecorder:
    """Collects spans into a per-run ``trace.jsonl``; optionally mirrors to Langfuse.

    A single recorder spans one harness run. ``span()`` opens a child of the
    currently-open span (or of the synthetic root). Records are buffered and
    written on ``close()`` in start order so the file reads top-down; the buffer
    is small (one line per agent call + per routed step), so deferring the write
    keeps the hot path free of file I/O.
    """

    def __init__(self, out_dir: Path | None, *, run_name: str,
                 backend: str, model: str) -> None:
        self.run_id = uuid.uuid4().hex[:12]
        self._out_dir = out_dir
        self._records: list[dict[str, Any]] = []
        self._spans: list[Span] = []  # closed spans, in start order, for tree export
        self._stack: list[Span] = []
        self._totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        self._root = Span(
            name=run_name or "run", span_id=self.run_id, parent_id=None, kind="run",
            started_at=time.time(), _t0=time.perf_counter(), run_id=self.run_id,
            attrs={"backend": backend, "model": model})
        self._lf = _LangfuseExporter(run_name or "vbio-cso", self.run_id,
                                     {"backend": backend, "model": model})

    @contextmanager
    def span(self, name: str, *, kind: str = "agent", **attrs: Any) -> Iterator[Span]:
        """Open a child span of the current top-of-stack (or root). Auto-times it.

        On exception the span is marked ``status="error"`` with the message, then
        the exception re-raises — the harness's own try/except still decides how to
        degrade; we only observe.
        """
        parent = self._stack[-1] if self._stack else self._root
        sp = Span(
            name=name, span_id=uuid.uuid4().hex[:12], parent_id=parent.span_id,
            kind=kind, started_at=time.time(), _t0=time.perf_counter(),
            run_id=self.run_id, attrs=dict(attrs))
        self._stack.append(sp)
        try:
            yield sp
        except Exception as exc:  # noqa: BLE001 — observe then re-raise
            sp.status = "error"
            sp.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            sp.duration_ms = (time.perf_counter() - sp._t0) * 1000.0
            self._stack.pop()
            for k in self._totals:
                self._totals[k] += sp.usage.get(k, 0)
            self._records.append(sp.to_record())
            self._spans.append(sp)  # Langfuse export happens root-first in close()

    def close(self, **summary_attrs: Any) -> Path | None:
        """Finalise the root span, write ``trace.jsonl``, flush Langfuse.

        Returns the trace path (or ``None`` if no ``out_dir`` was given — useful
        for tests/CLI runs that don't persist output).
        """
        self._root.duration_ms = (time.perf_counter() - self._root._t0) * 1000.0
        self._root.usage = dict(self._totals)
        self._root.attrs.update(summary_attrs)
        # Root first so the file reads as a tree from the top.
        lines = [self._root.to_record()] + self._records
        # Export to Langfuse root-first (parents before children) so each child can
        # attach to its already-created parent observation. Spans were buffered in
        # close order (innermost first); a stable sort by start time restores
        # parent-before-child order for the whole tree.
        ordered = sorted(self._spans, key=lambda s: s.started_at)
        self._lf.export(self._root, ordered)

        if self._out_dir is None:
            return None
        self._out_dir.mkdir(parents=True, exist_ok=True)
        path = self._out_dir / "trace.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for rec in lines:
                fh.write(json.dumps(rec, default=str) + "\n")
        return path

    @property
    def totals(self) -> dict[str, int]:
        return dict(self._totals)


class _LangfuseExporter:
    """Best-effort mirror of the span tree to Langfuse. No-op unless configured.

    Targets the **Langfuse Python SDK v4** (the March-2026 OpenTelemetry rewrite):
    observations are created with ``start_observation(as_type=...)`` and children
    are created on the parent object (``parent.start_observation(...)``); every
    observation must be ``.end()``-ed and the client ``.flush()``-ed. See
    https://langfuse.com/docs/observability/sdk/python/instrumentation.

    Activates only when both ``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY``
    are set *and* ``langfuse`` (v4) imports. Any setup/emit error silently
    disables the exporter — observability must never break or slow the run. The
    in-tree ``trace.jsonl`` is always written regardless.

    Export is deferred to ``export()`` (called from ``close()``) and walks the
    tree root-first, so each child attaches to an already-created parent.
    """

    def __init__(self, name: str, run_id: str, meta: dict[str, Any]) -> None:
        self._client = None
        self._name = name
        self._run_id = run_id
        self._meta = meta
        if not (os.environ.get("LANGFUSE_PUBLIC_KEY")
                and os.environ.get("LANGFUSE_SECRET_KEY")):
            return
        try:
            from langfuse import get_client  # type: ignore  # v4 entrypoint

            self._client = get_client()  # reads LANGFUSE_* env (incl. _HOST)
        except Exception:  # noqa: BLE001 — disable, never break the run
            self._client = None

    @staticmethod
    def _as_type(kind: str) -> str:
        # Agent spans carry token usage → model them as generations so Langfuse
        # renders cost; everything else is a plain span.
        return "generation" if kind == "agent" else "span"

    def _obs_kwargs(self, sp: "Span") -> dict[str, Any]:
        """Map a Span to start_observation() kwargs (v4 accepts these directly)."""
        kw: dict[str, Any] = {
            "name": sp.name,
            "as_type": self._as_type(sp.kind),
            "metadata": {"kind": sp.kind, "status": sp.status, **sp.attrs},
        }
        if sp.usage:
            kw["usage_details"] = {
                "input": sp.usage.get("input_tokens", 0),
                "output": sp.usage.get("output_tokens", 0),
            }
        if sp.status == "error" and sp.error:
            kw["level"] = "ERROR"
            kw["status_message"] = sp.error
        model = sp.attrs.get("model")
        if self._as_type(sp.kind) == "generation" and model:
            kw["model"] = model
        return kw

    def _emit_scores(self, sp: "Span", obs: Any) -> None:
        """Post a span's LLM-as-a-judge verdict as Langfuse scores on its observation.

        The reviewer panel folds N lenses into one verdict + per-axis 1–5 scores and
        stashes them on the span attrs (``verdict``, ``scores``). We surface those as
        proper Langfuse *scores* (not just metadata) so they land in the eval
        dashboards alongside managed evaluators: each axis as a NUMERIC score and the
        routing decision as a CATEGORICAL one. ``score_id`` is derived from the span
        id so a re-export is idempotent rather than duplicating. Any span without
        these attrs contributes nothing; any error disables scoring for this span
        only (the trace export already swallows at the call site too).

        IDs are read off the freshly-created observation object — ``start_observation``
        does not set the OTEL *current* context (only ``start_as_current_observation``
        would), so ``score_current_*`` wouldn't target this span. ``create_score``
        with an explicit ``trace_id``/``observation_id`` is the context-free path."""
        verdict = sp.attrs.get("verdict")
        scores = sp.attrs.get("scores") or {}
        if not verdict and not scores:
            return
        kw = {"trace_id": obs.trace_id, "observation_id": obs.id}
        for axis, value in scores.items():
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue  # non-numeric axis (e.g. a stub's empty string) → skip
            self._client.create_score(
                name=f"reviewer.{axis}", value=numeric, data_type="NUMERIC",
                score_id=f"{sp.span_id}-{axis}", **kw)
        if verdict:
            self._client.create_score(
                name="reviewer.verdict", value=str(verdict), data_type="CATEGORICAL",
                comment=f"reroute_votes={sp.attrs.get('reroute_votes')} "
                        f"forced_by_engine={sp.attrs.get('forced_by_engine')}",
                score_id=f"{sp.span_id}-verdict", **kw)

    def export(self, root: "Span", spans: list["Span"]) -> None:
        """Create the trace + observation tree, then flush. Root-first ordering."""
        if self._client is None:
            return
        try:
            objs: dict[str, Any] = {}
            # Root observation anchors the trace; its name/metadata become the trace's.
            root_obs = self._client.start_observation(
                name=root.name, as_type="span",
                metadata={"kind": "run", **self._meta, **root.attrs,
                          "usage": root.usage})
            objs[root.span_id] = root_obs
            # Name the trace itself when this SDK build exposes the current-trace API
            # (update_trace lives on the client in v4, only while a span is active).
            updater = getattr(self._client, "update_current_trace", None)
            if callable(updater):
                try:
                    updater(name=self._name, metadata={**self._meta, "usage": root.usage})
                except Exception:  # noqa: BLE001 — needs an active span on some builds
                    pass

            for sp in spans:  # already sorted parent-before-child by start time
                parent = objs.get(sp.parent_id) or root_obs
                obs = parent.start_observation(**self._obs_kwargs(sp))
                try:
                    self._emit_scores(sp, obs)  # judge verdict → Langfuse scores
                except Exception:  # noqa: BLE001 — scoring is additive; keep the tree
                    pass
                obs.end()
                objs[sp.span_id] = obs

            root_obs.end()
            self._client.flush()
        except Exception:  # noqa: BLE001 — partial trace is fine; never break the run
            try:
                self._client.flush()
            except Exception:  # noqa: BLE001
                pass
