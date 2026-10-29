# C5 integration points — deferred

No integration is performed by this branch. All shared/peer source remains read
only. The module is safe to import: it creates no DOM, subscriptions, observers,
network requests, control requests, global listeners or timers on import.

1. **CSS:** after the existing theme/typography and relevant feature stylesheet,
   load `features/operator_usability/operator_usability.css`. Rules require the
   matching feature class/root plus `data-operator-usability`; merely loading
   the file does not change existing views.
2. **Main navigation host:** after the existing Navigation DOM is mounted,
   call `mountOperatorUsability(document.querySelector('[data-page="navigation"]'),
   'navigation')`. This opts in coordinate/readout and error-message wrapping,
   adds a static sequencing hint and associates existing safety/localization
   text with the controls using `aria-describedby`. It does not observe,
   translate or decide localization/permission state. `navigation.js`,
   `scene3d.js`, official assets, draw functions and API handlers need no changes.
3. **C2 host, when C2 is actually integrated:** after C2 `mount` resolves/creates
   `.mmf`, call `mountOperatorUsability(root, 'multimap')`. This opts in readable
   review text, 44px actions, theme-token diagnostics, and a static filename-rule
   description. Rule source: C2 pinned `session.js:74–77`; validation remains C2's.
   Reconfirm that rule if C2 changes the export contract. Do not change save to
   operating-map apply or enable disabled review/save controls.
4. **C3 host, when C3 is actually integrated:** after `mountObstacleScene` creates
   `.obstacle-scene`, call `mountOperatorUsability(root, 'obstacles')` for readable
   text and 44px layer labels/actions. Its canvas, overlay, protection/evidence
   strings, style palette, subscription and freshness policies remain C3-owned.
5. Keep the returned handle and call `destroy()` before host replacement/unmount.
   Repeated mount on the same root is idempotent. Destroy removes only its own
   helper/description tokens and restores the previous scope attribute; it does
   not change focus or remove description tokens another caller added later.

The only future common-file connection is stylesheet loading and these explicit
mount/destroy calls in the owning host. No root-wide CSS, framework, automatic
navigation, control wiring, event interception, canvas resize/pointer rewrite,
URDF regeneration, coordinate adjustment or state translation is necessary.

Before any integration, address C5-H1 described in HANDOFF with C3's owner.
This display patch cannot certify a current risk assessment while C3's paused
view retains an expired FRESH snapshot. Re-run the supplied browser scripts and
existing Navigation/URDF tests against the final composed host. Main merge,
robot deployment and service restarts require the later approval phase.
