"""Run with PYTHONPATH=<read-only exact C1 export>. No service/solver/device.

Writes a generated strict C1 contract fixture to stdout, not tracked point data.
"""
import json
from robot_dashboard.expansion_contracts.fixtures import request
from robot_dashboard.expansion_contracts.messages import FusionProposal, IDENTITY

r = request()
p = FusionProposal(schema_version="0.1", evidence_kind="SYNTHETIC",
    producer="c2-contract-inspection", sequence=1, source_epoch="fixture-epoch",
    job_id="f" * 24, proposal_revision=1, state="SOLVED_CANDIDATE",
    anchor_source_key=r.anchor_source_key,
    T_fused_source={k: IDENTITY for k in r.source_pins}, pairwise_edges=[],
    connected_components=[list(r.source_pins)], quality={}, ambiguous_candidates=[],
    warnings=["EXTERNAL C1 CONTRACT FIXTURE ONLY; no registration solver executed"],
    input_pins=r.source_pins, solver_version="contract-fixture", elapsed_ms=0.)
print(json.dumps({"request": r.to_dict(), "proposal": p.to_dict()}))
