// Executes the production worker in Node's VM with an in-memory fetch response.
// No network function is supplied to the sandbox.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../fetch-worker.js', import.meta.url), 'utf8');
for (const [header, expected] of [[null, -1], ['0', 0], ['2', 2], ['600', 600], [' 2 ', 2], ['601', -2], ['3600', -2], ['1.5', -2], ['Wed, 09 Sep 2026 12:00:00 GMT', -2]]) {
  test(`preserves safe retry policy for ${header ?? 'absent header'}`, async () => {
    let cancelled = false;
    let calls = 0;
    const self = {postMessage() {}, close() {}, crossOriginIsolated: true};
    const context = vm.createContext({
      self, SharedArrayBuffer, Int32Array, Uint8Array, Atomics,
      TextEncoder, TextDecoder, AbortController, setTimeout, clearTimeout,
      fetch: async (url, options) => {
        assert.equal(url, 'https://api.openai.com/v1/chat/completions');
        assert.equal(options.credentials, 'omit');
        assert.equal(options.redirect, 'error');
        calls++;
        return {
          status: 429, redirected: false, type: 'basic',
          headers: {get(name) {assert.equal(name, 'retry-after'); return header;}},
          body: {cancel() {cancelled = true;}},
        };
      },
    });
    vm.runInContext(source, context);
    const buffer = new SharedArrayBuffer(1024 * 1024 + 20);
    await self.onmessage({data: {
      type: 'request', id: 1, method: 'POST',
      url: 'https://api.openai.com/v1/chat/completions',
      headers: {authorization: 'Bearer fictional-fixture-key'},
      body: '{"model":"gpt-4o-mini"}', buffer, timeoutMs: 1000,
    }});
    const control = new Int32Array(buffer, 0, 5);
    assert.equal(control[0], 1);
    assert.equal(control[2], 429);
    assert.equal(control[3], expected);
    assert.equal(cancelled, true);
    assert.equal(calls, 1);
    const response = new TextDecoder().decode(new Uint8Array(buffer, 20, control[1]));
    assert.equal(JSON.parse(response).error.message, 'Provider request failed.');
    assert.equal(response.includes('fictional-fixture-key'), false);
  });
}
