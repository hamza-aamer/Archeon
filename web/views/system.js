import { ago, api, bytes, esc, statusPill } from '../lib/util.js';
import { icon } from '../lib/icons.js';
import { confirmDialog, sparkline, toast } from '../lib/ui.js';

const VERSION_LABELS = [
  ['driver', 'NVIDIA driver'],
  ['compute_capability', 'Compute capability'],
  ['torch', 'PyTorch'],
  ['cuda', 'CUDA (PyTorch)'],
  ['pytorch3d', 'PyTorch3D'],
  ['colmap', 'COLMAP'],
  ['ffmpeg', 'ffmpeg'],
  ['open3d', 'Open3D'],
  ['numpy', 'NumPy'],
  ['python', 'Python'],
  ['sugar_commit', 'SuGaR commit'],
];

function verdict(preset, gb) {
  if (gb == null) return '<span class="pill status-failed">No GPU</span>';
  if (gb + 0.5 < preset.min_vram_gb) return '<span class="pill status-failed">Below minimum</span>';
  if (gb + 0.5 < preset.recommended_vram_gb) return '<span class="pill status-queued">May not fit</span>';
  return '<span class="pill status-done">Supported</span>';
}

export async function renderSystem(root, ctx) {
  const { presets } = await api.get('/api/presets');
  root.innerHTML = `
    <div class="page-head">
      <div>
        <div class="eyebrow">System</div>
        <h1 style="margin-top:8px">Hardware, software &amp; storage</h1>
        <p class="lede">What this machine can run, what is installed, and where the disk space goes.</p>
      </div>
    </div>
    <div class="system-grid">
      <section class="panel" id="gpu"><div class="skeleton" style="height:320px"></div></section>
      <section class="panel" id="compat"></section>
    </div>
    <section class="panel" id="diag" style="margin-top:20px"></section>
    <section class="panel" id="storage" style="margin-top:20px"></section>`;

  // ---------------------------------------------------------------- GPU (live)
  const gpuEl = root.querySelector('#gpu');
  const compatEl = root.querySelector('#compat');
  const renderGpu = (data, history) => {
    const g = data.gpu;
    if (!g) {
      gpuEl.innerHTML = `<div class="panel-body"><div class="notice error">${icon('alert', 15)}<span>No NVIDIA GPU detected: <span class="mono">nvidia-smi</span> is unavailable. Archeon needs a CUDA GPU to process scenes.</span></div></div>`;
      return;
    }
    const totalGb = g.memory_total_mb / 1024;
    const usedGb = g.memory_used_mb / 1024;
    const tiles = [
      ['Utilisation', Math.round(g.utilization ?? 0), '%'],
      ['VRAM in use', usedGb.toFixed(1), ` / ${totalGb.toFixed(1)} GB`],
      ['Temperature', g.temperature_c ?? '–', '°C'],
      ['Power', g.power_w != null ? Math.round(g.power_w) : '–', 'W'],
    ];
    const minutes = history.length ? Math.max(1, Math.round((history[history.length - 1].t - history[0].t) / 60000)) : 0;
    gpuEl.innerHTML = `
      <div class="panel-head">
        <h2>${icon('cpu', 17)} ${esc(g.name.replace(/^NVIDIA\s+/, ''))}</h2>
        <span class="live-tag"><span class="dot"></span>Live</span>
      </div>
      <div class="panel-body">
        <div class="tiles">${tiles.map(([label, value, unit]) => `
          <div class="tile"><div class="eyebrow">${label}</div><div class="tile-value num">${value}<small>${unit}</small></div></div>`).join('')}
        </div>
        <div class="charts">
          <div class="chart">
            <div class="row"><span class="eyebrow">Utilisation</span><span class="spacer"></span><span class="faint" style="font-size:11.5px">last ${minutes || '<1'} min</span></div>
            ${sparkline(history.map((h) => h.util), { height: 84 })}
          </div>
          <div class="chart">
            <div class="row"><span class="eyebrow">VRAM</span><span class="spacer"></span><span class="faint" style="font-size:11.5px">of ${totalGb.toFixed(1)} GB</span></div>
            ${sparkline(history.map((h) => h.mem), { height: 84, max: g.memory_total_mb })}
          </div>
        </div>
      </div>`;

    compatEl.innerHTML = `
      <div class="panel-head"><h2>${icon('layers', 17)} What this GPU can run</h2></div>
      <div class="panel-body">
        <div class="compat">${presets.map((p) => `
          <div class="compat-row">
            <div><div style="font-weight:600">${esc(p.label)}</div><div class="faint" style="font-size:12px">${p.sugar ? 'Splat + SuGaR mesh' : 'Splat only'} · ≈ ${esc(p.estimate)}</div></div>
            <div class="compat-vram num">${p.min_vram_gb}<small> / ${p.recommended_vram_gb} GB</small></div>
            ${verdict(p, totalGb)}
          </div>`).join('')}
        </div>
        <p class="faint" style="font-size:12px;margin-top:14px">VRAM shown as minimum / recommended. The 3DGS authors specify 24 GB for full-quality training; SuGaR keeps every frame on the GPU and adds its own models on top. You can run any preset on any GPU, but below the minimum it will usually stop with an out-of-memory error.</p>
      </div>`;
  };
  ctx.onSystem(renderGpu);

  // ---------------------------------------------------------------- diagnostics
  const diagEl = root.querySelector('#diag');
  const renderDiagnostics = (data) => {
    const failed = data.checks.filter((c) => !c.ok).length;
    diagEl.innerHTML = `
      <div class="panel-head">
        <h2>${icon('check', 17)} Diagnostics</h2>
        <span class="spacer"></span>
        <span class="faint" style="font-size:12px">checked ${ago(data.checked_at)}</span>
        <button class="button small" id="rerun">${icon('refresh', 14)} Run again</button>
      </div>
      <div class="panel-body diag-grid">
        <div>
          <div class="diag-summary ${failed ? 'bad' : 'ok'}">${icon(failed ? 'alert' : 'check', 18)}
            <span>${failed ? `${failed} check${failed > 1 ? 's' : ''} failed: processing will not work until fixed.` : 'Everything Archeon needs is installed and working.'}</span></div>
          <div class="checks">${data.checks.map((c) => `
            <div class="check-row ${c.ok ? 'ok' : 'bad'}">${icon(c.ok ? 'check' : 'x', 15)}
              <div><div>${esc(c.name.replace(/^python: /, ''))}</div>${c.detail ? `<div class="detail">${esc(c.detail)}</div>` : ''}</div></div>`).join('')}
          </div>
        </div>
        <div>
          <div class="eyebrow" style="margin-bottom:12px">Versions</div>
          <dl class="kv">${VERSION_LABELS.filter(([key]) => data.versions[key]).map(([key, label]) => `<dt>${label}</dt><dd class="mono">${esc(data.versions[key])}</dd>`).join('')}</dl>
        </div>
      </div>`;
    diagEl.querySelector('#rerun').addEventListener('click', () => loadDiagnostics(true));
  };
  const loadDiagnostics = async (refresh = false) => {
    diagEl.innerHTML = `
      <div class="panel-head"><h2>${icon('check', 17)} Diagnostics</h2><span class="spacer"></span><span class="faint" style="font-size:12px">Running checks: loads PyTorch and the CUDA extensions…</span></div>
      <div class="panel-body diag-grid"><div class="skeleton" style="height:260px"></div><div class="skeleton" style="height:260px"></div></div>`;
    try {
      renderDiagnostics(await api.get(`/api/diagnostics${refresh ? '?refresh=1' : ''}`));
    } catch (err) {
      diagEl.innerHTML = `<div class="panel-body"><div class="notice error">${icon('alert', 15)}<span>${esc(err.message)}</span></div></div>`;
    }
  };

  // ---------------------------------------------------------------- storage
  const storageEl = root.querySelector('#storage');
  const renderStorage = async () => {
    const data = await api.get('/api/storage');
    const used = data.disk.total - data.disk.free;
    const share = (n) => `${Math.max(0.4, (100 * n) / data.disk.total)}%`;
    storageEl.innerHTML = `
      <div class="panel-head"><h2>${icon('drive', 17)} Storage</h2><span class="faint mono" style="font-size:12px">${esc(data.data_dir)}</span></div>
      <div class="panel-body">
        <div class="usage-bar">
          <span class="seg archeon" style="width:${share(data.total)}" title="Archeon data"></span>
          <span class="seg other" style="width:${share(Math.max(used - data.total, 0))}" title="Other files"></span>
        </div>
        <div class="usage-legend">
          <span><i class="archeon"></i>Archeon <b class="num">${bytes(data.total)}</b></span>
          <span><i class="other"></i>Other files <b class="num">${bytes(Math.max(used - data.total, 0))}</b></span>
          <span><i></i>Free <b class="num">${bytes(data.disk.free)}</b></span>
        </div>
        ${data.scenes.length ? `
        <div class="table-wrap" style="margin-top:18px"><table class="table">
          <thead><tr><th>Scene</th><th>Status</th><th class="r">Video</th><th class="r">Working files</th><th class="r">Outputs</th><th class="r">Total</th><th></th></tr></thead>
          <tbody>${data.scenes.map((s) => `
            <tr>
              <td><a class="queue-name" href="#/scene/${s.id}">${esc(s.name)}</a></td>
              <td>${statusPill(s.status)}</td>
              <td class="r num">${s.video ? bytes(s.video) : '–'}</td>
              <td class="r num">${s.work ? bytes(s.work) : '–'}</td>
              <td class="r num">${s.artifacts ? bytes(s.artifacts) : '–'}</td>
              <td class="r num"><b>${bytes(s.video + s.work + s.artifacts)}</b></td>
              <td class="r">${s.status === 'done' && s.work > 5 * 2 ** 20
                ? `<button class="button small" data-clean="${s.id}" data-name="${esc(s.name)}" data-size="${s.work}">${icon('trash', 13)} Free ${bytes(s.work)}</button>` : ''}</td>
            </tr>`).join('')}</tbody>
        </table></div>
        <p class="faint" style="font-size:12px;margin-top:12px">Working files are the frames, COLMAP model and training checkpoints. They let a failed scene resume, but a finished scene no longer needs them.</p>`
        : '<p class="faint" style="margin-top:16px">No scenes on disk yet.</p>'}
      </div>`;
  };
  const onClick = async (e) => {
    const button = e.target.closest('[data-clean]');
    if (!button) return;
    const ok = await confirmDialog({
      title: `Free ${bytes(Number(button.dataset.size))}?`,
      body: `Deletes the working files of “${button.dataset.name}”. Its downloads, viewer and frame previews are kept.`,
      confirm: 'Delete working files',
    });
    if (!ok) return;
    try {
      const { freed } = await api.post(`/api/scenes/${button.dataset.clean}/clean`);
      toast(`Freed ${bytes(freed)}`, 'success');
      renderStorage();
    } catch (err) {
      toast(err.message, 'error');
    }
  };
  storageEl.addEventListener('click', onClick);

  renderStorage().catch((err) => {
    storageEl.innerHTML = `<div class="panel-body faint">${esc(err.message)}</div>`;
  });
  loadDiagnostics();
}
