import test from 'node:test';
import assert from 'node:assert/strict';
import { projectState } from '../robot_dashboard/static/features/cockpit/route_planner_client.js';

test('order projection preserves all five grouped sheets and twenty-five menu rows', () => {
  const orders = Array.from({ length: 5 }, () => ({ destination_id: 'COEX', lines: Array.from({ length: 5 }, (_, i) => ({ sequence: i + 1, restaurant_id: 'HANSOT', menu_id: 'CHICKEN_MAYO', quantity: 1 })) }));
  const order = { id: 'a'.repeat(32), revision: 'b'.repeat(64), label: 'Roundtrip', orders, lines: orders.flatMap((s) => s.lines), order_count: 5 };
  const projected = projectState({ available: true, state: 'ORDER_READY', order }).order;
  assert.deepEqual(projected.orders, orders);
  assert.equal(projected.lines.length, 25);
  assert.ok(Object.isFrozen(projected.orders[0].lines[0]));
  orders[0].lines[0].quantity = 5;
  assert.equal(projected.orders[0].lines[0].quantity, 1);
});
