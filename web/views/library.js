import { ACTIVE, RETRYABLE, ago, api, compact, currentStage, duration, elapsed, esc, pct, statusPill, tween } from '../lib/util.js';
import { icon } from '../lib/icons.js';

const FILTERS = [
  ['all', 'All', () => true],
  ['active', 'Processing', (s) => ACTIVE.has(s.status)],
  ['done', 'Ready', (s) => s.status === 'done'],
  ['failed', 'Needs attention', (s) => RETRYABLE.has(s.status)],
];

const splatArt = '<div class="splat-art"><i></i><i></i><i></i></div>';

function card(scene, index = 0) {
  const media = scene.preview
    ? `<div class="card-media" style="background-image:url('${scene.preview}')">`
    : `<div class="card-media">${splatArt}`;
  const stage = currentStage(scene);
  const overlay = ACTIVE.has(scene.status)
    ? `<div class="overlay">
         <div class="stage"><span>${esc(stage ? stage.label : scene.status === 'queued' ? 'Waiting for the GPU' : 'Uploading')}</span><span class="num">${pct(scene.progress)}</span></div>
         <div class="progress thin live"><span style="width:${pct(scene.progress)}"></span></div>
       </div>`
    : '';
  const s = scene.stats || {};
  const metrics = [
    s.gaussians_3dgs && [icon('sparkles', 13), `${compact(s.gaussians_3dgs)} splats`],
    s.mesh_faces && [icon('box', 13), `${compact(s.mesh_faces)} faces`],
    s.registered_images && [icon('aperture', 13), `${s.registered_images} views`],
  ].filter(Boolean);
  const time = elapsed(scene);
  return `
    <a class="card" href="#/scene/${scene.id}" style="--i:${index}">
      ${media}
        <div class="tags">${statusPill(scene.status)}<span class="pill plain">${esc(scene.preset)}</span></div>
        ${overlay}
      </div>
      <div class="card-body">
        <div class="card-title" title="${esc(scene.name)}">${esc(scene.name)}</div>
        <div class="card-meta"><span>${ago(scene.created_at)}</span>${time ? `<span class="sep"></span><span>${duration(time)}</span>` : ''}</div>
        ${metrics.length ? `<div class="metrics">${metrics.map(([i, t]) => `<span class="metric">${i}${t}</span>`).join('')}</div>` : ''}
        ${RETRYABLE.has(scene.status) && scene.error ? `<div class="faint" style="font-size:12.5px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">${esc(scene.error)}</div>` : ''}
      </div>
    </a>`;
}

function emptyState() {
  return `
    <div class="panel empty-state">
      <div class="orb">${splatArt}</div>
      <h2>Your library is empty</h2>
      <p>Record a slow walk around a room or an object, upload it, and Archeon reconstructs it as a photoreal Gaussian splat and a textured mesh.</p>
      <a class="button primary large" href="#/new">${icon('plus', 18)} New capture</a>
      <div class="how">
        <div class="how-step"><div class="icon-badge">${icon('video', 18)}</div><h3>1 · Capture</h3><p>30 seconds to 2 minutes of steady video, moving around the subject.</p></div>
        <div class="how-step"><div class="icon-badge">${icon('aperture', 18)}</div><h3>2 · Reconstruct</h3><p>COLMAP finds the camera path, 3DGS trains the splat, SuGaR extracts a mesh.</p></div>
        <div class="how-step"><div class="icon-badge">${icon('orbit', 18)}</div><h3>3 · Explore</h3><p>Fly through it in the browser, step in with a VR headset, or download the files.</p></div>
      </div>
    </div>`;
}

export async function renderLibrary(root, ctx) {
  let filter = 'all';
  let query = '';
  let firstPaint = true;
  let scenes = await api.get('/api/scenes');

  root.innerHTML = `
    <div class="page-head">
      <div>
        <div class="eyebrow">Library</div>
        <h1 style="margin-top:8px">Captured spaces</h1>
        <p class="lede">Every walkthrough you have turned into 3D. Open one to explore it, or start a new capture.</p>
      </div>
      <div class="summary" id="summary"></div>
    </div>
    <div class="toolbar" id="toolbar"></div>
    <div id="list"></div>`;

  const summary = root.querySelector('#summary');
  const toolbar = root.querySelector('#toolbar');
  const list = root.querySelector('#list');

  const renderSummary = () => {
    const ready = scenes.filter((s) => s.status === 'done').length;
    const active = scenes.filter((s) => ACTIVE.has(s.status)).length;
    const hours = scenes.reduce((sum, s) => sum + (s.status === 'done' ? elapsed(s) || 0 : 0), 0);
    if (!summary.childElementCount) {
      summary.innerHTML = ['Ready', 'Processing', 'GPU time'].map((label) => `
        <div class="stat"><div class="value num" data-value="0">0</div><div class="eyebrow">${label}</div></div>`).join('');
    }
    const values = summary.querySelectorAll('.value');
    tween(values[0], ready);
    tween(values[1], active);
    tween(values[2], hours, (v) => duration(v), 900);
  };

  const renderToolbar = () => {
    toolbar.innerHTML = `
      <div class="segmented" role="tablist">
        ${FILTERS.map(([key, label, test]) => `<button role="tab" data-filter="${key}" class="${key === filter ? 'active' : ''}">${label}<span class="count">${scenes.filter(test).length}</span></button>`).join('')}
      </div>
      <span class="spacer"></span>
      <label class="search">${icon('search', 15)}<input type="search" placeholder="Search scenes" value="${esc(query)}" aria-label="Search scenes"></label>
      <a class="button primary" href="#/new">${icon('plus', 16)} New capture</a>`;
    toolbar.querySelector('input').addEventListener('input', (e) => { query = e.target.value; renderList(); });
  };
  toolbar.addEventListener('click', (e) => {
    const key = e.target.closest('[data-filter]')?.dataset.filter;
    if (!key) return;
    filter = key;
    toolbar.querySelectorAll('[data-filter]').forEach((b) => b.classList.toggle('active', b.dataset.filter === key));
    renderList();
  });

  const renderList = () => {
    if (!scenes.length) {
      toolbar.classList.add('hidden');
      list.innerHTML = emptyState();
      return;
    }
    toolbar.classList.remove('hidden');
    const test = FILTERS.find(([key]) => key === filter)[2];
    const q = query.trim().toLowerCase();
    const shown = scenes.filter((s) => test(s) && (!q || s.name.toLowerCase().includes(q)));
    list.className = shown.length ? `grid${firstPaint ? ' stagger' : ''}` : '';
    firstPaint = false;
    list.innerHTML = shown.length
      ? shown.map((scene, i) => card(scene, i)).join('')
      : `<div class="panel empty-state" style="padding:48px"><h2>No matching scenes</h2><p>Try a different filter or search.</p></div>`;
  };

  renderSummary();
  renderToolbar();
  renderList();

  ctx.every(3000, async () => {
    try {
      const next = await api.get('/api/scenes');
      const changed = JSON.stringify(next.map((s) => [s.id, s.status, s.progress, s.stage, s.preview, s.name]))
        !== JSON.stringify(scenes.map((s) => [s.id, s.status, s.progress, s.stage, s.preview, s.name]));
      scenes = next;
      if (changed) {
        renderSummary();
        toolbar.querySelectorAll('[data-filter]').forEach((b) => {
          const [, , t] = FILTERS.find(([key]) => key === b.dataset.filter);
          b.querySelector('.count').textContent = scenes.filter(t).length;
        });
        renderList();
      }
    } catch (_) { /* transient */ }
  });
}
