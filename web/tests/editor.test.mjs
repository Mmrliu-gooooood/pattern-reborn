import test from 'node:test';
import assert from 'node:assert/strict';
import { historyReducer, initialHistory, imagePoint, orderedBox } from '../src/history.js';
test('undo/redo preserves edit states and a new edit drops the redo branch', () => {
  let state = initialHistory({ strokes: [] });
  state = historyReducer(state, { type: 'set', value: { strokes: ['keep'] } });
  state = historyReducer(state, { type: 'undo' });
  assert.deepEqual(state.present.strokes, []);
  state = historyReducer(state, { type: 'redo' });
  assert.deepEqual(state.present.strokes, ['keep']);
  state = historyReducer(state, { type: 'undo' });
  state = historyReducer(state, { type: 'set', value: { strokes: ['remove'] } });
  assert.deepEqual(historyReducer(state, { type: 'redo' }).present.strokes, ['remove']);
});
test('scaled, panned canvas uses working-image coordinates and clamps outside drags', () => {
  const rect = { left: 100, top: 50, width: 400, height: 200 };
  assert.deepEqual(imagePoint(300, 150, rect, 1600, 800), [800, 400]);
  assert.deepEqual(imagePoint(-100, 999, rect, 1600, 800), [0, 799]);
  assert.deepEqual(orderedBox([200, 600], [800, 50]), [200, 50, 800, 600]);
});
