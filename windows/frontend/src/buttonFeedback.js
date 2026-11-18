// Counters retain short taps even when press and release arrive between polls.
// This visual pulse has no connection to keyboard injection or BLE timing.
export const BUTTON_POLL_MS = 50;
export const TAP_HIGHLIGHT_MS = 140;

export function createButtonFeedback() {
  return { counts: { left: {}, right: {} }, until: { left: {}, right: {} }, epochs: {} };
}

export function buttonHighlights(feedback, snapshot, now) {
  const result = {};
  for (const side of ['left', 'right']) {
    const epoch = snapshot.epochs?.[side] ?? 0;
    if (feedback.epochs[side] !== epoch) {
      feedback.until[side] = {};
      feedback.counts[side] = {};
    }
    feedback.epochs[side] = epoch;
    const counts = snapshot.counts?.[side] ?? {};
    for (const [button, count] of Object.entries(counts)) {
      if (count > (feedback.counts[side][button] ?? 0)) {
        feedback.until[side][button] = now + TAP_HIGHLIGHT_MS;
      }
    }
    feedback.counts[side] = { ...counts };
    const active = new Set(snapshot.held?.[side] ?? []);
    for (const [button, until] of Object.entries(feedback.until[side])) {
      if (until > now) active.add(button);
      else delete feedback.until[side][button];
    }
    result[side] = [...active].sort();
  }
  return result;
}

export function sameHighlights(a, b) {
  return ['left', 'right'].every(side => a[side].length === b[side].length &&
    a[side].every((button, index) => button === b[side][index]));
}
