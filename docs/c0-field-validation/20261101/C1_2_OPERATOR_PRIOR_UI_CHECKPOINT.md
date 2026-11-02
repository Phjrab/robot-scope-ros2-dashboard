# Operator prior UI checkpoint — 2026-11-01

Status: checkpoint only. Integration with the backend operator-prior implementation has not been verified, and this checkpoint is not evidence of deployment or robot operation.

The preparation UI collects an operator's current map pose draft, uncertainty bounds and an explicit stationary acknowledgement before requesting a staged proposal. The draft is operator input, not a measured pose. A conditional proposal requires a separate acknowledgement before confirmation; the UI preserves the distinction between conditional selection and globally verified uniqueness. Existing source, freshness and safety gates remain in place, and sending an initial pose still requires an explicit action.

The displayed preparation flow combines initial-pose acceptance and matching in one step. Drafts are retained visibly as unconfirmed during temporary read failures, while changes to the relevant map, observation or runtime context invalidate or demote their current use.

## Local verification

- The first browser run started 54 tests: 31 passed and 23 failed. A later repaired run passed 60 tests on an earlier candidate snapshot; subsequent changes mean that run does not verify the final snapshot in full.
- Separate targeted browser runs on the later candidate passed 5, 3 and 1 tests respectively. A goal-flow run had 6 passes and 1 failure; the isolated failed case passed after the UI wording was repaired.
- The targeted Node runs passed 4 draft tests and 13 preparation tests. A filtered dataset contract run passed 1 test with 11 skipped. JavaScript syntax checks passed.

The complete suite was not rerun on the final candidate. Browser-to-backend integration with the operator-prior implementation, hardware operation and deployment were not tested. Test runs above are separate and should not be added together as a single suite result.
