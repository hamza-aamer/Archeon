import { api, esc } from './lib/util.js';
import { icon } from './lib/icons.js';
import { renderLibrary } from './views/library.js';
import { renderCapture } from './views/capture.js';
import { renderScene } from './views/scene.js';
import { renderQueue } from './views/queue.js';
import { renderSystem } from './views/system.js';
import { renderGuide } from './views/guide.js';

const app = document.getElementById('app');
// Rolling GPU telemetry shared by every view: [{t, util, mem, temp}], newest last.
const system = { latest: null, history: [], listeners: new Set() };
let cleanups = [];

const ROUTES = {
  library: renderLibrary,
  new: renderCapture,
  queue: renderQueue,
  system: renderSystem,
  guide: renderGuide,
};

// Lifecycle helpers handed to each view; everything registered here is torn down on navigation.
function viewContext() {
  return {
    every(ms, fn) {
      const id = setInterval(fn, ms);
      cleanups.push(() => clearInterval(id));
    },
    onLeave(fn) { cleanups.push(fn); },
    onSystem(fn) {
      system.listeners.add(fn);
      cleanups.push(() => system.listeners.delete(fn));
      if (system.latest) fn(system.latest, system.history);
    },
    system,
  };
}

const nav = document.getElementById('nav');
const indicator = document.createElement('span');
indicator.className = 'nav-indicator';
nav.prepend(indicator);

function moveIndicator() {
  const active = nav.querySelector('a.active');
  if (!active) {
    indicator.style.opacity = '0';
    return;
  }
  indicator.style.opacity = '1';
  indicator.style.width = `${active.offsetWidth}px`;
  indicator.style.transform = `translateX(${active.offsetLeft}px)`;
}
window.addEventListener('resize', moveIndicator);

async function route() {
  // Crossfade between pages where the browser supports view transitions.
  if (document.startViewTransition && !matchMedia('(prefers-reduced-motion: reduce)').matches && app.childElementCount) {
    const transition = document.startViewTransition(() => renderRoute());
    await transition.updateCallbackDone.catch(() => {});
  } else {
    await renderRoute();
  }
}

async function renderRoute() {
  for (const fn of cleanups.splice(0)) {
    try { await fn(); } catch (_) { /* best effort */ }
  }
  const hash = location.hash || '#/';
  const scene = hash.match(/^#\/scene\/([0-9a-f]{12})$/);
  const name = scene ? 'scene' : (hash.match(/^#\/(new|queue|system|guide)$/) || [])[1] || 'library';
  document.querySelectorAll('[data-route]').forEach((a) => a.classList.toggle('active', a.dataset.route === name));
  moveIndicator();
  app.innerHTML = '';
  window.scrollTo(0, 0);
  try {
    if (scene) await renderScene(app, viewContext(), scene[1]);
    else await ROUTES[name](app, viewContext());
  } catch (err) {
    app.innerHTML = `
      <div class="panel empty-state">
        <div class="icon-badge" style="width:48px;height:48px;color:var(--danger);background:var(--danger-soft)">${icon('alert', 22)}</div>
        <h2 style="margin-top:18px">${err.status === 404 ? 'Scene not found' : 'Something went wrong'}</h2>
        <p>${esc(err.message)}</p>
        <a class="button" href="#/">${icon('back', 16)} Back to library</a>
      </div>`;
  }
}

// ---------- top bar ----------
const NAV_ICONS = { library: 'grid', queue: 'hourglass', system: 'cpu', guide: 'info' };
Object.entries(NAV_ICONS).forEach(([key, name]) => {
  document.querySelector(`#nav [data-route="${key}"]`).insertAdjacentHTML('afterbegin', icon(name, 16));
});
document.getElementById('new-capture').innerHTML = `${icon('plus', 15)}<span>New capture</span>`;

const shortGpu = (name) => name.replace(/^NVIDIA\s+/, '').replace(/^GeForce\s+/, '').replace(/\s+GPU$/, '');

async function pollSystem() {
  try {
    const data = await api.get('/api/system');
    system.latest = data;
    if (data.gpu) {
      system.history.push({
        t: Date.now(),
        util: data.gpu.utilization || 0,
        mem: data.gpu.memory_used_mb || 0,
        temp: data.gpu.temperature_c || 0,
      });
      if (system.history.length > 144) system.history.shift(); // 6 minutes at 2.5 s
    }

    const badge = document.getElementById('queue-badge');
    const active = data.queue.running + data.queue.queued;
    badge.hidden = !active;
    badge.textContent = active;
    badge.classList.toggle('busy', !!data.queue.running);

    const gpu = document.getElementById('gpu-chip');
    if (data.gpu) {
      const g = data.gpu;
      gpu.querySelector('.text').textContent = `${shortGpu(g.name)} · ${Math.round(g.utilization ?? 0)}%`;
      gpu.querySelector('.meter span').style.width = `${g.utilization ?? 0}%`;
      gpu.title = `${g.name}\nVRAM ${(g.memory_used_mb / 1024).toFixed(1)} / ${(g.memory_total_mb / 1024).toFixed(1)} GB · ${g.temperature_c ?? '–'}°C · ${g.power_w ?? '–'} W`;
    } else {
      gpu.querySelector('.text').textContent = 'No GPU';
    }
    system.listeners.forEach((fn) => fn(data, system.history));
  } catch (_) {
    document.querySelector('#health .text').textContent = 'Server offline';
    document.querySelector('#health .dot').className = 'dot bad';
  }
}

async function pollHealth() {
  const health = document.getElementById('health');
  try {
    const { checks } = await api.get('/api/health');
    const failed = checks.filter((c) => !c.ok);
    health.querySelector('.dot').className = `dot ${failed.length ? 'bad' : 'ok'}`;
    health.querySelector('.text').textContent = failed.length ? `${failed.length} issue${failed.length > 1 ? 's' : ''}` : 'Ready';
    health.title = failed.length ? failed.map((c) => `${c.name}: ${c.detail}`).join('\n') : 'All quick checks passed';
  } catch (_) {
    health.querySelector('.dot').className = 'dot bad';
    health.querySelector('.text').textContent = 'Server offline';
  }
}

window.addEventListener('hashchange', route);
pollSystem();
pollHealth();
setInterval(pollSystem, 2500);
setInterval(pollHealth, 30000);
route();
