import { api, esc } from '../lib/util.js';
import { STAGE_ICONS, icon } from '../lib/icons.js';

const DO = [
  ['orbit', 'Move around the subject', 'Walk a slow arc or full loop so every surface is seen from several angles.'],
  ['hand', 'Move slowly and steadily', 'Consecutive frames should overlap by most of the picture. Sharpness beats resolution.'],
  ['sun', 'Use even, constant light', 'Lock exposure if your camera allows it. Overcast daylight is ideal outdoors.'],
  ['clock', 'Film 30 s to 2 min', 'More views help; Archeon keeps the sharpest frame from each moment.'],
];
const AVOID = [
  ['refresh', 'Spinning on the spot', 'Rotation without movement gives COLMAP no baseline to triangulate depth.'],
  ['ban', 'Reflective or see-through surfaces', 'Mirrors, glass, chrome and glossy floors change appearance as you move.'],
  ['image', 'Blank, textureless areas', 'White walls and clear sky have nothing to match between frames.'],
  ['video', 'Things that move', 'People, pets, trees in wind and screens break the static-scene assumption.'],
];

const OUTPUTS = [
  ['sparkles', 'scene.ply', 'Gaussian splat', 'The standard 3DGS file. Opens in the Archeon Unity VR viewer, SuperSplat, Blender splat add-ons and most splat viewers.'],
  ['sparkles', 'scene.splat', 'Web splat', 'The same splat packed to 32 bytes per Gaussian (base colour only). Loads quickly in browsers.'],
  ['layers', 'sugar.ply', 'SuGaR splat', 'Gaussians bound to the mesh surface. Can be edited or animated together with the mesh.'],
  ['box', 'mesh.obj / .png', 'Textured mesh', 'SuGaR’s UV-textured mesh, for Blender, Unity, Unreal, or 3D printing after cleanup.'],
  ['box', 'mesh.glb', 'Single-file mesh', 'The same mesh with its texture embedded, used by the in-browser mesh viewer.'],
];

const CREDITS = [
  ['SuGaR', 'Guédon & Lepetit, CVPR 2024', 'Surface-aligned Gaussians and mesh extraction', 'Inria non-commercial', 'https://github.com/Anttwo/SuGaR'],
  ['3D Gaussian Splatting', 'Kerbl et al., SIGGRAPH 2023', 'The differentiable splat renderer and trainer', 'Inria non-commercial', 'https://github.com/graphdeco-inria/gaussian-splatting'],
  ['COLMAP', 'Schönberger & Frahm', 'Structure-from-motion camera poses', 'BSD', 'https://colmap.github.io/'],
  ['GaussianSplats3D', 'Mark Kellogg', 'WebGL splat viewer with WebXR', 'MIT', 'https://github.com/mkkellogg/GaussianSplats3D'],
  ['three.js', 'three.js authors', 'WebGL scene graph for the mesh and camera views', 'MIT', 'https://threejs.org/'],
];

const SECTIONS = [
  ['pipeline', 'How it works'],
  ['capture', 'Capturing'],
  ['outputs', 'What you get'],
  ['vr', 'Viewing in VR'],
  ['hardware', 'Hardware'],
  ['credits', 'Credits'],
];

export async function renderGuide(root, ctx) {
  const [stages, { presets }] = await Promise.all([api.get('/api/pipeline'), api.get('/api/presets')]);

  root.innerHTML = `
    <div class="guide-hero">
      <div class="eyebrow">Guide</div>
      <h1>From a phone video to a 3D space</h1>
      <p class="lede">Archeon chains three research systems: COLMAP for camera poses, 3D Gaussian Splatting for a photoreal radiance field, and SuGaR for a textured mesh. Then it packages the results for the browser, VR and 3D tools.</p>
    </div>
    <div class="guide">
      <nav class="toc" aria-label="Guide sections">
        ${SECTIONS.map(([id, label], i) => `<button data-target="${id}" class="${i ? '' : 'active'}">${label}</button>`).join('')}
      </nav>
      <div class="guide-body">
        <section id="pipeline" class="guide-section">
          <h2>How it works</h2>
          <p class="muted">Each upload runs through these stages on the GPU. Every stage writes its output to disk, so a failed or interrupted run resumes where it stopped.</p>
          <ol class="timeline">
            ${stages.map((s, i) => `
              <li>
                <div class="timeline-node">${icon(STAGE_ICONS[s.key] || 'sparkles', 18)}</div>
                <div class="timeline-body">
                  <div class="row" style="gap:10px;flex-wrap:wrap">
                    <span class="faint num" style="font-size:12px">${String(i + 1).padStart(2, '0')}</span>
                    <h3>${esc(s.label)}</h3>
                    <span class="spacer"></span>
                    ${presets.map((p) => `<span class="preset-tag ${s.presets.includes(p.name) ? 'on' : ''}">${esc(p.label)}</span>`).join('')}
                  </div>
                  <p>${esc(s.description)}</p>
                </div>
              </li>`).join('')}
          </ol>
        </section>

        <section id="capture" class="guide-section">
          <h2>Capturing a good scene</h2>
          <p class="muted">Reconstruction quality is decided at capture time. A careful 60-second video beats a rushed 5-minute one.</p>
          <div class="do-avoid">
            <div class="panel panel-pad">
              <div class="do-head ok">${icon('check', 16)} Do</div>
              <ul class="tips">${DO.map(([i, t, d]) => `<li><div class="icon-badge ok">${icon(i, 16)}</div><div><strong>${t}</strong><span>${d}</span></div></li>`).join('')}</ul>
            </div>
            <div class="panel panel-pad">
              <div class="do-head bad">${icon('x', 16)} Avoid</div>
              <ul class="tips">${AVOID.map(([i, t, d]) => `<li><div class="icon-badge bad">${icon(i, 16)}</div><div><strong>${t}</strong><span>${d}</span></div></li>`).join('')}</ul>
            </div>
          </div>
        </section>

        <section id="outputs" class="guide-section">
          <h2>What you get</h2>
          <p class="muted">Every finished scene has these downloads on its page (mesh files need the Standard or High preset).</p>
          <div class="output-grid">
            ${OUTPUTS.map(([i, file, title, text]) => `
              <div class="panel panel-pad output-card">
                <div class="row"><div class="icon-badge">${icon(i, 16)}</div><span class="spacer"></span><span class="mono faint" style="font-size:12px">${file}</span></div>
                <h3 style="margin-top:14px">${title}</h3>
                <p class="faint" style="font-size:13px;margin-top:6px">${text}</p>
              </div>`).join('')}
          </div>
        </section>

        <section id="vr" class="guide-section">
          <h2>Viewing in VR</h2>
          <div class="vr-grid">
            <div class="panel panel-pad">
              <div class="row"><div class="icon-badge">${icon('headset', 16)}</div><h3>In the browser (WebXR)</h3></div>
              <ol class="steps">
                <li>Open the scene and choose the <b>Splat</b> view.</li>
                <li>Click <b>VR</b>; the viewer reloads with an <b>Enter VR</b> button.</li>
                <li>On a Meta Quest, open this server's address in the Quest browser. On a PC headset, use Chrome or Edge with SteamVR or Oculus Link.</li>
              </ol>
            </div>
            <div class="panel panel-pad">
              <div class="row"><div class="icon-badge">${icon('package', 16)}</div><h3>Unity VR viewer (Windows)</h3></div>
              <ol class="steps">
                <li>Unzip <span class="mono">clients/unity-vr-viewer/ArcheonViewer-win64.zip</span>.</li>
                <li>Download the scene's <b>Gaussian splat (.ply)</b> into the folder you launch the viewer from.</li>
                <li>Run <span class="mono">ArcheonViewer.exe</span> with your headset connected. It loads every <span class="mono">.ply</span> in its working folder.</li>
              </ol>
            </div>
          </div>
        </section>

        <section id="hardware" class="guide-section">
          <h2>Hardware requirements</h2>
          <p class="muted">Processing needs an NVIDIA GPU with CUDA. Memory needs grow with frame count and resolution: SuGaR keeps every training frame on the GPU. The 3DGS authors specify 24 GB for full-quality training.</p>
          <div class="panel" style="margin-top:16px"><div class="table-wrap"><table class="table">
            <thead><tr><th>Preset</th><th>Output</th><th class="r">Frames</th><th class="r">Min VRAM</th><th class="r">Recommended</th><th class="r">Typical time</th></tr></thead>
            <tbody>${presets.map((p) => `
              <tr><td><b>${esc(p.label)}</b></td><td class="muted">${p.sugar ? 'Splat + mesh' : 'Splat'}</td><td class="r num">${p.max_frames} @ ${p.max_side}px</td>
              <td class="r num">${p.min_vram_gb} GB</td><td class="r num">${p.recommended_vram_gb} GB</td><td class="r num">${esc(p.estimate)}</td></tr>`).join('')}
            </tbody></table></div></div>
          <p class="faint" style="font-size:12.5px;margin-top:12px">Software stack: PyTorch 2.0.1 with CUDA 11.8 (SuGaR's tested versions), so GPUs up to compute capability 9.0 (RTX 20/30/40-series, A100/H100). The <a href="#/system">System page</a> shows how this machine compares.</p>
        </section>

        <section id="credits" class="guide-section">
          <h2>Credits</h2>
          <p class="muted">Archeon is a final-year project built on open research code. Each component keeps its own license.</p>
          <div class="credits">${CREDITS.map(([name, who, what, license, url]) => `
            <a class="credit" href="${url}" target="_blank" rel="noopener">
              <div><div style="font-weight:600">${name}</div><div class="faint" style="font-size:12.5px">${who} · ${what}</div></div>
              <span class="pill plain">${license}</span>
            </a>`).join('')}
          </div>
        </section>
      </div>
    </div>`;

  // Table of contents: smooth scroll, and highlight the section in view.
  const toc = root.querySelector('.toc');
  toc.addEventListener('click', (e) => {
    const id = e.target.closest('[data-target]')?.dataset.target;
    if (id) root.querySelector(`#${id}`).scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  const observer = new IntersectionObserver((entries) => {
    entries.filter((en) => en.isIntersecting).forEach((en) => {
      toc.querySelectorAll('button').forEach((b) => b.classList.toggle('active', b.dataset.target === en.target.id));
    });
  }, { rootMargin: '-30% 0px -60% 0px' });
  root.querySelectorAll('.guide-section').forEach((section) => observer.observe(section));
  ctx.onLeave(() => observer.disconnect());
}
