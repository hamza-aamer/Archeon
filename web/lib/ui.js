// Toasts and modal dialogs.
import { esc } from './util.js';
import { icon } from './icons.js';

let toastHost = null;

export function toast(message, kind = 'info') {
  if (!toastHost) {
    toastHost = document.createElement('div');
    toastHost.className = 'toasts';
    document.body.appendChild(toastHost);
  }
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.innerHTML = `${icon(kind === 'error' ? 'alert' : kind === 'success' ? 'check' : 'info', 16)}<span>${esc(message)}</span>`;
  toastHost.appendChild(el);
  requestAnimationFrame(() => el.classList.add('show'));
  setTimeout(() => {
    el.classList.remove('show');
    setTimeout(() => el.remove(), 300);
  }, kind === 'error' ? 6000 : 3500);
}

function openDialog(html, onReady) {
  return new Promise((resolve) => {
    const dialog = document.createElement('dialog');
    dialog.className = 'modal';
    dialog.innerHTML = html;
    document.body.appendChild(dialog);
    const finish = (value) => {
      dialog.close();
      dialog.remove();
      resolve(value);
    };
    dialog.addEventListener('cancel', (e) => { e.preventDefault(); finish(null); });
    dialog.addEventListener('click', (e) => { if (e.target === dialog) finish(null); });
    onReady(dialog, finish);
    dialog.showModal();
  });
}

export function confirmDialog({ title, body, confirm = 'Confirm', danger = false }) {
  return openDialog(`
    <form method="dialog" class="modal-body">
      <h2>${esc(title)}</h2>
      <p class="muted">${esc(body)}</p>
      <div class="modal-actions">
        <button class="button ghost" value="cancel" type="button" data-cancel>Cancel</button>
        <button class="button ${danger ? 'danger-solid' : 'primary'}" value="ok" type="submit">${esc(confirm)}</button>
      </div>
    </form>`, (dialog, finish) => {
    dialog.querySelector('[data-cancel]').addEventListener('click', () => finish(false));
    dialog.querySelector('form').addEventListener('submit', (e) => { e.preventDefault(); finish(true); });
  }).then((value) => value === true);
}

export function promptDialog({ title, label, value = '', confirm = 'Save' }) {
  return openDialog(`
    <form method="dialog" class="modal-body">
      <h2>${esc(title)}</h2>
      <label class="field"><span class="label">${esc(label)}</span>
        <input type="text" name="value" maxlength="120" value="${esc(value)}" required autocomplete="off"></label>
      <div class="modal-actions">
        <button class="button ghost" type="button" data-cancel>Cancel</button>
        <button class="button primary" type="submit">${esc(confirm)}</button>
      </div>
    </form>`, (dialog, finish) => {
    const input = dialog.querySelector('input');
    setTimeout(() => { input.focus(); input.select(); }, 0);
    dialog.querySelector('[data-cancel]').addEventListener('click', () => finish(null));
    dialog.querySelector('form').addEventListener('submit', (e) => {
      e.preventDefault();
      finish(input.value.trim() || null);
    });
  });
}

/** Tiny SVG sparkline for 0-100 series. */
export function sparkline(values, { width = 220, height = 44, max = 100 } = {}) {
  if (!values.length) return `<svg class="spark" width="${width}" height="${height}"></svg>`;
  const step = width / Math.max(values.length - 1, 1);
  const pts = values.map((v, i) => `${(i * step).toFixed(1)},${(height - 2 - ((v || 0) / max) * (height - 4)).toFixed(1)}`);
  return `<svg class="spark" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" width="100%" height="${height}">
    <defs><linearGradient id="sparkfill" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="var(--accent)" stop-opacity=".35"/><stop offset="1" stop-color="var(--accent)" stop-opacity="0"/>
    </linearGradient></defs>
    <polygon points="0,${height} ${pts.join(' ')} ${((values.length - 1) * step).toFixed(1)},${height}" fill="url(#sparkfill)"/>
    <polyline points="${pts.join(' ')}" fill="none" stroke="var(--accent-strong)" stroke-width="1.6" vector-effect="non-scaling-stroke"/>
  </svg>`;
}
