// news.js  (v12)

const FEED_URL = 'frontend/data/news.json';
const BLOCKED = ['tass.ru', 'www.tass.ru', 'tass.com', 'tass'];

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

function stripHTML(s = '') {
  const el = document.createElement('div');
  el.innerHTML = s;
  return (el.textContent || '').trim();
}
function fmtDate(iso) {
  const d = new Date(iso || Date.now());
  if (Number.isNaN(+d)) return '';
  const p = n => String(n).padStart(2, '0');
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()}, ${p(d.getHours())}:${p(d.getMinutes())}`;
}
function hostname(u = '') {
  try { return new URL(u).hostname; } catch { return ''; }
}
function pickImage(it) {
  if (!it) return '';
  const cand = it.image || it.cover || it.img || (Array.isArray(it.images) ? it.images[0] : '');
  return (typeof cand === 'string' && cand.trim()) ? cand.trim() : '';
}
function placeholderFor(it) {
  const domain = (it?.domain || 'news').replace(/^https?:\/\//, '').split('/')[0];
  const label = domain.length > 18 ? domain.slice(0, 18) + '…' : domain;
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360'>
    <rect width='100%' height='100%' fill='#eef2f7'/>
    <text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle'
      font-family='Inter,system-ui,Segoe UI,Roboto,Arial' font-size='28' fill='#667085'>${label}</text>
  </svg>`;
  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
}
function isBlocked(it) {
  const d = String(it?.domain || '').toLowerCase().trim();
  const u = String(it?.url || '').toLowerCase().trim();
  return BLOCKED.some(b => d.includes(b) || u.includes(b));
}

function cardTemplate(it, idx) {
  const img = pickImage(it);
  const domain = it.domain || hostname(it.url) || '';
  const date = it.date ? fmtDate(it.date) : '';
  const lead = it.summary ? stripHTML(it.summary) : '';

  const cover = img
    ? `<img class="card__img" src="${img}" loading="lazy" decoding="async" referrerpolicy="no-referrer"
         onerror="this.onerror=null;this.src='${placeholderFor(it)}'">`
    : `<img class="card__img" src="${placeholderFor(it)}" alt="">`;

  return `
  <article class="card" data-index="${idx}">
    <div class="card__cover">${cover}</div>
    <div class="card__body">
      <h3 class="card__title">${stripHTML(it.title || '')}</h3>
      <div class="card__meta">
        ${domain ? `<span>${domain}</span>` : ''}
        ${date ? `<span>•</span><time>${date}</time>` : ''}
      </div>
      ${lead ? `<p class="card__lead">${lead}</p>` : ''}
    </div>
  </article>`;
}

function paint(arr) {
  const mount = $('#feed') || document.body;
  if (!Array.isArray(arr) || !arr.length) {
    mount.innerHTML = '<p style="opacity:.6">Лента пуста.</p>';
    return;
  }
  const html = arr.map(cardTemplate).join('');
  mount.innerHTML = html;

  // клик по карточке => article.html
  $$('.card', mount).forEach(el => {
    el.addEventListener('click', () => {
      const idx = Number(el.dataset.index || -1);
      if (!Number.isFinite(idx) || !arr[idx]) return;
      try { localStorage.setItem('currentArticle', JSON.stringify(arr[idx])); } catch {}
      location.href = `article.html?id=${idx}`;
    });
  });
}

async function loadFeed() {
  const url = `${FEED_URL}?t=${Date.now()}`; // no-cache
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

(async () => {
  try {
    const raw = await loadFeed();
    // фильтруем заблокированные
    const items = (Array.isArray(raw) ? raw : []).filter(x => !isBlocked(x));
    window.__ALL_NEWS__ = items;
    console.log('NEWS LOADED (main.js):', items.length);
    paint(items);
  } catch (e) {
    console.error('load feed failed:', e);
    paint([]);
  }

  // восстановление из BFCache
  window.addEventListener('pageshow', ev => {
    if (ev.persisted && Array.isArray(window.__ALL_NEWS__)) {
      console.debug('pageshow (persisted) → restore feed');
      paint(window.__ALL_NEWS__);
    }
  });
})();
