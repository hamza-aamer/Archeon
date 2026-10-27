import {
  ACTIVE, RETRYABLE, ago, api, createEtaTracker, currentStage, duration, elapsed, esc, now, pct, roughDuration,
  statusPill,
} from '../lib/util.js';
import { STAGE_ICONS, icon } from '../lib/icons.js';
import { confirmDialog, toast } from '../lib/ui.js';

const FINAL = new Set(['done', 'failed', 'cancelled', 'interrupted']);

const etaFor = createEtaTracker();

function nowCard(scene, gpu) {
  if (!scene) {
    return `
      <div class="panel queue-idle">
        <div class="icon-badge" style="width:48px;height:48px">${icon('cpu', 22)}</div>
        <div>
          <h2>The GPU is idle</h2>
          <p class="muted" style="margin-top:4px">Nothing is processing right now. New captures start immediately.</p>
        </div>
        <span class="spacer"></span>
        <a class="button primary" href="#/new">${icon('plus', 16)} New capture</a>
      </div>`;
  }
  const stage = currentStage(scene);
  const eta = etaFor(scene);
  const index = stage ? scene.stages.indexOf(stage) : -1;
  return `
    <a class="panel queue-now" href="#/scene/${scene.id}">
      <div class="queue-now-media" style="${scene.preview ? `background-image:url('${scene.preview}')` : ''}">${scene.preview ? '' : '<div class="splat-art"><i></i><i></i><i></i></div>'}</div>
      <div class="queue-now-body">
        <div class="row" style="gap:10px">${statusPill(scene.status)}<span class="pill plain">${esc(scene.preset)}</span>
          <span class="spacer"></span><span class="faint num">${duration(elapsed(scene))} elapsed</span></div>
        <h2 style="font-size:22px;margin-top:12px">${esc(scene.name)}</h2>
        <div class="queue-stage">
          ${stage ? `<span class="icon-badge">${icon(STAGE_ICONS[stage.key], 16)}</span>
            <div><div class="eyebrow">Step ${index + 1} of ${scene.stages.length}</div><div style="font-weight:600;margin-top:4px">${esc(stage.label)}</div></div>` : '<div class="muted">Preparing…</div>'}
          <span class="spacer"></span>
          <div style="text-align:right"><div class="big-num">${pct(scene.stage_progress)}</div><div class="faint" style="font-size:12px">${eta != null ? `about ${roughDuration(eta)} left` : 'this step'}</div></div>
        </div>
        <div class="progress live" style="margin-top:14px"><span style="width:${pct(scene.stage_progress)}"></span></div>
        <div class="row" style="margin-top:14px;font-size:12.5px;color:var(--text-3)">
          <span>Overall <b style="color:var(--text)" class="num">${pct(scene.progress)}</b></span>
          ${gpu ? `<span>· GPU <b style="color:var(--text)" class="num">${Math.round(gpu.utilization ?? 0)}%</b></span>
          <span>· VRAM <b style="color:var(--text)" class="num">${((gpu.memory_used_mb || 0) / 1024).toFixed(1)} / ${((gpu.memory_total_mb || 0) / 1024).toFixed(1)} GB</b></span>` : ''}
          <span class="spacer"></span><span class="open-link">Open ${icon('chevron', 14)}</span>
        </div>
      </div>
    </a>`;
}

function averages(scenes) {
  const groups = {};
  scenes.filter((s) => s.status === 'done' && elapsed(s)).forEach((s) => {
    (groups[s.preset] ||= []).push(elapsed(s));
  });
  return Object.entries(groups).map(([preset, times]) => ({
    preset, count: times.length, mean: times.reduce((a, b) => a + b, 0) / times.length,
  }));
}

export async function renderQueue(root, ctx) {
  root.innerHTML = `
    <div class="page-head">
      <div>
        <div class="eyebrow">Queue</div>
        <h1 style="margin-top:8px">Processing queue</h1>
        <p class="lede">One scene trains at a time, so it gets the whole GPU. Everything else waits here in order of upload.</p>
      </div>
      <div class="summary" id="averages"></div>
    </div>
    <div class="stack">
      <section id="now"></section>
      <section class="panel" id="next"></section>
      <section class="panel" id="history"></section>
    </div>`;

  let scenes = [];
  let lastSignature = '';
  const render = (force = false) => {
    // Only touch the DOM when something visible changed, so animations and hover states are not reset.
    const gpu = ctx.system.latest?.gpu;
    const signature = JSON.stringify([scenes.map((s) => [s.id, s.status, s.stage, s.progress, s.stage_progress, s.name, s.preview]),
      gpu && [Math.round(gpu.utilization || 0), Math.round(gpu.memory_used_mb || 0)], Math.floor(Date.now() / 5000)]);
    if (!force && signature === lastSignature) return;
    lastSignature = signature;
    const running = scenes.find((s) => s.status === 'running' || s.status === 'uploading');
    const queued = scenes.filter((s) => s.status === 'queued').sort((a, b) => a.created_at - b.created_at);
    const history = scenes.filter((s) => FINAL.has(s.status) && s.preset !== 'imported')
      .sort((a, b) => (b.finished_at || b.created_at) - (a.finished_at || a.created_at)).slice(0, 20);

    root.querySelector('#now').innerHTML = nowCard(running, ctx.system.latest?.gpu);

    root.querySelector('#next').innerHTML = `
      <div class="panel-head"><h2>${icon('hourglass', 17)} Up next</h2><span class="faint num">${queued.length} waiting</span></div>
      ${queued.length ? `<ol class="queue-list">${queued.map((s, i) => `
        <li>
          <span class="position">${i + 1}</span>
          <a href="#/scene/${s.id}" class="queue-name">${esc(s.name)}</a>
          <span class="pill plain">${esc(s.preset)}</span>
          <span class="faint">waiting ${duration(now() - s.created_at)}</span>
          <button class="button small ghost" data-cancel="${s.id}" data-name="${esc(s.name)}">${icon('x', 14)} Remove</button>
        </li>`).join('')}</ol>`
        : `<div class="panel-body faint">Nothing waiting. Uploads join the end of this list.</div>`}`;

    root.querySelector('#history').innerHTML = `
      <div class="panel-head"><h2>${icon('clock', 17)} Recent runs</h2></div>
      ${history.length ? `<div class="table-wrap"><table class="table">
        <thead><tr><th>Scene</th><th>Result</th><th>Preset</th><th class="r">Duration</th><th class="r">Finished</th><th></th></tr></thead>
        <tbody>${history.map((s) => `
          <tr>
            <td><a href="#/scene/${s.id}" class="queue-name">${esc(s.name)}</a>${s.error ? `<div class="faint table-sub">${esc(s.error)}</div>` : ''}</td>
            <td>${statusPill(s.status)}</td>
            <td class="muted">${esc(s.preset)}</td>
            <td class="r num">${duration(elapsed(s))}</td>
            <td class="r faint">${s.finished_at ? ago(s.finished_at) : '–'}</td>
            <td class="r">${RETRYABLE.has(s.status) ? `<button class="button small" data-retry="${s.id}">${icon('refresh', 13)} Resume</button>` : `<a class="button small ghost" href="#/scene/${s.id}">Open</a>`}</td>
          </tr>`).join('')}</tbody></table></div>`
        : `<div class="panel-body faint">Finished and failed runs will show up here.</div>`}`;

    const avg = averages(scenes);
    root.querySelector('#averages').innerHTML = avg.length
      ? avg.map((a) => `<div class="stat"><div class="value">${duration(a.mean)}</div><div class="eyebrow">avg ${esc(a.preset)} · ${a.count} run${a.count > 1 ? 's' : ''}</div></div>`).join('')
      : '';
  };

  const onClick = async (e) => {
    const cancel = e.target.closest('[data-cancel]');
    const retry = e.target.closest('[data-retry]');
    try {
      if (cancel) {
        const ok = await confirmDialog({ title: 'Remove from queue?', body: `“${cancel.dataset.name}” will be cancelled before it starts. You can resume it later from its page.`, confirm: 'Remove', danger: true });
        if (!ok) return;
        await api.post(`/api/scenes/${cancel.dataset.cancel}/cancel`);
        toast('Removed from the queue');
      } else if (retry) {
        await api.post(`/api/scenes/${retry.dataset.retry}/retry`);
        toast('Queued to resume', 'success');
      } else {
        return;
      }
      scenes = await api.get('/api/scenes');
      render(true);
    } catch (err) {
      toast(err.message, 'error');
    }
  };
  root.addEventListener('click', onClick);
  ctx.onLeave(() => root.removeEventListener('click', onClick));

  scenes = await api.get('/api/scenes');
  render();
  ctx.every(2000, async () => {
    try {
      scenes = await api.get('/api/scenes');
      render();
    } catch (_) { /* transient */ }
  });
  // keep the running card's GPU numbers in step with the top bar
  ctx.onSystem(() => { if (scenes.some((s) => ACTIVE.has(s.status))) render(); });
}
