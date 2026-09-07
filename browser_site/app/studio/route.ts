import { studioSecurityHeaders } from '@/lib/security-headers';
const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Reliability Studio</title><link rel="stylesheet" href="/assets/studio/stlite/style.css">
<style>
body{margin:0;background:#fbfcff;color:#17212f;font-family:Arial,Helvetica,sans-serif}.boot{max-width:640px;margin:10vh auto;padding:32px}.brand{font-size:15px;font-weight:700;color:#2563eb;margin-bottom:48px}.boot h1{font-size:32px;letter-spacing:-.8px;line-height:1.2;margin:0 0 18px}.boot p{font-size:16px;line-height:1.6;color:#46515f}.boot .step{font-size:14px;color:#2563eb;margin-top:28px}.boot progress{width:100%;height:5px;accent-color:#2563eb}.boot button{background:#2563eb;color:white;border:0;border-radius:8px;padding:12px 20px;font:inherit;cursor:pointer}.boot button:focus-visible{outline:3px solid #17212f;outline-offset:3px}.boot small{display:block;font-size:13px;line-height:1.6;color:#687385;margin-top:28px}#root[hidden]{display:none}
</style></head><body>
<section class="boot" id="boot" aria-labelledby="boot-title"><div class="brand">AI Reliability Studio</div>
<h1 id="boot-title">Opening your private workspace</h1><p>Review AI answers against your sources, record decisions, and check whether a fix helped.</p>
<p id="boot-status" class="step" role="status" aria-live="polite">Loading the tools into this tab…</p><progress id="boot-progress" aria-label="Opening workspace"></progress>
<small>Your browser runs the workspace. The first load can take a little while. Save an export before closing or reloading the tab.</small>
<button id="boot-retry" hidden>Try again</button><noscript><p>Enable JavaScript to open the workspace.</p></noscript></section>
<div id="root" hidden></div><script type="module" src="/assets/studio/boot.js"></script></body></html>`;
export function GET() {
  return new Response(html, { headers: {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-cache',
    ...studioSecurityHeaders,
  }});
}
