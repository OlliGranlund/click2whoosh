import test from 'node:test';
import assert from 'node:assert/strict';
import { createButtonFeedback, buttonHighlights, TAP_HIGHLIGHT_MS } from './buttonFeedback.js';

test('a press released between polls still flashes, then expires', () => {
  const feedback = createButtonFeedback();
  const released = { held: { right: [] }, counts: { right: { plus: 1 } } };
  assert.deepEqual(buttonHighlights(feedback, released, 10).right, ['plus']);
  assert.deepEqual(buttonHighlights(feedback, released, 10 + TAP_HIGHLIGHT_MS).right, []);
});

test('a rapid second tap refreshes its pulse; duplicate snapshots do not', () => {
  const feedback = createButtonFeedback();
  buttonHighlights(feedback, { counts: { right: { plus: 1 } } }, 0);
  buttonHighlights(feedback, { counts: { right: { plus: 2 } } }, 100);
  assert.deepEqual(buttonHighlights(feedback, { counts: { right: { plus: 2 } } }, 200).right, ['plus']);
  assert.deepEqual(buttonHighlights(feedback, { counts: { right: { plus: 2 } } }, 300).right, []);
});

test('a long hold stays lit and independent taps on both sides survive a poll', () => {
  const feedback = createButtonFeedback();
  const snapshot = { held: { right: ['plus'] }, counts: { left: { minus: 3 }, right: { plus: 2, b: 1 } } };
  assert.deepEqual(buttonHighlights(feedback, snapshot, 0), { left: ['minus'], right: ['b', 'plus'] });
  assert.deepEqual(buttonHighlights(feedback, snapshot, 1000), { left: [], right: ['plus'] });
});

test('disconnect clears the pulse and idle polls never invent another press', () => {
  const feedback = createButtonFeedback();
  const snapshot = { held: {}, counts: { left: { minus: 1 } }, epochs: { left: 0 } };
  buttonHighlights(feedback, snapshot, 0);
  const disconnected = { held: {}, counts: {}, epochs: { left: 1 } };
  assert.deepEqual(buttonHighlights(feedback, disconnected, 10).left, []);
  assert.deepEqual(buttonHighlights(feedback, disconnected, 600000).left, []);
  assert.deepEqual(buttonHighlights(feedback, { ...disconnected, counts: { left: { minus: 1 } } }, 600010).left, ['minus']);
});
