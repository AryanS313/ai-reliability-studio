// Production nonstreaming bridge. No configurable fetch implementation, URL
// rewrite, fixture origin, console output, storage, credentials, or retries.
const MAX_BYTES = 1024 * 1024;
const CONTROL_BYTES = 20;
const ENDPOINTS = new Map([
  ['https://api.openai.com/v1/chat/completions', 'openai'],
  ['https://api.anthropic.com/v1/messages', 'anthropic'],
  ['https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent', 'gemini'],
  ['https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent', 'gemini'],
]);
const MODELS = {
  openai: new Set(['gpt-4o-mini', 'gpt-4.1-mini']),
  anthropic: new Set(['claude-sonnet-5', 'claude-haiku-4-5']),
};
let active = null;
let stopped = false;

function validatedRequest(data) {
  const provider = ENDPOINTS.get(data.url);
  if (!provider || data.method !== 'POST' || typeof data.body !== 'string' ||
      !Number.isInteger(data.id) || data.id < 1 ||
      !Number.isInteger(data.timeoutMs) || data.timeoutMs < 1 || data.timeoutMs > 30000) throw 0;
  const body = new TextEncoder().encode(data.body);
  if (body.byteLength > MAX_BYTES) throw 0;
  const payload = JSON.parse(data.body);
  if (!payload || typeof payload !== 'object' || Array.isArray(payload) ||
      ('stream' in payload && payload.stream !== false) ||
      (provider !== 'gemini' && !MODELS[provider].has(payload.model))) throw 0;
  const keyHeader = {openai:'authorization', anthropic:'x-api-key', gemini:'x-goog-api-key'}[provider];
  const key = data.headers?.[keyHeader];
  if (typeof key !== 'string' || !key.length || key.length > 8192 || /[^\x20-\x7e]/.test(key) ||
      (provider === 'openai' && (!key.startsWith('Bearer ') || !key.slice(7).trim()))) throw 0;
  const headers = {'content-type':'application/json', accept:'application/json', [keyHeader]:key};
  if (provider === 'anthropic') {
    headers['anthropic-version'] = '2023-06-01';
    headers['anthropic-dangerous-direct-browser-access'] = 'true';
  }
  return {body, headers};
}

function notify(control, bytes, state, body, status = 0, retryAfter = -1) {
  if (body) bytes.set(body);
  Atomics.store(control, 1, body?.length ?? 0);
  Atomics.store(control, 2, status);
  Atomics.store(control, 3, retryAfter);
  Atomics.store(control, 0, state);
  Atomics.notify(control, 0);
}

self.onmessage = async ({data}) => {
  if (data?.type === 'ready') {
    self.postMessage({type:'ready', protocol:1, available:!stopped && self.crossOriginIsolated === true});
    return;
  }
  if (data?.type === 'shutdown') {
    stopped = true;
    if (active) { active.cancelled = true; active.controller.abort(); }
    self.close();
    return;
  }
  if (data?.type === 'cancel') {
    if (active?.id === data.id) { active.cancelled = true; active.controller.abort(); }
    return;
  }
  if (data?.type !== 'request') return;
  if (!(data.buffer instanceof SharedArrayBuffer) || data.buffer.byteLength !== MAX_BYTES + CONTROL_BYTES) return;
  const control = new Int32Array(data.buffer, 0, 5);
  const bytes = new Uint8Array(data.buffer, CONTROL_BYTES);
  if (stopped) { notify(control, bytes, -5); return; }
  if (active) { notify(control, bytes, -6); return; }
  let validated;
  try { validated = validatedRequest(data); }
  catch { notify(control, bytes, -4); return; }
  const job = {id:data.id, controller:new AbortController(), timedOut:false, cancelled:false};
  active = job;
  let reader = null;
  const timeout = setTimeout(() => { job.timedOut = true; job.controller.abort(); }, data.timeoutMs);
  try {
    const response = await fetch(data.url, {
      method:'POST', headers:validated.headers, body:validated.body,
      credentials:'omit', redirect:'error', cache:'no-store', referrerPolicy:'no-referrer',
      signal:job.controller.signal,
    });
    if (response.redirected || response.type === 'opaque' || response.type === 'opaqueredirect') throw 0;
    if (response.status !== 200) {
      // Provider error bodies can contain echoed prompts, keys, or debug data.
      // Preserve the status and bounded numeric retry delay, never their text.
      if (response.body) await response.body.cancel();
      const retry = response.headers.get('retry-after');
      const retryAfter = retry !== null && /^\d{1,3}$/.test(retry) && Number(retry) <= 600 ? Number(retry) : -1;
      const body = new TextEncoder().encode(JSON.stringify({error:{message:'Provider request failed.',type:'browser_provider_error',code:'http_error'}}));
      notify(control, bytes, 1, body, response.status, retryAfter);
      return;
    }
    const contentType = response.headers.get('content-type')?.split(';',1)[0].trim().toLowerCase();
    if (contentType !== 'application/json') {
      if (response.body) await response.body.cancel();
      notify(control, bytes, -7); return;
    }
    const length = response.headers.get('content-length');
    if (length && /^\d+$/.test(length) && Number(length) > MAX_BYTES) {
      if (response.body) await response.body.cancel();
      notify(control, bytes, -3); return;
    }
    if (!response.body) { notify(control, bytes, -7); return; }
    reader = response.body.getReader();
    let count = 0;
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      if (count + value.length > MAX_BYTES) {
        await reader.cancel(); bytes.fill(0); notify(control, bytes, -3); return;
      }
      bytes.set(value, count); count += value.length;
    }
    // JSON validation is bounded and never includes raw provider text in errors.
    // TextDecoder rejects SharedArrayBuffer-backed views in browsers. Copy only
    // the bounded populated range into an ordinary ArrayBuffer before decoding.
    try { JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(bytes.slice(0,count))); }
    catch { bytes.fill(0); notify(control, bytes, -7); return; }
    Atomics.store(control, 1, count);
    Atomics.store(control, 2, response.status);
    Atomics.store(control, 3, -1);
    Atomics.store(control, 0, 1);
    Atomics.notify(control, 0);
  } catch {
    bytes.fill(0);
    notify(control, bytes, job.timedOut ? -2 : job.cancelled ? -5 : -1);
  } finally {
    clearTimeout(timeout);
    if (reader) { try { reader.releaseLock(); } catch {} }
    validated.body.fill(0);
    for (const key of Object.keys(validated.headers)) delete validated.headers[key];
    data.body = ''; data.headers = null; data.buffer = null;
    active = null;
  }
};
