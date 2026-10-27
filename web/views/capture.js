import { api, bytes, duration, esc, pct } from '../lib/util.js';
import { icon } from '../lib/icons.js';
import { toast } from '../lib/ui.js';

const OUTPUTS = {
  preview: ['Gaussian splat'],
  standard: ['Gaussian splat', 'Textured mesh'],
  high: ['Gaussian splat', 'High-poly mesh'],
};

function gpuFit(preset, gpuGb) {
  if (gpuGb == null) return '';
  const have = Math.round(gpuGb);
  if (gpuGb + 0.5 < preset.min_vram_gb) {
    return `<div class="fit bad">${icon('alert', 13)}<span>Your GPU has ${have} GB, below the ${preset.min_vram_gb} GB minimum. Expect it to run out of memory.</span></div>`;
  }
  if (gpuGb + 0.5 < preset.recommended_vram_gb) {
    return `<div class="fit warn">${icon('info', 13)}<span>${have} GB available, ${preset.recommended_vram_gb} GB recommended. Larger scenes may not fit.</span></div>`;
  }
  return `<div class="fit ok">${icon('check', 13)}<span>Fits your ${have} GB GPU</span></div>`;
}

const TIPS = [
  ['orbit', 'Move around the subject', 'Walk a slow arc or loop. Rotating in place gives COLMAP nothing to triangulate.'],
  ['hand', 'Keep it steady', 'Sharp frames matter more than resolution. Slow down in tight spots.'],
  ['sun', 'Even, fixed lighting', 'Avoid flicker, harsh shadows and auto-exposure jumps.'],
  ['ban', 'Skip the hard stuff', 'Mirrors, glass, glossy floors, blank walls and moving people break matching.'],
  ['clock', '30 seconds to 2 minutes', 'Longer clips are fine. Archeon keeps the sharpest frames from each moment.'],
];

export async function renderCapture(root, ctx) {
  const [{ presets, default: fallback }, system] = await Promise.all([api.get('/api/presets'), api.get('/api/system')]);
  const gpu = system.gpu;
  const gpuGb = gpu ? gpu.memory_total_mb / 1024 : null;
  // Pre-select the recommended preset, unless this GPU is below its minimum: then the best one that fits.
  const fitting = presets.filter((p) => gpuGb == null || gpuGb + 0.5 >= p.min_vram_gb);
  const preferred = fitting.some((p) => p.name === fallback) ? fallback : (fitting[fitting.length - 1] || presets[0]).name;

  root.innerHTML = `
    <div class="page-head">
      <div>
        <div class="eyebrow">New capture</div>
        <h1 style="margin-top:8px">Turn a video into a 3D scene</h1>
        <p class="lede">Upload a walkthrough video, or record one with your phone's browser. Processing runs locally on this machine's GPU.</p>
      </div>
    </div>
    <div class="capture">
      <form class="panel panel-pad stack" id="form" novalidate>
        <div id="source"></div>
        <div class="field">
          <label class="label" for="name">Scene name</label>
          <input type="text" id="name" maxlength="120" placeholder="e.g. Living room, Garden statue" autocomplete="off">
        </div>
        <div class="field">
          <span class="label">Quality</span>
          <div class="presets" role="radiogroup">
            ${presets.map((p) => `
              <label class="preset">
                ${p.name === fallback ? '<span class="recommended">RECOMMENDED</span>' : ''}
                <input type="radio" name="preset" value="${esc(p.name)}" ${p.name === preferred ? 'checked' : ''}>
                <div class="top"><span class="name">${esc(p.label)}</span><span class="radio"></span></div>
                <div class="desc">${esc(p.description)}</div>
                <div class="outputs">${(OUTPUTS[p.name] || []).map((o) => `<span class="metric">${icon(o.includes('mesh') ? 'box' : 'sparkles', 12)}${o}</span>`).join('')}</div>
                <dl class="spec">
                  <dt>Frames</dt><dd>up to ${p.max_frames} · ${p.max_side}px</dd>
                  <dt>VRAM</dt><dd>${p.min_vram_gb} GB min · ${p.recommended_vram_gb} GB rec.</dd>
                  <dt>Time</dt><dd>≈ ${esc(p.estimate)}</dd>
                </dl>
                ${gpuFit(p, gpuGb)}
              </label>`).join('')}
          </div>
        </div>
        <div id="upload" class="upload-status hidden"></div>
        <div id="form-error"></div>
        <div class="row">
          <span class="faint" style="font-size:12.5px">The video stays on this machine.</span>
          <span class="spacer"></span>
          <button class="button primary large" id="submit" type="submit" disabled>${icon('sparkles', 17)} Start processing</button>
        </div>
      </form>

      <aside class="stack">
        <div class="panel">
          <div class="panel-head"><h2>${icon('cpu', 17)} This machine</h2></div>
          <div class="panel-body stack-sm">
            ${gpu ? `
              <dl class="kv">
                <dt>GPU</dt><dd>${esc(gpu.name.replace(/^NVIDIA\s+/, ''))}</dd>
                <dt>VRAM</dt><dd>${(gpu.memory_total_mb / 1024).toFixed(1)} GB</dd>
              </dl>
              <p class="faint" style="font-size:12.5px">SuGaR keeps every training frame on the GPU and adds its own models on top of 3DGS, whose authors specify 24 GB for full-quality training. Times are estimates for a GPU that meets the recommendation.</p>`
              : `<div class="notice error">${icon('alert', 15)}<span>No NVIDIA GPU detected. Processing needs a CUDA GPU.</span></div>`}
          </div>
        </div>
        <div class="panel">
          <div class="panel-head"><h2>${icon('video', 17)} Capturing well</h2></div>
          <div class="panel-body">
            <ul class="tips">
              ${TIPS.map(([i, title, text]) => `<li><div class="icon-badge">${icon(i, 16)}</div><div><strong>${title}</strong><span>${text}</span></div></li>`).join('')}
            </ul>
          </div>
        </div>
        <div class="panel">
          <div class="panel-head"><h2>${icon('phone', 17)} Record from your phone</h2></div>
          <div class="panel-body stack-sm">
            <p class="muted" style="font-size:13px">Open this address on a phone on the same network, then use <b>Record</b>: the clip uploads straight into the queue.</p>
            ${(system.urls || []).map((url) => `
              <div class="lan-url"><span style="overflow:hidden;text-overflow:ellipsis">${esc(url)}</span><span class="spacer"></span>
                <button class="button small ghost icon-only" type="button" data-copy="${esc(url)}" title="Copy">${icon('copy', 14)}</button></div>`).join('')}
            ${system.wsl ? `<div class="notice info">${icon('info', 15)}<span>This server runs inside WSL2. Phones can only reach it once Windows forwards the port (<span class="mono">netsh interface portproxy</span>) or WSL uses mirrored networking.</span></div>` : ''}
          </div>
        </div>
      </aside>
    </div>`;

  const form = root.querySelector('#form');
  const source = root.querySelector('#source');
  const nameInput = root.querySelector('#name');
  const submit = root.querySelector('#submit');
  const errorBox = root.querySelector('#form-error');
  let file = null;
  let objectUrl = null;
  ctx.onLeave(() => objectUrl && URL.revokeObjectURL(objectUrl));

  root.querySelectorAll('[data-copy]').forEach((b) => b.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(b.dataset.copy);
      toast('Address copied', 'success');
    } catch (_) {
      toast('Copy failed: select the address manually', 'error');
    }
  }));

  const renderPicker = () => {
    source.innerHTML = `
      <div class="dropzone" id="drop" role="button" tabindex="0" aria-label="Choose a video">
        <input type="file" accept="video/*" hidden id="file">
        <div>
          <div class="icon-badge">${icon('upload', 22)}</div>
          <strong>Drop a video here, or browse</strong>
          <div class="formats" style="margin-top:6px">MP4 · MOV · MKV · WebM, from any phone or camera</div>
        </div>
        <label class="button small" id="record-button" style="margin-top:6px">
          <input type="file" accept="video/*" capture="environment" hidden id="record">${icon('video', 15)} Record with camera
        </label>
      </div>`;
    const drop = source.querySelector('#drop');
    const fileInput = source.querySelector('#file');
    fileInput.addEventListener('change', (e) => choose(e.target.files[0]));
    source.querySelector('#record').addEventListener('change', (e) => choose(e.target.files[0]));
    drop.addEventListener('click', (e) => {
      if (e.target !== fileInput && !e.target.closest('#record-button')) fileInput.click();
    });
    drop.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        fileInput.click();
      }
    });
    drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
    drop.addEventListener('dragleave', () => drop.classList.remove('over'));
    drop.addEventListener('drop', (e) => {
      e.preventDefault();
      drop.classList.remove('over');
      choose(e.dataTransfer.files[0]);
    });
  };

  const renderPreview = () => {
    source.innerHTML = `
      <div class="preview">
        <video src="${objectUrl}" muted playsinline autoplay loop></video>
        <button class="button small replace" type="button" id="replace">${icon('refresh', 14)} Replace</button>
      </div>
      <div class="video-facts" id="facts">
        <span class="metric">${icon('file', 12)}${esc(file.name)}</span>
        <span class="metric">${icon('drive', 12)}${bytes(file.size)}</span>
      </div>
      <div id="video-warning" style="margin-top:12px"></div>`;
    source.querySelector('#replace').addEventListener('click', () => {
      file = null;
      submit.disabled = true;
      renderPicker();
    });
    const video = source.querySelector('video');
    video.addEventListener('loadedmetadata', () => {
      const facts = source.querySelector('#facts');
      const { videoWidth: w, videoHeight: h, duration: d } = video;
      facts.insertAdjacentHTML('beforeend', `
        <span class="metric">${icon('clock', 12)}${duration(d)}</span>
        <span class="metric">${icon('image', 12)}${w}×${h} ${h > w ? 'portrait' : 'landscape'}</span>`);
      const warn = source.querySelector('#video-warning');
      if (d < 8) {
        warn.innerHTML = `<div class="notice warn">${icon('alert', 15)}<span>This clip is only ${duration(d)} long. Very short clips rarely give COLMAP enough viewpoints. For reliable results, film 30 s or more while moving around the subject.</span></div>`;
      } else if (d > 300) {
        warn.innerHTML = `<div class="notice info">${icon('info', 15)}<span>Long clip: Archeon samples it evenly and keeps the sharpest frame from each moment.</span></div>`;
      }
    });
  };

  const choose = (picked) => {
    if (!picked) return;
    if (!picked.type.startsWith('video/') && !/\.(mp4|mov|m4v|mkv|webm|avi|3gp)$/i.test(picked.name)) {
      toast('That file is not a video', 'error');
      return;
    }
    file = picked;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(picked);
    if (!nameInput.value) {
      nameInput.value = picked.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
    }
    submit.disabled = false;
    errorBox.innerHTML = '';
    renderPreview();
  };

  renderPicker();

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    if (!file) return;
    const body = new FormData();
    body.append('video', file);
    body.append('name', nameInput.value);
    body.append('preset', form.preset.value);

    const status = root.querySelector('#upload');
    status.classList.remove('hidden');
    status.innerHTML = `
      <div class="row"><span>Uploading</span><span class="faint num" id="up-text"></span></div>
      <div class="progress live"><span style="width:0"></span></div>`;
    const bar = status.querySelector('.progress span');
    const text = status.querySelector('#up-text');
    errorBox.innerHTML = '';
    submit.disabled = true;
    const started = performance.now();

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/scenes');
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      const fraction = event.loaded / event.total;
      const seconds = (performance.now() - started) / 1000;
      const rate = event.loaded / Math.max(seconds, 0.001);
      bar.style.width = pct(fraction);
      text.textContent = fraction < 1
        ? `${bytes(event.loaded)} of ${bytes(event.total)} · ${bytes(rate)}/s · ${duration((event.total - event.loaded) / rate)} left`
        : 'Saving on the server…';
    };
    const fail = (message) => {
      status.classList.add('hidden');
      errorBox.innerHTML = `<div class="notice error">${icon('alert', 15)}<span>${esc(message)}</span></div>`;
      submit.disabled = false;
    };
    xhr.onload = () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch (_) { /* empty */ }
      if (xhr.status === 201) {
        toast('Upload complete: processing has started', 'success');
        location.hash = `#/scene/${data.id}`;
      } else {
        fail(data.detail || `Upload failed (HTTP ${xhr.status})`);
      }
    };
    xhr.onerror = () => fail('Upload failed: the server could not be reached.');
    xhr.send(body);
    ctx.onLeave(() => { if (xhr.readyState !== 4) xhr.abort(); });
  });
}
