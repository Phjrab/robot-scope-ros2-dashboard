import test from 'node:test';
import assert from 'node:assert/strict';
import { projectState } from '../robot_dashboard/static/features/cockpit/route_planner_client.js';

test('order projection preserves eight grouped sheets and forty menu rows', () => {
  const orders = Array.from({ length: 8 }, () => ({
    destination_id: 'COEX',
    lines: Array.from({ length: 5 }, (_, index) => ({
      sequence: index + 1,
      restaurant_id: 'HANSOT',
      menu_id: 'CHICKEN_MAYO',
      quantity: 1,
    })),
  }));
  const order = {
    id: 'a'.repeat(32), revision: 'b'.repeat(64), label: 'Eight sheets',
    orders, lines: orders.flatMap((sheet) => sheet.lines), order_count: 8,
  };
  const projected = projectState({ available: true, state: 'ORDER_READY', order }).order;
  assert.equal(projected.orders.length, 8);
  assert.equal(projected.lines.length, 40);
  assert.equal(projected.order_count, 8);
});
