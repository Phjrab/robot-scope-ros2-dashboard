"""Server-owned, explicitly non-motion contract rehearsal.

This consumes observations through an adapter, not YOLO or avoidance logic.
There is no native registration path and no navigation/bridge reference. The VM
integration must bind the PROPOSED port to the existing MissionCoordinator and
single command arbiter before any robot action can become available.
"""
from __future__ import annotations

import asyncio
import copy
import secrets
import time

from .competition_contract import Evidence
from .models import digest
from ..application.mission_coordinator import MissionConflict

FRESH_S = 0.5


class FixtureAdapter:
    mode = "fixture"
    owner_id = "competition-fixture-no-motion"

    def __init__(self, scenario="normal", *, clock=time.monotonic):
        self.scenario, self.clock = scenario, clock
        self.commands, self.constraints = [], []
        self.epoch = secrets.token_hex(8)
        self.sequence = 0
        self.current = None
        self.started = 0
        self.held = False

    def dispatch(self, command):
        self.current = copy.deepcopy(command)
        self.commands.append(copy.deepcopy(command))
        self.started, self.held = self.clock(), False
        return secrets.token_hex(16)

    def constrain(self, constraint):
        # This is a receipt log, NEVER a cmd_vel publisher or arbiter.
        self.constraints.append(copy.deepcopy(constraint))
        self.held = constraint["mode"] == "HOLD"

    def sample(self, state):
        self.sequence += 1
        action = self.current["action"]
        elapsed = self.clock() - self.started
        signal = "RED" if elapsed < 1 or self.scenario == "red" else "GREEN"
        if self.scenario == "unknown":
            signal = "UNKNOWN"
        return Evidence(
            producer_id="explicit-synthetic-fixture", producer_epoch=self.epoch,
            sequence=self.sequence, source_stamp_ns=str(time.time_ns()), source_clock="fixture",
            evidence_type="fixture", config_hash=digest({"scenario": self.scenario}), source_age_s=0,
            owner_id=self.owner_id, mission_run_id=state["id"], step_id=action["step_id"],
            goal_id=state["goal_id"], goal_generation=state["goal_generation"],
            goal_state="FAILED" if self.scenario == "nav_failure" else "SUCCEEDED" if elapsed >= .4 else "ACTIVE",
            hold_ack=self.held, pose=None if self.scenario == "missing_pose" else {"x": 0.0, "y": 0.0, "yaw": 0.0},
            path_clear=self.scenario != "obstacle", obstacle_state="WAIT_OBSTACLE" if self.scenario == "obstacle" else "FOLLOWING",
            obstacle_source="synthetic_fixture", observation_age_s=0,
            signal_id=action["signal_id"], crossing_id=action["crossing_id"], raw_state=signal, stable_state=signal,
            quality_flags=["CAMERA_STALE"] if self.scenario == "stale_image" else [],
            preprocess_profile="fixture-no-images", zone_id=action["zone_id"],
            front_left_status="INSIDE", front_right_status="OUTSIDE" if self.scenario == "one_foot" else "INSIDE",
            feet_evidence_kind="SIM_GT", body_motion_status="STOPPED" if self.held else "MOVING",
            full_body_inside=True, posture="SIT", full_body_crossed=elapsed >= .4, terrain_complete=elapsed >= .4,
        )


class ContractExecutor:
    """One attempt/generation fence and local monotonic dwell, independent of UI."""
    def __init__(self, run, adapter, *, clock=time.monotonic):
        if adapter.mode != "fixture":
            raise MissionConflict("NATIVE_ACTION_INTEGRATION_REQUIRED")
        self.run, self.adapter, self.clock = run, adapter, clock
        self.state = run["fixture_state"]
        self.started = clock()
        self.step_started = self.started
        self.valid_since = None
        self.last_receipt = None
        self.producer = None
        self.sequence = -1
        self.config_hash = None
        self._begin()

    def event(self, name):
        events = self.run["events"]
        if events and events[-1]["event"] == name:
            return
        self.state["event_seq"] += 1
        events.append({"seq": self.state["event_seq"], "event": name, "elapsed_s": round(self.clock() - self.started, 3), "step_id": self.state.get("step_id"), "generation": self.state["goal_generation"], "evidence_type": "fixture"})
        self.run["events"] = events[-120:]

    def _begin(self):
        s = self.state
        if s["current_index"] >= len(self.run["definition"]["visits"]):
            s.update(state="completed", phase="COMPLETED", outcome="fixture_completed", goal_id=None, reason=None)
            self.event("FIXTURE_COMPLETED_NO_ROBOT_EVIDENCE")
            return
        visit = self.run["definition"]["visits"][s["current_index"]]
        self.action = copy.deepcopy(visit["mission_action"])
        s.update(step_id=self.action["step_id"], phase="FOLLOWING", reason=None, dwell_elapsed_s=0.0, observation=None)
        self.step_started = self.clock()
        self.valid_since = self.last_receipt = None
        s["waypoints"][s["current_index"]].update(status="running", attempts=1)
        self._dispatch("approach", visit)

    def _dispatch(self, leg, visit):
        s = self.state
        s["goal_generation"] += 1
        # Exact saved fields go through this port; no reinterpreted arrival enum.
        command = {"schema_version": "mission-action-dispatch.v0.1", "mode": "fixture", "owner_id": self.adapter.owner_id,
                   "mission_run_id": s["id"], "visit_id": visit["visit_id"], "step_id": self.action["step_id"],
                   "goal_generation": s["goal_generation"], "request_id": secrets.token_hex(16), "leg": leg,
                   "action": copy.deepcopy(self.action), "visit": copy.deepcopy(visit), "snapshot_pins": copy.deepcopy(self.run["snapshot_pins"])}
        s["goal_id"] = self.adapter.dispatch(command)
        self.event("FIXTURE_DISPATCH_" + leg.upper())

    def _constraint(self, mode, reason):
        s = self.state
        value = {"schema_version": "motion-constraint.v0.1", "owner_id": self.adapter.owner_id, "run_id": s["id"],
                 "step_id": s["step_id"], "request_id": secrets.token_hex(16), "generation": s["goal_generation"],
                 "reason": reason, "mode": mode, "max_vx": 0.0 if mode == "HOLD" else None,
                 "max_vy": 0.0 if mode == "HOLD" else None, "max_wz": 0.0 if mode == "HOLD" else None,
                 "validity": "current_generation_only", "priority": "mission_hold", "evidence_type": "fixture"}
        self.adapter.constrain(value)
        s["motion_constraint"] = value
        self.event("FIXTURE_" + mode)

    def _reset_dwell(self, reason):
        self.valid_since = None
        self.state.update(dwell_elapsed_s=0.0, reason=reason)

    def _dwell(self, valid, duration, reason):
        if not valid:
            self._reset_dwell(reason)
            return False
        if self.valid_since is None:
            self.valid_since = self.clock()
        self.state["dwell_elapsed_s"] = round(max(0, self.clock() - self.valid_since), 3)
        self.state["reason"] = "CONTINUOUS_PHYSICAL_CONDITION_TIMER"
        return self.clock() - self.valid_since >= duration

    def fail(self, reason, *, interrupted=False):
        self._constraint("HOLD", reason)
        self._reset_dwell(reason)
        self.state.update(state="failed", phase="INTERRUPTED" if interrupted else "FAILED", outcome="interrupted" if interrupted else reason, goal_id=None, observation=None)
        if self.state["current_index"] < len(self.state["waypoints"]):
            self.state["waypoints"][self.state["current_index"]]["status"] = "failed"
        self.event(reason)

    def _complete_step(self):
        s = self.state
        s["waypoints"][s["current_index"]]["status"] = "completed"
        self.event("FIXTURE_STEP_COMPLETED")
        s["current_index"] += 1
        s["completed_count"] += 1
        self._begin()

    def tick(self, evidence=None):
        s = self.state
        if s["state"] != "running":
            return
        now = self.clock()
        s["elapsed_s"] = round(now - self.started, 3)
        if now - self.step_started > self.action["timeout_seconds"]:
            self.fail("SIGNAL_WAIT_TIMEOUT" if s["phase"] == "HOLD_SIGNAL" else "ACTION_TIMEOUT")
            return
        try:
            e = evidence if isinstance(evidence, Evidence) else Evidence.model_validate(evidence) if evidence is not None else self.adapter.sample(s)
        except (ValueError, TypeError):
            self._reset_dwell("INVALID_ADAPTER_EVIDENCE")
            s["observation"] = None
            return
        bound = (e.owner_id, e.mission_run_id, e.step_id, e.goal_id, e.goal_generation)
        expected = (self.adapter.owner_id, s["id"], s["step_id"], s["goal_id"], s["goal_generation"])
        if bound != expected:
            self._reset_dwell("STALE_OWNER_OR_GENERATION")
            s["observation"] = None
            return
        producer = (e.producer_id, e.producer_epoch)
        if (self.producer is not None and producer != self.producer) or e.sequence <= self.sequence:
            self._reset_dwell("PRODUCER_EPOCH_OR_SEQUENCE_CHANGED")
            s["observation"] = None
            return
        self.producer, self.sequence = producer, e.sequence
        if self.config_hash is not None and e.config_hash != self.config_hash:
            self._reset_dwell("EVIDENCE_CONFIG_CHANGED_REVALIDATE")
            s["observation"] = None
            return
        self.config_hash = e.config_hash
        s["observation"] = e.model_dump()
        if e.evidence_type != "fixture" or e.source_clock != "fixture" or e.source_age_s > FRESH_S:
            self._reset_dwell("EVIDENCE_STALE_OR_WRONG_MODE")
            return
        if self.last_receipt is not None and now - self.last_receipt > FRESH_S:
            self._reset_dwell("EVIDENCE_GAP_RESTARTS_DWELL")
        self.last_receipt = now
        if e.pose is None:
            self._reset_dwell("CURRENT_POSE_MISSING")
            return
        if s["phase"] not in {"HOLD_SIGNAL", "PARK_HOLD"}:
            if e.goal_state == "FAILED":
                self.fail("NAVIGATION_PROGRESS_FAILED")
                return
            if e.obstacle_state in {"WAIT_OBSTACLE", "SENSOR_UNAVAILABLE", "REPLANNING"}:
                s["reason"] = e.obstacle_state
                return
            if e.goal_state == "CANCELED" and not e.cancel_ack:
                s["reason"] = "CANCEL_ACK_REQUIRED"
                return
            if e.goal_state == "CANCELED" and (self.action["type"] not in {"TRAFFIC_STOP_AND_GO", "PARK_SIT_HOLD"} or s["phase"] == "EXITING"):
                self.fail("NAVIGATION_CANCELED")
                return
            if e.goal_state not in {"SUCCEEDED", "CANCELED"}:
                s["reason"] = "APPROACH_TERMINAL_REQUIRED"
                return
            if self.action["type"] == "TRAFFIC_STOP_AND_GO" and s["phase"] != "EXITING":
                self._constraint("HOLD", "HOLD_SIGNAL")
                s.update(phase="HOLD_SIGNAL", reason="HOLD_ACK_REQUIRED")
                return
            if self.action["type"] == "PARK_SIT_HOLD":
                self._constraint("HOLD", "PARK_HOLD")
                s.update(phase="PARK_HOLD", reason="HOLD_ACK_REQUIRED")
                return
        if s["phase"] == "HOLD_SIGNAL":
            physical = e.hold_ack and e.zone_id == self.action["zone_id"] and e.front_left_status == e.front_right_status == "INSIDE" and e.feet_evidence_kind == "SIM_GT" and e.body_motion_status == "STOPPED"
            ready = self._dwell(physical, self.action["dwell_seconds"], "BOTH_FEET_AND_PHYSICAL_STOP_REQUIRED")
            if not ready:
                return
            if e.quality_flags:
                s["reason"] = ",".join(e.quality_flags)
                return
            if (e.signal_id, e.crossing_id) != (self.action["signal_id"], self.action["crossing_id"]):
                s["reason"] = "SIGNAL_ASSOCIATION_MISMATCH"
                return
            if e.stable_state != "GREEN":
                s["reason"] = "SIGNAL_" + e.stable_state
                return
            if not e.path_clear or e.obstacle_state in {"WAIT_OBSTACLE", "SENSOR_UNAVAILABLE", "FAILED"}:
                s["reason"] = "WAIT_OBSTACLE"
                return
            self._constraint("RELEASE", "FRESH_GREEN_PATH_POSE")
            s["phase"] = "EXITING"
            self._dispatch("exit", self.run["definition"]["visits"][s["current_index"]])
            # No previous velocity is stored or replayed. Exit is a new goal generation.
            return
        if s["phase"] == "PARK_HOLD":
            if not self._dwell(e.hold_ack and e.zone_id == self.action["zone_id"] and e.full_body_inside and e.posture == "SIT" and e.body_motion_status == "STOPPED", self.action["sit_seconds"], "FULL_CONTAINMENT_SIT_AND_STOP_REQUIRED"):
                return
        elif self.action["type"] == "FINISH_CROSSING" and not (e.full_body_crossed and e.zone_id == self.action["zone_id"]):
            s["reason"] = "FULL_BODY_OUT_LINE_CROSSING_REQUIRED"
            return
        elif self.action["type"] == "TRAVERSE_TERRAIN" and not e.terrain_complete:
            s["reason"] = "VERIFIED_GAIT_COMPLETION_REQUIRED"
            return
        self._complete_step()


def new_fixture_state(identifier, definition):
    return {"id": identifier, "label": definition["label"], "state": "ready", "phase": "READY", "outcome": None,
            "owner_id": "competition-fixture-no-motion", "mode": "fixture", "timer_owner": "onboard_backend",
            "current_index": 0, "completed_count": 0, "goal_generation": 0, "goal_id": None,
            "dwell_elapsed_s": 0.0, "elapsed_s": 0.0, "event_seq": 0, "observation": None,
            "reason": "EXPLICIT_FIXTURE_NOT_ROBOT_EXECUTION", "motion_constraint": None,
            "waypoints": [{"visit_id": v["visit_id"], "label": v["label"], "status": "pending", "attempts": 0} for v in definition["visits"]]}


class FixtureRuns:
    def __init__(self, service):
        self.service = service
        self.executors, self.tasks = {}, {}
        self.lock = asyncio.Lock()
        changed = False
        for run in service.data["runs"].values():
            s = run.get("fixture_state")
            if s and s["state"] == "running":
                s.update(state="failed", phase="INTERRUPTED", outcome="interrupted", reason="SERVER_RESTART_INTERRUPTED", dwell_elapsed_s=0, observation=None, goal_id=None, motion_constraint=None)
                for v in s["waypoints"]:
                    if v["status"] == "running":
                        v["status"] = "failed"
                changed = True
        if changed:
            service._save()

    def snapshot(self, run):
        executor = self.executors.get(run["id"])
        # A failed atomic store write may roll the facade back to its last
        # durable copy. Never present that old RUNNING snapshot as live after
        # this process has stopped the fixture executor.
        s = copy.deepcopy(executor.state if executor else run["fixture_state"])
        receipt = executor.last_receipt if executor else None
        s["receipt_age_s"] = round(max(0, executor.clock() - receipt), 3) if receipt is not None else None
        if s.get("observation") and s["receipt_age_s"] is not None:
            s["observation"]["source_age_s"] += s["receipt_age_s"]
        s.update(ownership_active=False, logs=copy.deepcopy((executor.run if executor else run)["events"]), hold_remaining=None, physical_stop_observed=None)
        return s

    async def action(self, identifier, action):
        async with self.lock:
            run = self.service.data["runs"][identifier]
            if identifier in self.executors:
                run = self.executors[identifier].run
            s = run["fixture_state"]
            if action == "start":
                if s["state"] == "running":
                    return
                if s["state"] != "ready":
                    raise MissionConflict("FIXTURE_RESTART_REQUIRES_NEW_ATTEMPT")
                if any(not task.done() for task in self.tasks.values()):
                    raise MissionConflict("FIXTURE_ATTEMPT_ALREADY_ACTIVE")
                s["state"] = "running"
                executor = ContractExecutor(run, FixtureAdapter(run["scenario"]))
                self.executors[identifier] = executor
                try:
                    self.service._save()
                except Exception:
                    executor.fail("FIXTURE_AUDIT_STORAGE_UNAVAILABLE")
                    raise
                self.tasks[identifier] = asyncio.create_task(self._monitor(identifier), name="competition-fixture-no-motion")
            elif action in {"abort", "pause"}:
                executor = self.executors.get(identifier)
                if executor and s["state"] == "running":
                    executor.fail("FIXTURE_ABORTED")
                    self.service._save()
            else:
                raise MissionConflict("COMPETITION_HAS_NO_MANUAL_GREEN_SKIP_OR_RESUME")

    async def _monitor(self, identifier):
        executor = self.executors[identifier]
        try:
            while executor.state["state"] == "running":
                await asyncio.sleep(.2)
                async with self.lock:
                    if executor.state["state"] != "running":
                        break
                    if self.service.context.snapshot()["navigation_context_revision"] != executor.run["snapshot_pins"]["context_revision"]:
                        executor.fail("RUN_CONTEXT_CHANGED_REVALIDATE")
                    executor.tick()
                    self.service.data["runs"][identifier] = executor.run
                    self.service._save()
        except asyncio.CancelledError:
            raise
        except Exception:
            executor.fail("FIXTURE_BACKEND_FAILED")
            try:
                self.service.data["runs"][identifier] = executor.run
                self.service._save()
            except Exception:
                pass

    async def close(self):
        try:
            async with self.lock:
                for identifier, executor in self.executors.items():
                    if executor.state["state"] == "running":
                        executor.fail("SERVER_RESTART_INTERRUPTED", interrupted=True)
                    self.service.data["runs"][identifier] = executor.run
                for task in self.tasks.values():
                    task.cancel()
                if self.executors:
                    self.service._save()
        finally:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)
