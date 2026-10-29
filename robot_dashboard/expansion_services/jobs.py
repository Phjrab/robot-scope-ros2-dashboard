"""One explicit bounded worker, bounded history and fenced candidate publication.

Injected solvers must cooperate with cancel/progress. An uncooperative solver
retains the sole slot; no replacement worker/thread is spawned to bypass bounds.
"""

from collections import OrderedDict
from contextlib import contextmanager
import copy
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import tempfile
import queue
import threading
import time
import uuid

from robot_dashboard.expansion_contracts import (
    ContractError,
    FusionRequest,
    FusionProposal,
)
from robot_dashboard.expansion_contracts.messages import integer, number
from robot_dashboard.pcd_editing.store import _open_regular, _signature, _digest
from .catalogue import Busy, Conflict


class FusionJobManager:
    def __init__(
        self,
        catalogue,
        solver,
        store,
        *,
        max_queue=4,
        max_history=32,
        max_job_bytes=256 * 1024**2,
    ):
        integer(max_job_bytes, "job byte bound", 1, 256 * 1024**2)
        self.max_job_bytes = max_job_bytes
        integer(max_queue, "queue bound", 1, 64)
        integer(max_history, "history bound", max_queue + 1, 256)
        self.catalogue, self.solver, self.store = catalogue, solver, store
        self.max_queue, self.max_history = max_queue, max_history
        self._lock = threading.RLock()
        self._jobs = OrderedDict()
        self._requests = {}
        self._queue = queue.Queue(max_queue + 1)
        self._outstanding, self._closed = 0, False
        self._wake = threading.Event()
        self._worker = threading.Thread(
            target=self._run, name="c1-fusion-worker", daemon=True
        )
        self._worker.start()

    def enqueue(self, value):
        request = FusionRequest.from_dict(
            value.to_dict() if isinstance(value, FusionRequest) else value
        )
        self.catalogue.pinned(request)
        with self._lock:
            if self._closed:
                raise Busy("manager closed")
            if request.request_id in self._requests:
                old = self._jobs[self._requests[request.request_id]]
                if old["request"].fingerprint != request.fingerprint:
                    raise Conflict("request ID reused with changed pins/options")
                return self._public(old)
            if self._outstanding >= self.max_queue + 1:
                raise Busy("fusion queue full")
            while len(self._jobs) >= self.max_history:
                victim = next(
                    (
                        k
                        for k, j in self._jobs.items()
                        if j["done"] and not j["exporting"]
                    ),
                    None,
                )
                if victim is None:
                    raise Busy("bounded history full")
                old = self._jobs.pop(victim)
                self._requests.pop(old["request"].request_id, None)
            job_id = uuid.uuid4().hex[:24]
            job = dict(
                job_id=job_id,
                request=request,
                state="QUEUED",
                progress=0.0,
                proposal=None,
                proposal_revision=0,
                review=None,
                export=None,
                exporting=False,
                cancel=threading.Event(),
                done=False,
                error=None,
            )
            self._jobs[job_id] = job
            self._requests[request.request_id] = job_id
            self._outstanding += 1
            self._queue.put_nowait(job_id)
            self._wake.set()
            return self._public(job)

    def _public(self, j):
        return copy.deepcopy(
            {
                k: j[k]
                for k in (
                    "job_id",
                    "state",
                    "progress",
                    "proposal_revision",
                    "review",
                    "export",
                    "error",
                )
            }
            | {
                "proposal": j["proposal"].to_dict() if j["proposal"] else None,
                "operational_installed": False,
                "evidence_kind": j["request"].evidence_kind,
            }
        )

    def status(self, job_id):
        with self._lock:
            return self._public(self._jobs[job_id])

    def cancel(self, job_id):
        with self._lock:
            j = self._jobs[job_id]
            if j["state"] == "EXPORTED":
                raise Conflict("immutable export is already committed")
            j["cancel"].set()
            j["state"], j["proposal"], j["review"] = "CANCELED", None, None
            return self._public(j)

    def _snapshots(self, sources, directory, cancel):
        result, total = [], 0
        for index, source in enumerate(sources):
            destination = Path(directory) / f"source-{index}.pcd"
            sha = hashlib.sha256()
            with (
                _open_regular(source.asset.path, self.catalogue.max_bytes) as original,
                destination.open("xb") as out,
            ):
                before = _signature(os.fstat(original.fileno()))
                while block := original.read(1024 * 1024):
                    if cancel.is_set():
                        raise Conflict("snapshot canceled")
                    total += len(block)
                    if total > self.max_job_bytes:
                        raise ContractError(
                            "aggregate source bytes exceed worker bound"
                        )
                    sha.update(block)
                    out.write(block)
                if (
                    before != _signature(os.fstat(original.fileno()))
                    or sha.hexdigest() != source.descriptor.sha256
                ):
                    raise Conflict("source changed during private snapshot")
            destination.chmod(0o400)
            result.append(
                replace(source, asset=replace(source.asset, path=destination))
            )
        return tuple(result)

    def _run(self):
        while True:
            self._wake.wait(0.1)
            try:
                job_id = self._queue.get_nowait()
            except queue.Empty:
                self._wake.clear()
                with self._lock:
                    if self._closed:
                        return
                continue
            with self._lock:
                j = self._jobs[job_id]
                if not j["cancel"].is_set():
                    j["state"] = "RUNNING"
            started = time.monotonic()
            request = j["request"]

            def progress(value):
                number(value, "progress")
                with self._lock:
                    if not j["cancel"].is_set() and j["state"] == "RUNNING":
                        j["progress"] = max(j["progress"], min(1.0, max(0.0, value)))
                    if time.monotonic() - started > request.options.get(
                        "max_runtime_s", 300
                    ):
                        j["cancel"].set()
                        j["state"] = "CANCELED"

            try:
                if not j["cancel"].is_set():
                    sources = self.catalogue.pinned(request)
                    # D1 receives the manager ID via this explicit bound request context.
                    with tempfile.TemporaryDirectory(prefix="c1-solver-") as directory:
                        snapshots = self._snapshots(sources, directory, j["cancel"])
                        result = self.solver(
                            FusionRequest.from_dict(request.to_dict()),
                            snapshots,
                            j["cancel"],
                            progress,
                            job_id=job_id,
                        )
                        if any(
                            _digest(s.asset.path, self.catalogue.max_bytes)
                            != s.descriptor.sha256
                            for s in snapshots
                        ):
                            raise Conflict("worker changed private source snapshot")
                    proposal = FusionProposal.from_dict(
                        result.to_dict()
                        if isinstance(result, FusionProposal)
                        else result
                    )
                    self.catalogue.pinned(request)
                    if (
                        proposal.job_id != job_id
                        or proposal.input_pins != request.source_pins
                        or proposal.anchor_source_key != request.anchor_source_key
                        or proposal.evidence_kind != request.evidence_kind
                        or proposal.source_epoch != request.source_epoch
                        or proposal.proposal_revision != 1
                    ):
                        raise Conflict("solver result identity/pins mismatch")
                    if time.monotonic() - started > request.options.get(
                        "max_runtime_s", 300
                    ):
                        raise Conflict("solver runtime deadline exceeded")
                    with self._lock:
                        if not j["cancel"].is_set():
                            j.update(
                                state=proposal.state,
                                proposal=proposal,
                                proposal_revision=proposal.proposal_revision,
                                progress=1.0,
                            )
            except Exception as exc:
                with self._lock:
                    if not j["cancel"].is_set():
                        # Never leak server paths or solver internals to the API.
                        j["state"], j["error"] = "FAILED", type(exc).__name__
            finally:
                with self._lock:
                    if j["cancel"].is_set():
                        j.update(state="CANCELED", proposal=None, review=None)
                    j["done"] = True
                    self._outstanding -= 1
                self._queue.task_done()

    def review(self, job_id, expected_revision, accepted, manual_selection=None):
        integer(expected_revision, "expected proposal revision", 1)
        if type(accepted) is not bool:
            raise ContractError("explicit boolean review required")
        with self._lock:
            j = self._jobs[job_id]
            if (
                j["state"] not in {"SOLVED_CANDIDATE", "REVIEWED", "REJECTED"}
                or j["proposal"] is None
                or j["exporting"]
                or j["proposal_revision"] != expected_revision
            ):
                raise Conflict("stale proposal or invalid review state")
            self.catalogue.pinned(j["request"])
            proposal = j["proposal"]
            if manual_selection is not None:
                if (
                    not accepted
                    or not isinstance(manual_selection, dict)
                    or set(manual_selection) != set(j["request"].source_pins)
                ):
                    raise ContractError(
                        "manual selection requires explicit complete transform set"
                    )
                proposal = replace(
                    proposal,
                    T_fused_source=copy.deepcopy(manual_selection),
                    state="SOLVED_CANDIDATE",
                    warnings=[
                        *proposal.warnings,
                        "manual transforms are user supplied; quality not recomputed",
                    ],
                )
            revision = expected_revision + 1
            j.update(
                proposal=replace(proposal, proposal_revision=revision),
                proposal_revision=revision,
                review={
                    "accepted": accepted,
                    "manual": manual_selection is not None,
                    "expected_revision": expected_revision,
                    "registration_quality_validated": False
                    if manual_selection is not None
                    else None,
                },
                state="REVIEWED" if accepted else "REJECTED",
            )
            return self._public(j)

    def export(self, job_id, name, expected_revision):
        integer(expected_revision, "expected proposal revision", 1)
        with self._lock:
            j = self._jobs[job_id]
            if (
                j["state"] != "REVIEWED"
                or j["proposal_revision"] != expected_revision
                or j["exporting"]
            ):
                raise Conflict("export requires current accepted review")
            j["exporting"] = True
            request, proposal, review = (
                j["request"],
                j["proposal"],
                copy.deepcopy(j["review"]),
            )

        @contextmanager
        def publication_guard():
            with self._lock:
                if (
                    j["cancel"].is_set()
                    or j["state"] != "REVIEWED"
                    or j["proposal_revision"] != expected_revision
                ):
                    raise Conflict("export lost proposal ownership")
                yield
                j["state"] = "EXPORTED"

        try:
            result = self.store.save(
                request,
                proposal,
                name,
                j["cancel"],
                review,
                publication_guard=publication_guard,
            )
            with self._lock:
                j["export"] = {"id": result["id"], "revision": result["revision"]}
                return result
        finally:
            with self._lock:
                j["exporting"] = False

    def close(self, timeout=2.0):
        with self._lock:
            self._closed = True
            for j in self._jobs.values():
                if not j["done"]:
                    j["cancel"].set()
        self._wake.set()
        self._worker.join(timeout)
