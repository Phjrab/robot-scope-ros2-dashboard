import { api } from '../../core/api.js';
import { createRoutePlannerPanel } from '../cockpit/panels/route_planner_panel.js';
import { createRoutePlannerClient } from '../cockpit/route_planner_client.js';

const host = document.querySelector('#dashboardRoutePlannerHost');
const client = createRoutePlannerClient({ api });
const panel = createRoutePlannerPanel({ client, document });
let activePage = '';

panel.mount(host);

function sync() {
  if (activePage === 'route-planner' && !document.hidden) panel.activate();
  else panel.deactivate();
}

document.addEventListener('robot-scope:page-change', (event) => {
  activePage = String(event.detail?.activePage || '');
  sync();
});
document.addEventListener('visibilitychange', sync);
window.addEventListener('pageshow', sync);
window.addEventListener('pagehide', () => panel.deactivate());

window.RobotScopeRoutePlanner = Object.freeze({
  snapshot: () => client.snapshot(),
  diagnostics: () => Object.freeze({ client: client.diagnostics(), panel: panel.diagnostics() }),
});
