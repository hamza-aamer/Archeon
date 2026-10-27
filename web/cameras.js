// Draws COLMAP's sparse reconstruction: coloured points plus a frustum for every recovered camera pose.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const START = new THREE.Color('#8b5cf6');
const END = new THREE.Color('#22d3ee');

export function mountCameras(container, data, { autoRotate = false, background = 0x07070d } = {}) {
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(background);
  const camera = new THREE.PerspectiveCamera(50, 1, 0.01, 1000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.autoRotate = autoRotate;
  controls.autoRotateSpeed = 0.8;

  // Points
  const positions = new Float32Array(data.points);
  const colors = new Float32Array(data.colors.length);
  for (let i = 0; i < data.colors.length; i += 1) colors[i] = data.colors[i] / 255;
  const cloud = new THREE.BufferGeometry();
  cloud.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  cloud.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  cloud.computeBoundingSphere();
  const radius = cloud.boundingSphere?.radius || 1;

  // Robust scene scale from camera spacing, so frustums stay readable whatever COLMAP's units are.
  const centers = data.cameras.map((c) => new THREE.Vector3(...c.center));
  const look = new THREE.Vector3(...data.view.look_at);
  const spread = centers.length ? centers.reduce((sum, c) => sum + c.distanceTo(look), 0) / centers.length : radius;
  const pointSize = spread * 0.006;
  scene.add(new THREE.Points(cloud, new THREE.PointsMaterial({ size: pointSize, vertexColors: true, sizeAttenuation: true })));

  // Camera frustums + path
  const frustumSize = spread * 0.06;
  const linePositions = [];
  const lineColors = [];
  const color = new THREE.Color();
  data.cameras.forEach((cam, index) => {
    color.copy(START).lerp(END, data.cameras.length > 1 ? index / (data.cameras.length - 1) : 0);
    const c = new THREE.Vector3(...cam.center);
    const f = new THREE.Vector3(...cam.forward).normalize();
    const up = new THREE.Vector3(...cam.up).normalize();
    const right = new THREE.Vector3().crossVectors(f, up).normalize();
    const base = c.clone().addScaledVector(f, frustumSize);
    const w = frustumSize * 0.55;
    const h = frustumSize * 0.4;
    const corners = [[1, 1], [1, -1], [-1, -1], [-1, 1]].map(([sx, sy]) => base.clone()
      .addScaledVector(right, sx * w).addScaledVector(up, sy * h));
    const segments = [];
    corners.forEach((corner, i) => {
      segments.push(c, corner);
      segments.push(corner, corners[(i + 1) % 4]);
    });
    segments.push(corners[0].clone().lerp(corners[3], 0.5), corners[0].clone().lerp(corners[3], 0.5).addScaledVector(up, h * 0.6));
    segments.forEach((p) => { linePositions.push(p.x, p.y, p.z); lineColors.push(color.r, color.g, color.b); });
  });
  for (let i = 1; i < centers.length; i += 1) {
    [centers[i - 1], centers[i]].forEach((p) => { linePositions.push(p.x, p.y, p.z); lineColors.push(0.55, 0.5, 0.75); });
  }
  const lines = new THREE.BufferGeometry();
  lines.setAttribute('position', new THREE.Float32BufferAttribute(linePositions, 3));
  lines.setAttribute('color', new THREE.Float32BufferAttribute(lineColors, 3));
  scene.add(new THREE.LineSegments(lines, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.9 })));

  // Frame everything: step back from the scene centre, roughly above the capture path.
  const up = new THREE.Vector3(...data.view.up).normalize();
  const pathCenter = centers.length ? centers.reduce((a, c) => a.add(c), new THREE.Vector3()).divideScalar(centers.length) : look;
  const away = pathCenter.clone().sub(look);
  if (away.lengthSq() < 1e-8) away.set(0, 0, -1);
  away.normalize();
  camera.up.copy(up);
  camera.position.copy(look).addScaledVector(away, spread * 2.2).addScaledVector(up, spread * 1.2);
  camera.near = spread / 500;
  camera.far = spread * 100;
  controls.target.copy(look);
  controls.update();

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
  const loop = () => {
    frame = requestAnimationFrame(loop);
    controls.update();
    renderer.render(scene, camera);
  };
  loop();

  return async () => {
    cancelAnimationFrame(frame);
    observer.disconnect();
    controls.dispose();
    cloud.dispose();
    lines.dispose();
    renderer.dispose();
    container.replaceChildren();
  };
}
