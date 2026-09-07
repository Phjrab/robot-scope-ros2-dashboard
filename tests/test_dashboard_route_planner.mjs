import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const index = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');
const app = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const styles = readFileSync(new URL('../robot_dashboard/static/styles.css', import.meta.url), 'utf8');
const dashboardPage = readFileSync(new URL('../robot_dashboard/static/features/route_planner/dashboard_page.js', import.meta.url), 'utf8');

test('main dashboard exposes Route Planner as an independent page and overview shortcut', () => {
  assert.match(index, /href="#route-planner" data-nav="route-planner"/);
  assert.match(index, /data-page="route-planner"/);
  assert.match(index, /id="dashboardRoutePlannerHost"/);
  assert.match(index, /SERVER-AUTHORITATIVE · NO MOTION AUTHORITY/);
  assert.match(index, /로봇 제어 권한, Nav2 goal, ARM 또는 deadman을 획득하지 않습니다/);
});

test('standalone page reuses the Route Planner client and panel with page-scoped polling', () => {
  assert.match(app, /features\/route_planner\/dashboard_page\.js/);
  assert.match(app, /robot-scope:page-change/);
  assert.match(dashboardPage, /createRoutePlannerClient\(\{ api \}\)/);
  assert.match(dashboardPage, /createRoutePlannerPanel\(\{ client, document \}\)/);
  assert.match(dashboardPage, /panel\.mount\(host\)/);
  assert.match(dashboardPage, /activePage === 'route-planner' && !document\.hidden/);
  assert.match(dashboardPage, /panel\.deactivate\(\)/);
  assert.match(dashboardPage, /RobotScopeRoutePlanner/);
  assert.doesNotMatch(dashboardPage, /\/api\/v1\/control|\/navigation\/goal|lease|deadman|cmd_vel|sport/i);
});

test('standalone Route Planner layout is wide and has a single-column responsive fallback', () => {
  assert.match(styles, /\.route-planner-dashboard-host \.cockpit-route-planner \{ grid-template-columns:/);
  assert.match(styles, /\.route-planner-dashboard-host \.route-planner-planning \{ grid-column:2;/);
  assert.match(styles, /\.route-planner-dashboard-host \.cockpit-route-planner \{ grid-template-columns:1fr; \}/);
});
