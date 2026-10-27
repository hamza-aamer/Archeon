// Fetch wrapper and formatting helpers shared by the views.

export const ACTIVE = new Set(['uploading', 'queued', 'running']);
export const RETRYABLE = new Set(['failed', 'cancelled', 'interrupted']);

export const api = {
  async request(method, path, body) {
    const res = await fetch(path, { method, body });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch (_) { /* not json */ }
      const error = new Error(detail);
      error.status = res.status;
      throw error;
    }
    return res.status === 204 ? null : res.json();
  },
  get: (path) => api.request('GET', path),
  post: (path, body) => api.request('POST', path, body),
  patch: (path, body) => api.request('PATCH', path, body),
  del: (path) => api.request('DELETE', path),
};

export const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
})[c]);

export const pct = (fraction) => `${Math.round(Math.min(Math.max(fraction || 0, 0), 1) * 100)}%`;

export function compact(value) {
  if (value == null) return '–';
  const n = Number(value);
  if (n >= 1e6) return `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M`;
  if (n >= 1e4) return `${Math.round(n / 1e3)}k`;
  return n.toLocaleString();
}

export const num = (value) => (value == null ? '–' : Number(value).toLocaleString());

export function bytes(value) {
  if (value == null) return '';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let n = Number(value);
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i += 1; }
  return `${n.toFixed(n >= 100 || i === 0 ? 0 : 1)} ${units[i]}`;
}

export function duration(seconds) {
  if (seconds == null || !Number.isFinite(seconds)) return '–';
  if (seconds < 1) return '<1s';
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${String(s % 60).padStart(2, '0')}s`;
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m`;
}

export function ago(ts) {
  const diff = Date.now() / 1000 - ts;
  if (diff < 45) return 'just now';
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)} h ago`;
  if (diff < 7 * 86400) return `${Math.round(diff / 86400)} d ago`;
  return new Date(ts * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

export const now = () => Date.now() / 1000;

/** Processing time across all attempts: finished stage durations plus the stage in progress. */
export function elapsed(scene) {
  const times = Object.values(scene.stage_times || {});
  const running = scene.status === 'running' && scene.stage_started_at ? now() - scene.stage_started_at : 0;
  if (!times.length && !running) return null;
  return times.reduce((a, b) => a + b, 0) + running;
}

/**
 * Remaining-time estimates from the *measured* recent rate of progress (sliding window), not from the
 * stage's start time: some stages spend a while loading before reporting, and SuGaR resumes its iteration
 * counter from where 3DGS stopped, so progress since stage start is not linear.
 */
export function createEtaTracker({ windowSeconds = 90, minSpan = 15 } = {}) {
  let key = null;
  let samples = [];
  let smoothed = null;
  return (scene) => {
    if (scene.status !== 'running' || !scene.stage) return null;
    const k = `${scene.id}:${scene.stage}`;
    if (k !== key) {
      key = k;
      samples = [];
      smoothed = null;
    }
    const t = now();
    const p = scene.stage_progress || 0;
    if (!samples.length || p !== samples[samples.length - 1].p) samples.push({ t, p });
    samples = samples.filter((s) => t - s.t <= windowSeconds);
    if (samples.length < 3 || p >= 1) return null;
    const first = samples[0];
    const span = t - first.t;
    const progressed = p - first.p;
    if (span < minSpan || progressed <= 0.002) return null;
    const eta = ((1 - p) * span) / progressed;
    smoothed = smoothed == null ? eta : smoothed * 0.7 + eta * 0.3;
    return smoothed;
  };
}

/** Round an estimate so it does not pretend to be more precise than it is. */
export function roughDuration(seconds) {
  if (seconds < 60) return 'under a minute';
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${Math.floor(seconds / 3600)} h ${Math.round((seconds % 3600) / 60)} min`;
}

export const STATUS_TEXT = {
  uploading: 'Uploading',
  queued: 'Queued',
  running: 'Processing',
  done: 'Ready',
  failed: 'Failed',
  cancelled: 'Cancelled',
  interrupted: 'Interrupted',
};

export const statusPill = (status) => `<span class="pill status-${esc(status)}">${STATUS_TEXT[status] || esc(status)}</span>`;

export function currentStage(scene) {
  return scene.stages.find((s) => s.key === scene.stage) || null;
}

/** Smoothly animate a number shown in `el` towards `to` (format turns the number into text). */
export function tween(el, to, format = (v) => `${Math.round(v)}`, ms = 600) {
  if (!el) return;
  const from = Number(el.dataset.value ?? to);
  el.dataset.value = to;
  if (from === to || matchMedia('(prefers-reduced-motion: reduce)').matches) {
    el.textContent = format(to);
    return;
  }
  const start = performance.now();
  cancelAnimationFrame(Number(el.dataset.raf || 0));
  const step = (t) => {
    const k = Math.min((t - start) / ms, 1);
    const eased = 1 - (1 - k) ** 3;
    el.textContent = format(from + (to - from) * eased);
    if (k < 1) el.dataset.raf = requestAnimationFrame(step);
  };
  el.dataset.raf = requestAnimationFrame(step);
}
