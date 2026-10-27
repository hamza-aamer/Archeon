import {
  ACTIVE, RETRYABLE, ago, api, bytes, compact, currentStage, duration, elapsed, esc, now, num, pct,
  createEtaTracker, roughDuration, statusPill, tween,
} from '../lib/util.js';
import { STAGE_ICONS, icon } from '../lib/icons.js';
import { confirmDialog, promptDialog, sparkline, toast } from '../lib/ui.js';
import { mountMesh, mountSplat } from '../viewer.js';
import { mountCameras } from '../cameras.js';

const DOWNLOADS = [
  ['scene_ply', 'sparkles', 'Gaussian splat', '.ply · standard 3DGS: Unity VR viewer, SuperSplat'],
  ['scene_splat', 'sparkles', 'Web splat', '.splat · compact, base colour only'],
  ['sugar_ply', 'layers', 'SuGaR splat', '.ply · Gaussians bound to the mesh'],
  ['mesh_glb', 'box', 'Textured mesh', '.glb · single file, texture embedded'],
  ['mesh_zip', 'box', 'Mesh + texture', '.obj · .mtl · .png in a zip'],
  ['manifest', 'file', 'Manifest', '.json · stats, timings, camera'],
];

const VIEW_TABS = [
  ['scene_splat', 'sparkles', 'Splat'],
  ['sugar_splat', 'layers', 'SuGaR splat'],
  ['mesh_glb', 'box', 'Mesh'],
  ['cameras', 'aperture', 'Cameras'],
];

function stageColor(index, total) {
  const stops = [[139, 92, 246], [109, 124, 247], [34, 211, 238]];
  const t = total > 1 ? index / (total - 1) : 0;
  const seg = t < 0.5 ? 0 : 1;
  const local = t < 0.5 ? t / 0.5 : (t - 0.5) / 0.5;
  const c = stops[seg].map((v, i) => Math.round(v + (stops[seg + 1][i] - v) * local));
  return `rgb(${c.join(',')})`;
}

function logLineClass(line) {
  if (/^\[archeon\] =====/.test(line)) return 'l-stage';
  if (/^\[archeon\] \$ /.test(line)) return 'l-cmd';
  if (/FAILED|Traceback|Error|error:|out of memory|exception/i.test(line)) return 'l-err';
  if (/warn/i.test(line)) return 'l-warn';
  if (/^\[archeon\] .*(done in|kept the sharpest|using \d)/.test(line)) return 'l-ok';
  if (/^I\d{8} /.test(line)) return 'l-dim';
  return '';
}

function errorHints(scene) {
  const text = `${scene.error || ''}`.toLowerCase();
  if (text.includes('memory')) {
    return ['Use the Preview preset, which skips SuGaR.', 'Trim the clip, or record at 1080p instead of 4K.', 'Close other apps using the GPU, then resume.'];
  }
  if (text.includes('colmap') || text.includes('placed') || text.includes('reconstruct')) {
    return ['Walk around the subject instead of turning on the spot.', 'Move slowly so consecutive frames overlap heavily.', 'Avoid glossy floors, glass and blank walls; add texture to the view.'];
  }
  if (text.includes('short')) return ['Record at least 20–30 seconds of footage.'];
  return [];
}

export async function renderScene(root, ctx, id) {
  let scene = await api.get(`/api/scenes/${id}`);
  let mode = null;
  let logOffset = 0;
  let activity = '';
  let framesLoaded = false;
  let camerasMounted = false;
  let disposeMini = null;
  const etaFor = createEtaTracker();

  root.innerHTML = `
    <a class="back" href="#/">${icon('back', 14)} Library</a>
    <div class="scene-head" id="head"></div>
    <div id="body"></div>`;
  const head = root.querySelector('#head');
  const body = root.querySelector('#body');
  ctx.onLeave(async () => { if (disposeMini) await disposeMini(); });

  // ---------------------------------------------------------------- header
  const renderHead = () => {
    const total = elapsed(scene);
    head.innerHTML = `
      <div>
        <div class="scene-title">
          <h1>${esc(scene.name)}</h1>
          <button class="edit" data-act="rename" title="Rename" aria-label="Rename">${icon('pencil', 16)}</button>
        </div>
        <div class="scene-meta">
          ${statusPill(scene.status)}
          <span>${icon('layers', 14)}${scene.preset === 'imported' ? 'Imported' : `${esc(scene.preset)} preset`}</span><span class="sep"></span>
          <span>${icon('clock', 14)}${ago(scene.created_at)}</span>
          ${total ? `<span class="sep"></span><span>${icon('hourglass', 14)}<span id="elapsed" class="num">${duration(total)}</span></span>` : ''}
          ${scene.source_filename ? `<span class="sep"></span><span>${icon('file', 14)}${esc(scene.source_filename)}</span>` : ''}
        </div>
      </div>
      <div class="row">
        ${ACTIVE.has(scene.status) ? `<button class="button danger" data-act="cancel">${icon('x', 15)} Cancel</button>` : ''}
        ${RETRYABLE.has(scene.status) ? `<button class="button primary" data-act="retry">${icon('refresh', 15)} Resume</button>` : ''}
        <button class="button ghost icon-only" data-act="delete" title="Delete scene" aria-label="Delete scene">${icon('trash', 16)}</button>
      </div>`;
  };

  const onAction = async (e) => {
    const act = e.target.closest('[data-act]')?.dataset.act;
    if (!act) return;
    try {
      if (act === 'rename') {
        const name = await promptDialog({ title: 'Rename scene', label: 'Name', value: scene.name });
        if (!name) return;
        const form = new FormData();
        form.append('name', name);
        scene = await api.patch(`/api/scenes/${id}`, form);
        toast('Renamed', 'success');
      } else if (act === 'cancel') {
        const ok = await confirmDialog({
          title: 'Cancel processing?',
          body: 'The current stage stops immediately. Finished stages are kept, so you can resume later.',
          confirm: 'Cancel processing', danger: true,
        });
        if (!ok) return;
        scene = await api.post(`/api/scenes/${id}/cancel`);
        toast('Processing cancelled');
      } else if (act === 'retry') {
        scene = await api.post(`/api/scenes/${id}/retry`);
        toast('Resuming from the last unfinished stage', 'success');
      } else if (act === 'delete') {
        const ok = await confirmDialog({
          title: `Delete “${scene.name}”?`,
          body: 'The video, intermediate data and every exported file for this scene are removed from disk.',
          confirm: 'Delete scene', danger: true,
        });
        if (!ok) return;
        await api.del(`/api/scenes/${id}`);
        toast('Scene deleted', 'success');
        location.hash = '#/';
        return;
      }
      update();
    } catch (err) {
      toast(err.message, 'error');
    }
  };
  root.addEventListener('click', onAction);
  ctx.onLeave(() => root.removeEventListener('click', onAction));

  // ---------------------------------------------------------------- processing view
  const stepState = (s, index) => {
    const keys = scene.stages.map((st) => st.key);
    const currentIndex = keys.indexOf(scene.stage);
    const done = scene.status === 'done' || s.key in scene.stage_times || (currentIndex >= 0 && index < currentIndex);
    if (done) return 'done';
    if (s.key !== scene.stage) return 'pending';
    if (RETRYABLE.has(scene.status)) return 'failed';
    return scene.status === 'running' ? 'current' : 'current paused';
  };

  const stepTime = (s, state) => {
    if (scene.stage_times[s.key] != null) return duration(scene.stage_times[s.key]);
    if (state === 'current' && scene.stage_started_at) return duration(now() - scene.stage_started_at);
    return '';
  };

  const renderPipeline = () => {
    const el = body.querySelector('#pipeline');
    if (!el) return;
    const fresh = el.childElementCount !== scene.stages.length;
    if (fresh) {
      // Build once, then update classes in place so the connector fill and node transitions animate.
      el.innerHTML = scene.stages.map((s, i) => `
        <div class="step pending" data-step="${s.key}" style="--i:${i}">
          <div class="node"></div>
          <div class="label">${esc(s.label)}</div>
          <div class="time num"></div>
        </div>`).join('');
      el.classList.add('intro');
      setTimeout(() => el.classList.remove('intro'), 2500);
    }
    const apply = () => scene.stages.forEach((s, i) => {
      const step = el.children[i];
      const state = stepState(s, i);
      if (step.dataset.state !== state) {
        step.dataset.state = state;
        step.className = `step ${state}`;
        step.querySelector('.node').innerHTML = `${icon(state === 'failed' ? 'alert' : STAGE_ICONS[s.key] || 'sparkles', 18)}${state === 'done' ? `<span class="tick">${icon('check', 10)}</span>` : ''}`;
      }
      step.querySelector('.time').textContent = stepTime(s, state);
    });
    if (fresh) requestAnimationFrame(() => requestAnimationFrame(apply));
    else apply();
  };

  const renderMainCard = () => {
    const el = body.querySelector('#main-card');
    if (!el) return;
    const stage = currentStage(scene);
    if (RETRYABLE.has(scene.status)) {
      const hints = errorHints(scene);
      const title = scene.status === 'cancelled' ? 'Processing was cancelled'
        : scene.status === 'interrupted' ? 'Processing was interrupted' : `Failed while ${stage ? stage.label.toLowerCase() : 'processing'}`;
      el.innerHTML = `
        <div class="panel error-card">
          <div class="head">
            <div class="icon-badge">${icon(scene.status === 'cancelled' ? 'pause' : 'alert', 18)}</div>
            <div>
              <h2>${esc(title)}</h2>
              ${scene.error ? `<p>${esc(scene.error)}</p>` : '<p>Finished stages are kept. Resume to continue where it stopped.</p>'}
              ${hints.length ? `<ul class="faint" style="margin:12px 0 0;padding-left:18px;font-size:13px">${hints.map((h) => `<li>${esc(h)}</li>`).join('')}</ul>` : ''}
              <div class="row actions">
                <button class="button primary" data-act="retry">${icon('refresh', 15)} Resume${stage ? ` from “${esc(stage.label)}”` : ''}</button>
              </div>
            </div>
          </div>
        </div>`;
      return;
    }
    if (scene.status === 'queued' || scene.status === 'uploading' || !stage) {
      const busy = ctx.system.latest?.queue?.running;
      el.innerHTML = `
        <div class="panel queued-card">
          <div class="icon-badge" style="width:44px;height:44px">${icon('hourglass', 20)}</div>
          <div>
            <h2>${scene.status === 'uploading' ? 'Receiving upload' : 'Waiting for the GPU'}</h2>
            <p class="muted" style="margin-top:4px">${busy ? 'Another scene is processing. This one starts automatically when it finishes.' : 'Starting shortly…'}</p>
          </div>
        </div>`;
      return;
    }
    if (!el.querySelector('.now-card') || el.dataset.stage !== stage.key) {
      el.dataset.stage = stage.key;
      el.innerHTML = `
        <div class="panel now-card">
          <div class="head">
            <div class="icon-badge">${icon(STAGE_ICONS[stage.key] || 'sparkles', 20)}</div>
            <div>
              <div class="eyebrow">Step ${scene.stages.indexOf(stage) + 1} of ${scene.stages.length}</div>
              <h2 style="margin-top:6px">${esc(stage.label)}</h2>
              <p class="desc">${esc(stage.description)}</p>
            </div>
            <div class="big" id="stage-pct">0%</div>
          </div>
          <div class="progress live"><span id="stage-bar" style="width:0"></span></div>
          <div class="facts">
            <span>Elapsed <b id="stage-elapsed">–</b></span>
            <span>Remaining <b id="stage-eta">estimating…</b></span>
          </div>
          <div class="activity" id="activity">${esc(activity || 'Starting…')}</div>
        </div>`;
    }
    tickStage();
  };

  const tickStage = () => {
    const pctEl = body.querySelector('#stage-pct');
    const asPct = (v) => `${Math.round(v)}%`;
    if (pctEl) {
      tween(pctEl, Math.round((scene.stage_progress || 0) * 100), asPct);
      body.querySelector('#stage-bar').style.width = pct(scene.stage_progress);
      body.querySelector('#stage-elapsed').textContent = scene.stage_started_at ? duration(now() - scene.stage_started_at) : '–';
      const eta = etaFor(scene);
      body.querySelector('#stage-eta').textContent = eta != null ? `about ${roughDuration(eta)}`
        : scene.stage_progress > 0 ? 'calculating…' : 'not reported for this step';
    }
    const overall = body.querySelector('#overall');
    if (overall) {
      tween(overall.querySelector('.value'), Math.round((scene.progress || 0) * 100), asPct);
      overall.querySelector('.progress span').style.width = pct(scene.progress);
    }
    const el = head.querySelector('#elapsed');
    if (el) el.textContent = duration(elapsed(scene));
    body.querySelectorAll('.step.current .time').forEach((t) => {
      if (scene.stage_started_at) t.textContent = duration(now() - scene.stage_started_at);
    });
  };

  const renderCapturePanel = () => {
    const el = body.querySelector('#capture-panel');
    if (!el) return;
    const s = scene.stats || {};
    const rows = [
      ['Video', s.video_duration != null ? `${duration(s.video_duration)} · ${s.video_width}×${s.video_height}` : null],
      ['Frames kept', s.frames_selected != null ? `${num(s.frames_selected)} of ${num(s.frames_decoded)}` : null],
      ['Views placed', s.registered_images != null ? `${num(s.registered_images)} of ${num(s.frames_selected)}` : null],
      ['Sparse points', s.sparse_points != null ? num(s.sparse_points) : null],
      ['Gaussians', s.gaussians_3dgs != null ? num(s.gaussians_3dgs) : null],
    ].filter(([, v]) => v != null);
    el.innerHTML = rows.length
      ? `<div class="panel-head"><h2>${icon('info', 17)} Capture</h2></div>
         <div class="panel-body"><dl class="kv">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl></div>`
      : '';
    el.classList.toggle('hidden', !rows.length);
  };

  const loadFrames = async (container) => {
    if (framesLoaded || !('frames' in scene.stage_times)) return;
    framesLoaded = true;
    try {
      const { frames } = await api.get(`/api/scenes/${id}/frames`);
      if (!frames.length) return;
      container.classList.remove('hidden');
      container.innerHTML = `
        <div class="panel-head"><h2>${icon('film', 17)} Selected frames</h2><span class="faint num">${frames.length} frames</span></div>
        <div class="panel-body" style="padding-bottom:12px">
          <div class="frames">${frames.map((f, i) => `
            <a href="${f.full}" target="_blank" rel="noopener" title="${esc(f.name)}"><img src="${f.thumb}" loading="lazy" alt=""><span class="index">${i + 1}</span></a>`).join('')}
          </div>
        </div>`;
    } catch (_) { framesLoaded = false; }
  };

  const loadCameras = async () => {
    const panel = body.querySelector('#camera-panel');
    if (!panel || camerasMounted || !('colmap' in scene.stage_times)) return;
    camerasMounted = true;
    try {
      const data = await api.get(`/api/scenes/${id}/reconstruction`);
      panel.classList.remove('hidden');
      panel.innerHTML = `
        <div class="panel-head"><h2>${icon('aperture', 17)} Camera path</h2><span class="faint num">${data.cameras.length} views</span></div>
        <div class="panel-body"><div class="mini-viewport" id="mini"></div>
          <p class="faint" style="font-size:12px;margin-top:10px">COLMAP's sparse point cloud, with a frustum for every recovered camera position. Drag to orbit.</p></div>`;
      disposeMini = mountCameras(panel.querySelector('#mini'), data, { autoRotate: true });
    } catch (_) { camerasMounted = false; }
  };

  const renderGpu = (data, history) => {
    const el = body.querySelector('#gpu-card');
    if (!el) return;
    const g = data.gpu;
    if (!g) {
      el.innerHTML = `<div class="panel-body faint">GPU statistics are unavailable (nvidia-smi not found).</div>`;
      return;
    }
    const usedGb = (g.memory_used_mb || 0) / 1024;
    const totalGb = (g.memory_total_mb || 1) / 1024;
    el.innerHTML = `
      <div class="panel-head"><h2>${icon('cpu', 17)} GPU</h2><span class="faint" style="font-size:12px">${esc(g.name.replace(/^NVIDIA\s+/, ''))}</span></div>
      <div class="panel-body">
        <div class="gauges">
          <div class="gauge"><div class="eyebrow">Utilisation</div><div class="value">${Math.round(g.utilization ?? 0)}<small>%</small></div></div>
          <div class="gauge"><div class="eyebrow">Temperature</div><div class="value">${g.temperature_c ?? '–'}<small>°C</small></div></div>
        </div>
        ${sparkline(history.map((h) => h.util), { height: 48 })}
        <div class="vram">
          <div class="row"><span>VRAM</span><span class="num">${usedGb.toFixed(1)} / ${totalGb.toFixed(1)} GB</span></div>
          <div class="progress thin"><span style="width:${pct(usedGb / totalGb)}"></span></div>
          ${g.power_w != null ? `<div class="row"><span>Power</span><span class="num">${g.power_w.toFixed(0)} W</span></div>` : ''}
        </div>
      </div>`;
  };

  const renderProcessing = () => {
    mode = 'processing';
    framesLoaded = false;
    camerasMounted = false;
    body.innerHTML = `
      <div class="panel"><div class="pipeline" id="pipeline"></div></div>
      <div class="scene-grid">
        <div class="stack">
          <div id="main-card"></div>
          <div class="panel hidden" id="frames-panel"></div>
          <div class="terminal">
            <div class="terminal-bar">
              <span class="lights"><i></i><i></i><i></i></span>${icon('terminal', 14)}<span>Processing log</span>
              <span class="spacer"></span>
              <label><input type="checkbox" id="follow" checked> Follow</label>
              <button class="button small ghost" id="copy-log" type="button">${icon('copy', 13)} Copy</button>
            </div>
            <pre class="log" id="log"></pre>
          </div>
        </div>
        <div class="stack">
          <div class="panel"><div class="panel-body overall" id="overall">
            <div class="row"><span class="eyebrow">Overall progress</span><span class="value">0%</span></div>
            <div class="progress live"><span style="width:0"></span></div>
          </div></div>
          <div class="panel gpu-card" id="gpu-card"></div>
          <div class="panel hidden" id="camera-panel"></div>
          <div class="panel hidden" id="capture-panel"></div>
        </div>
      </div>`;
    body.querySelector('#copy-log').addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(body.querySelector('#log').textContent);
        toast('Log copied', 'success');
      } catch (_) { toast('Copy failed', 'error'); }
    });
    ctx.onSystem(renderGpu);
  };

  const refreshProcessing = () => {
    renderPipeline();
    renderMainCard();
    renderCapturePanel();
    loadFrames(body.querySelector('#frames-panel'));
    loadCameras();
    tickStage();
  };

  // ---------------------------------------------------------------- result view
  const renderResult = async () => {
    mode = 'result';
    if (disposeMini) { await disposeMini(); disposeMini = null; }
    const files = scene.files;
    const s = scene.stats || {};
    let reconstruction = null;
    try { reconstruction = await api.get(`/api/scenes/${id}/reconstruction`); } catch (_) { /* imported scenes have none */ }
    const tabs = VIEW_TABS.filter(([key]) => (key === 'cameras' ? reconstruction : files[key]));

    const stats = [
      ['Frames kept', s.frames_selected != null ? `${num(s.frames_selected)} of ${num(s.frames_decoded)}` : null],
      ['Views placed', s.registered_images != null ? num(s.registered_images) : null],
      ['Sparse points', s.sparse_points != null ? num(s.sparse_points) : null],
      ['3DGS Gaussians', s.gaussians_3dgs != null ? num(s.gaussians_3dgs) : null],
      ['SuGaR Gaussians', s.sugar_splat_count != null ? num(s.sugar_splat_count) : null],
      ['Mesh', s.mesh_faces != null ? `${compact(s.mesh_vertices)} verts · ${compact(s.mesh_faces)} faces` : null],
      ['Video', s.video_duration != null ? `${duration(s.video_duration)} · ${s.video_width}×${s.video_height}` : null],
    ].filter(([, v]) => v != null);

    const timed = scene.stages.filter((st) => scene.stage_times[st.key] != null);
    const totalTime = timed.reduce((sum, st) => sum + scene.stage_times[st.key], 0);

    body.innerHTML = `
      <div class="result-grid">
        <div>
          ${tabs.length ? `
          <div class="viewer" id="viewer">
            <div class="viewer-bar">
              <div class="segmented" id="tabs">${tabs.map(([key, ic, label], i) => `<button data-tab="${key}" class="${i ? '' : 'active'}">${icon(ic, 14)}${label}</button>`).join('')}</div>
              <span class="spacer"></span>
              <button class="button small" id="vr" title="Reload the splat with WebXR enabled. Needs a headset or a WebXR browser.">${icon('headset', 15)} VR</button>
              <button class="button small icon-only" id="reset" title="Reset view" aria-label="Reset view">${icon('locate', 15)}</button>
              <button class="button small icon-only" id="fullscreen" title="Fullscreen" aria-label="Fullscreen">${icon('maximize', 15)}</button>
            </div>
            <div class="viewport" id="viewport"></div>
            <div class="viewer-hint"><span><kbd>drag</kbd>orbit</span><span><kbd>right-drag</kbd>pan</span><span><kbd>scroll</kbd>zoom</span></div>
          </div>` : `<div class="panel empty-state"><h2>Nothing to preview</h2><p>This scene has no viewable output.</p></div>`}
        </div>
        <div class="stack">
          <div class="panel">
            <div class="panel-head"><h2>${icon('download', 17)} Downloads</h2></div>
            <div class="panel-body downloads">
              ${DOWNLOADS.filter(([key]) => files[key]).map(([key, ic, label, hint]) => `
                <a class="download" href="${files[key]}" download>
                  <span class="icon-badge">${icon(ic, 16)}</span>
                  <span><div class="name">${label}</div><div class="hint">${hint}</div></span>
                  <span class="size">${bytes(scene.file_sizes[key])}${icon('download', 14)}</span>
                </a>`).join('')}
            </div>
          </div>
          ${stats.length ? `
          <div class="panel">
            <div class="panel-head"><h2>${icon('aperture', 17)} Reconstruction</h2></div>
            <div class="panel-body"><dl class="kv">${stats.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl></div>
          </div>` : ''}
        </div>
      </div>
      <div class="below">
        ${timed.length ? `
        <div class="panel">
          <div class="panel-head"><h2>${icon('clock', 17)} Where the time went</h2></div>
          <div class="panel-body">
            <div class="timing-total"><span class="value">${duration(totalTime)}</span><span class="faint">on ${esc(scene.preset)} preset</span></div>
            <div class="timing-bar">${timed.map((st, i) => `<span title="${esc(st.label)}: ${duration(scene.stage_times[st.key])}" style="width:${(100 * scene.stage_times[st.key]) / totalTime}%;background:${stageColor(i, timed.length)}"></span>`).join('')}</div>
            <div class="timing-list">${timed.map((st, i) => `
              <div class="row"><span class="swatch" style="background:${stageColor(i, timed.length)}"></span>${esc(st.label)}
                <span class="t">${duration(scene.stage_times[st.key])} · ${Math.round((100 * scene.stage_times[st.key]) / totalTime)}%</span></div>`).join('')}
            </div>
          </div>
        </div>` : ''}
        <div class="panel hidden" id="frames-panel"></div>
        <details class="terminal collapsible ${timed.length ? '' : 'hidden'}" id="log-details">
          <summary class="terminal-bar"><span class="lights"><i></i><i></i><i></i></span>${icon('terminal', 14)}<span>Processing log</span><span class="spacer"></span><span class="chev">${icon('chevron', 14)}</span></summary>
          <pre class="log" id="log"></pre>
        </details>
      </div>`;

    loadFrames(body.querySelector('#frames-panel'));
    body.querySelector('#log-details').addEventListener('toggle', () => pullLog(), { once: true });
    if (!tabs.length) return;

    const viewport = body.querySelector('#viewport');
    let dispose = null;
    let active = tabs[0][0];
    let vr = false;
    const vrButton = body.querySelector('#vr');
    const show = async () => {
      if (dispose) await dispose();
      const view = s.view || reconstruction?.view || null;
      if (active === 'mesh_glb') {
        const onSnapshot = files.thumbnail ? null : async (blob) => {
          const form = new FormData();
          form.append('image', blob, 'thumbnail.jpg');
          try {
            scene = await api.post(`/api/scenes/${id}/thumbnail`, form);
            files.thumbnail = scene.files.thumbnail;
          } catch (_) { /* a thumbnail is a nicety */ }
        };
        dispose = mountMesh(viewport, files.mesh_glb, view, { onSnapshot });
      }
      else if (active === 'cameras') dispose = mountCameras(viewport, reconstruction);
      else dispose = mountSplat(viewport, files[active], view, { vr });
      const splat = active === 'scene_splat' || active === 'sugar_splat';
      vrButton.disabled = !splat;
      vrButton.classList.toggle('on', vr && splat);
    };
    body.querySelector('#tabs').addEventListener('click', (e) => {
      const key = e.target.closest('[data-tab]')?.dataset.tab;
      if (!key || key === active) return;
      active = key;
      body.querySelectorAll('#tabs button').forEach((b) => b.classList.toggle('active', b.dataset.tab === key));
      show();
    });
    vrButton.addEventListener('click', () => {
      vr = !vr;
      if (vr) toast('VR mode on: use the “Enter VR” button in the viewer', 'info');
      show();
    });
    body.querySelector('#reset').addEventListener('click', show);
    body.querySelector('#fullscreen').addEventListener('click', () => body.querySelector('#viewer').requestFullscreen?.());
    ctx.onLeave(async () => { if (dispose) await dispose(); });
    show();
  };

  // ---------------------------------------------------------------- log
  const pullLog = async () => {
    const log = body.querySelector('#log');
    if (!log) return;
    const chunk = await api.get(`/api/scenes/${id}/log?offset=${logOffset}`);
    if (!chunk.text) return;
    logOffset = chunk.offset;
    const lines = chunk.text.split('\n');
    if (lines[lines.length - 1] === '') lines.pop();
    const html = lines.map((line) => {
      const cls = logLineClass(line);
      return cls ? `<span class="${cls}">${esc(line)}</span>` : esc(line);
    }).join('\n');
    log.insertAdjacentHTML('beforeend', `${log.childNodes.length ? '\n' : ''}${html}`);
    while (log.childNodes.length > 6000) log.removeChild(log.firstChild);
    const last = [...lines].reverse().find((l) => l.trim() && !/^\[archeon\] (\$|=====)/.test(l) && !/^I\d{8} /.test(l));
    const lastColmap = [...lines].reverse().find((l) => /^I\d{8} /.test(l));
    const candidate = last || (lastColmap && lastColmap.replace(/^I\d{8} [\d:.]+\s+\d+\s+\S+\]\s*/, ''));
    if (candidate) {
      activity = candidate.replace(/^\[archeon\] /, '');
      const el = body.querySelector('#activity');
      if (el) el.textContent = activity;
    }
    const follow = body.querySelector('#follow');
    if (!follow || follow.checked) log.scrollTop = log.scrollHeight;
  };

  // ---------------------------------------------------------------- update loop
  async function update() {
    renderHead();
    if (scene.status === 'done') {
      if (mode !== 'result') {
        logOffset = 0;
        await renderResult();
      }
      return;
    }
    if (mode !== 'processing') {
      logOffset = 0;
      renderProcessing();
    }
    refreshProcessing();
    pullLog().catch(() => {});
  }

  await update();
  ctx.every(1000, () => { if (mode === 'processing') tickStage(); });
  ctx.every(1500, async () => {
    if (mode === 'result') return;
    try {
      const previous = scene.status;
      scene = await api.get(`/api/scenes/${id}`);
      if (previous !== scene.status && scene.status === 'done') toast(`${scene.name} is ready`, 'success');
      await update();
    } catch (_) { /* transient */ }
  });
}

