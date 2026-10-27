// Splat and mesh viewers. Each mount function returns an async dispose() so tabs can switch cleanly.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import * as GaussianSplats3D from 'gaussian-splats-3d';

// COLMAP scenes have +y pointing down; used when a scene has no computed view.
const FALLBACK_VIEW = { position: [0, -1.5, -5], look_at: [0, 0, 0], up: [0, -1, 0] };

function overlay(container, text) {
  let el = container.querySelector('.overlay-msg');
  if (!el) {
    el = document.createElement('div');
    el.className = 'overlay-msg';
    container.appendChild(el);
  }
  el.textContent = text || '';
  el.hidden = !text;
  return el;
}

export function mountSplat(container, url, view, { vr = false } = {}) {
  const v = view || FALLBACK_VIEW;
  const viewer = new GaussianSplats3D.Viewer({
    rootElement: container,
    cameraUp: v.up,
    initialCameraPosition: v.position,
    initialCameraLookAt: v.look_at,
    sharedMemoryForWorkers: false, // avoids needing cross-origin isolation headers
    webXRMode: vr ? GaussianSplats3D.WebXRMode.VR : GaussianSplats3D.WebXRMode.None,
    renderMode: GaussianSplats3D.RenderMode.Always,
  });
  let disposed = false;
  viewer
    .addSplatScene(url, { showLoadingUI: true, progressiveLoad: true, splatAlphaRemovalThreshold: 5 })
    .then(() => { if (!disposed) viewer.start(); })
    .catch((err) => { if (!disposed) overlay(container, `Could not load splat: ${err.message || err}`); });
  return async () => {
    disposed = true;
    try { await viewer.dispose(); } catch (_) { /* viewer may still be loading */ }
    container.replaceChildren();
  };
}

export function mountMesh(container, url, view, { onSnapshot } = {}) {
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x07070d);
  const camera = new THREE.PerspectiveCamera(55, 1, 0.01, 1000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  const resize = () => {
    const { clientWidth: w, clientHeight: h } = container;
    renderer.setSize(w, h);
    camera.aspect = w / Math.max(h, 1);
    camera.updateProjectionMatrix();
  };
  const observer = new ResizeObserver(resize);
  observer.observe(container);
  resize();

  let frame = 0;
  let fadeIn = null;
  let snapshotPending = false;
  const loop = () => {
    frame = requestAnimationFrame(loop);
    if (fadeIn) {
      const k = Math.min((performance.now() - fadeIn.start) / 700, 1);
      fadeIn.materials.forEach((m) => {
        m.opacity = 1 - (1 - k) ** 3;
        if (k >= 1) m.transparent = false;
      });
      if (k >= 1) fadeIn = null;
    }
    controls.update();
    renderer.render(scene, camera);
    if (snapshotPending && !fadeIn) {
      // Captured straight after rendering, while the drawing buffer is still intact.
      snapshotPending = false;
      renderer.domElement.toBlob((blob) => blob && onSnapshot(blob), 'image/jpeg', 0.85);
    }
  };
  loop();

  overlay(container, 'Loading mesh…');
  new GLTFLoader().load(
    url,
    (gltf) => {
      // SuGaR bakes lighting into the texture, so show it unlit.
      gltf.scene.traverse((node) => {
        if (node.isMesh) {
          const map = node.material?.map || null;
          if (map) map.colorSpace = THREE.SRGBColorSpace;
          node.material = new THREE.MeshBasicMaterial({ map, color: map ? 0xffffff : 0x9a96b3, side: THREE.DoubleSide });
        }
      });
      scene.add(gltf.scene);
      fadeIn = { start: performance.now(), materials: [] };
      gltf.scene.traverse((node) => {
        if (node.isMesh) {
          node.material.transparent = true;
          node.material.opacity = 0;
          fadeIn.materials.push(node.material);
        }
      });
      const box = new THREE.Box3().setFromObject(gltf.scene);
      const size = box.getSize(new THREE.Vector3()).length() || 1;
      camera.near = size / 2000;
      camera.far = size * 20;
      const v = view || {
        ...FALLBACK_VIEW,
        look_at: box.getCenter(new THREE.Vector3()).toArray(),
        position: box.getCenter(new THREE.Vector3()).add(new THREE.Vector3(0, -0.3, -1).multiplyScalar(size)).toArray(),
      };
      camera.up.fromArray(v.up);
      camera.position.fromArray(v.position);
      controls.target.fromArray(v.look_at);
      camera.updateProjectionMatrix();
      controls.update();
      overlay(container, '');
      if (onSnapshot) setTimeout(() => { snapshotPending = true; }, 900);
    },
    (event) => {
      if (event.total) overlay(container, `Loading mesh… ${Math.round((100 * event.loaded) / event.total)}%`);
    },
    (err) => overlay(container, `Could not load mesh: ${err.message || err}`),
  );

  return async () => {
    cancelAnimationFrame(frame);
    observer.disconnect();
    controls.dispose();
    scene.traverse((node) => {
      if (node.isMesh) {
        node.geometry.dispose();
        node.material.map?.dispose();
        node.material.dispose();
      }
    });
    renderer.dispose();
    container.replaceChildren();
  };
}
