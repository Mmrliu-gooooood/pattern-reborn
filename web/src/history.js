export const initialHistory = value => ({ past: [], present: value, future: [] });
export function historyReducer(state, action) {
  if (action.type === 'reset') return initialHistory(action.value);
  if (action.type === 'undo' && state.past.length) return { past: state.past.slice(0, -1), present: state.past.at(-1), future: [state.present, ...state.future] };
  if (action.type === 'redo' && state.future.length) return { past: [...state.past, state.present], present: state.future[0], future: state.future.slice(1) };
  if (action.type === 'set' && JSON.stringify(action.value) !== JSON.stringify(state.present)) return { past: [...state.past, state.present].slice(-100), present: action.value, future: [] };
  return state;
}
export function imagePoint(clientX, clientY, rect, width, height) {
  return [Math.max(0, Math.min(width - 1, Math.round((clientX - rect.left) * width / rect.width))), Math.max(0, Math.min(height - 1, Math.round((clientY - rect.top) * height / rect.height)))];
}
export const orderedBox = (a, b) => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])];
