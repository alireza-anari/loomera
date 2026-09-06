const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');

const utilsSource = readFileSync(resolve(__dirname, '../static/js/utils.js'), 'utf8');
const utilsUrl = `data:text/javascript;base64,${Buffer.from(utilsSource).toString('base64')}`;

function browser(clipboard, legacyResult = true) {
  const calls = { removed: 0, restored: 0, legacy: 0, feedback: [], selected: 0 };
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { clipboard } });
  globalThis.window = { LoomeraFeedback: { show: (...args) => calls.feedback.push(args) } };
  globalThis.document = {
    activeElement: { focus: () => calls.restored++ },
    body: { appendChild: () => {} },
    createElement: () => ({ style: {}, setAttribute() {}, focus() {}, select() {},
      setSelectionRange() {}, remove: () => calls.removed++ }),
    execCommand: () => { calls.legacy++; return legacyResult; },
    addEventListener: (_type, listener) => { calls.click = listener; },
  };
  return calls;
}

test('modern clipboard copies the complete URL', async () => {
  let copied;
  const calls = browser({ writeText: async (text) => { copied = text; } });
  const { copyText } = await import(utilsUrl);
  assert.equal(await copyText('https://example.test/?start=loomi_s_12'), true);
  assert.equal(copied, 'https://example.test/?start=loomi_s_12');
  assert.equal(calls.legacy, 0);
});

test('clipboard unavailable uses fallback and restores focus', async () => {
  const calls = browser(undefined);
  const { copyText } = await import(utilsUrl);
  assert.equal(await copyText('sample-link'), true);
  assert.equal(calls.legacy, 1);
  assert.equal(calls.removed, 1);
  assert.equal(calls.restored, 1);
});

test('denied clipboard permission also uses fallback', async () => {
  const calls = browser({ writeText: async () => { throw new Error('denied'); } });
  const { copyText } = await import(utilsUrl);
  assert.equal(await copyText('sample-link'), true);
  assert.equal(calls.removed, 1);
});

async function clickCopy(success) {
  const calls = browser(success ? { writeText: async () => {} } : undefined, false);
  const input = { value: 'https://example.test/link', focus() {},
    select: () => calls.selected++, setSelectionRange() {} };
  const button = { disabled: false, closest: () => ({ querySelector: () => input }) };
  const source = readFileSync(resolve(__dirname, '../static/js/pages/loomi_share_links.js'), 'utf8')
    .replace("'../utils.js'", JSON.stringify(utilsUrl)) + `\n// case ${success}`;
  await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
  await calls.click({ target: { closest: () => button } });
  assert.equal(button.disabled, false);
  return calls;
}

test('successful button uses existing Loomera feedback', async () => {
  const calls = await clickCopy(true);
  assert.equal(calls.feedback[0][0], 'لینک لومی کپی شد.');
  assert.equal(calls.feedback[0][1], 'success');
});

test('failed copy selects visible URL for manual copying without claiming success', async () => {
  const calls = await clickCopy(false);
  assert.equal(calls.selected, 1);
  assert.equal(calls.feedback[0][1], 'info');
  assert.equal(calls.removed, 1);
});
