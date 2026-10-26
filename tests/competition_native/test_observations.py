from dataclasses import replace
from types import SimpleNamespace
import unittest

from robot_dashboard.mission_routes.competition_native import TimingPolicy
from robot_dashboard.mission_routes.competition_native.observations import Extras, Normalizer, ObservationRejected, from_vm_stop_input
from .helpers import Rig


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.r = Rig()
        self.n = Normalizer(self.r.scope, TimingPolicy.synthetic(), self.r.bindings, synthetic=True, receiver_session_id=self.r.adapter.receiver_session_id)

    def test_component_source_and_receiver_age_are_independent(self):
        p = self.r.packet()
        parts = dict(p.components)
        parts["signal"] = replace(parts["signal"], source_age_s=0.4)
        frame = self.n.receive(replace(p, components=parts), 10.0)
        self.assertTrue(frame.fresh("signal", "pose"))
        frame = self.n.current(10.100001)
        self.assertFalse(frame.fresh("signal"))
        self.assertTrue(frame.fresh("pose"))

    def test_duplicate_envelope_never_refreshes_ttl(self):
        p = self.r.packet()
        self.n.receive(p, 0)
        with self.assertRaisesRegex(ObservationRejected, "DUPLICATE"):
            self.n.receive(p, 0.2)
        self.assertIsNone(self.n.current(0.2))

    def test_component_reuse_keeps_original_receipt(self):
        p = self.r.packet()
        self.n.receive(p, 0)
        q = self.r.packet()
        parts = dict(q.components)
        parts["signal"] = p.components["signal"]
        frame = self.n.receive(replace(q, components=parts), 0.500001)
        self.assertFalse(frame.fresh("signal"))
        self.assertTrue(frame.fresh("pose"))
        self.assertEqual(frame.components["signal"].receipt_s, 0)

    def test_duplicate_component_cannot_change_payload(self):
        p = self.r.packet()
        self.n.receive(p, 0)
        q = self.r.packet(stable_state="RED")
        with self.assertRaisesRegex(ObservationRejected, "CHANGED"):
            self.n.receive(replace(q, components=p.components), 0.1)

    def test_each_identity_field_is_fenced(self):
        for key, value in (("owner_id", "foreign"), ("mission_run_id", "e" * 32),
                           ("step_id", "e" * 32), ("goal_id", "e" * 32),
                           ("goal_generation", 2), ("config_hash", "e" * 64)):
            with self.subTest(key=key), self.assertRaisesRegex(ObservationRejected, "SCOPE"):
                self.n.receive(self.r.packet(**{key: value}), 0)

    def test_wrong_component_generation_is_rejected_even_with_matching_envelope(self):
        p = self.r.packet()
        parts = dict(p.components)
        parts["signal"] = replace(parts["signal"], scope=replace(self.r.scope, goal_generation=2))
        with self.assertRaisesRegex(ObservationRejected, "COMPONENT_SCOPE"):
            self.n.receive(replace(p, components=parts), 0)

    def test_unverified_clock_and_old_epoch_cannot_be_restamped(self):
        for binding in (replace(self.r.bindings["signal"], relation_verified=False),
                        replace(self.r.bindings["signal"], epoch="epoch-2"),
                        replace(self.r.bindings["signal"], source_clock="synchronized_ros")):
            n = Normalizer(self.r.scope, TimingPolicy.synthetic(), {**self.r.bindings, "signal": binding}, synthetic=True, receiver_session_id=self.r.adapter.receiver_session_id)
            with self.assertRaises(ObservationRejected):
                n.receive(self.r.packet(), 100000.0)

    def test_retired_epoch_envelope_is_rejected(self):
        with self.assertRaisesRegex(ObservationRejected, "EPOCH"):
            self.n.receive(self.r.packet(producer_epoch="old-epoch"), 0)

    def test_generation_switch_preserves_replay_highwater(self):
        p = self.r.packet()
        self.n.receive(p, 0)
        scope = replace(self.r.scope, goal_id="f" * 32, goal_generation=2)
        self.n.change_scope(scope)
        data = {**p.evidence, **vars(scope), "sequence": 2}
        parts = {k: replace(s, scope=scope) for k, s in p.components.items()}
        with self.assertRaisesRegex(ObservationRejected, "REPLAY"):
            self.n.receive(replace(p, evidence=data, components=parts), 0.1)

    def test_native_rejects_fixture_and_unknown_clock(self):
        n = Normalizer(self.r.scope, TimingPolicy.synthetic(), self.r.bindings, receiver_session_id=self.r.adapter.receiver_session_id)
        with self.assertRaisesRegex(ObservationRejected, "NOT_NATIVE"):
            n.receive(self.r.packet(), 0)
        with self.assertRaises(ObservationRejected):
            self.n.receive(self.r.packet(source_clock="remote_monotonic"), 0)

    def test_finite_age_sequence_and_clock_boundaries(self):
        for change in ({"source_age_s": float("nan")}, {"source_age_s": -1},
                       {"sequence": True}, {"source_stamp_ns": "bad"}):
            p = self.r.packet()
            parts = dict(p.components)
            parts["pose"] = replace(parts["pose"], **change)
            with self.subTest(change=change), self.assertRaises(ObservationRejected):
                self.n.receive(replace(p, components=parts), 0)
        self.n.receive(self.r.packet(), 1)
        with self.assertRaisesRegex(ObservationRejected, "ROLLBACK"):
            self.n.current(0.99)

    def test_invalid_extras_boolean_does_not_become_truthy(self):
        with self.assertRaisesRegex(ObservationRejected, "BOOLEAN"):
            self.n.receive(self.r.packet(extras=Extras(estop="false")), 0)

    def test_vm_stopinput_translation_does_not_promote_approach_ack(self):
        p = self.r.packet()
        value = SimpleNamespace(run_id=self.r.scope.mission_run_id, step_id=self.r.scope.step_id,
            generation=1, sequence=p.evidence["sequence"], epoch="epoch-1", signal_id="signal-1", crossing_id="crossing-1", stable_state="GREEN",
            zone_id="zone-1", left_inside=True, right_inside=False, feet_kind="SIM_GT",
            body_stopped=True, path_clear=True, fully_crossed=False, observation_age_s=0.0,
            signal_age_s=0.0, localization_ready=True, departure_observed=False,
            safety_stop=False, approach_ack=True)
        translated = from_vm_stop_input(value, envelope=p.evidence, stamps=p.components, receiver_session_id=p.receiver_session_id)
        frame = self.n.receive(translated, 0)
        self.assertEqual(frame.evidence.goal_state, "ACTIVE")
        self.assertEqual(frame.evidence.front_right_status, "OUTSIDE")
        self.assertEqual(frame.evidence.feet_evidence_kind, "SIM_GT")

    def test_canonical_schema_is_reused_without_new_wire_fields(self):
        from robot_dashboard.mission_routes.competition_contract import Evidence
        import json
        from pathlib import Path
        schema = json.loads(Path("docs/mission-competition/evidence.schema.json").read_text())
        self.assertEqual(schema, Evidence.model_json_schema())
        with self.assertRaises(ObservationRejected):
            self.n.receive(self.r.packet(departure_observed=True), 0)

    def test_restart_nonce_rejects_old_packet_even_if_epochs_match(self):
        p = self.r.packet()
        self.n.receive(p, 0)
        restarted = Normalizer(self.r.scope, TimingPolicy.synthetic(), self.r.bindings, synthetic=True)
        with self.assertRaisesRegex(ObservationRejected, "SESSION_RETIRED"):
            restarted.receive(p, 0)

    def test_new_sequence_cannot_launder_same_component_source_stamp(self):
        p = self.r.packet()
        self.n.receive(p, 0)
        q = self.r.packet()
        parts = dict(q.components)
        parts["signal"] = replace(parts["signal"], source_stamp_ns=p.components["signal"].source_stamp_ns)
        with self.assertRaisesRegex(ObservationRejected, "REPLAY"):
            self.n.receive(replace(q, components=parts), 0.1)

    def test_route_observation_age_is_not_laundered_by_envelope(self):
        frame = self.n.receive(self.r.packet(observation_age_s=2.0), 0)
        self.assertFalse(frame.fresh("path"))
        self.assertTrue(frame.fresh("pose"))

    def test_native_synchronized_clock_contract_accepts_pinned_components(self):
        bindings = {k: replace(v, source_clock="synchronized_ros") for k, v in self.r.bindings.items()}
        n = Normalizer(self.r.scope, TimingPolicy.synthetic(), bindings,
                       receiver_session_id=self.r.adapter.receiver_session_id)
        p = self.r.packet(source_clock="synchronized_ros", evidence_type="robot_observation",
                          feet_evidence_kind="KINEMATIC")
        p = replace(p, components={k: replace(s, source_clock="synchronized_ros") for k, s in p.components.items()})
        frame = n.receive(p, 2000)
        self.assertTrue(frame.fresh("signal", "feet", "motion"))
        self.assertEqual(frame.evidence.evidence_type, "robot_observation")
        # This is a synthetic contract test, not physical robot evidence.
