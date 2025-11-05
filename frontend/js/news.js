// frontend/js/news.js

const STATE = {
  all: [],
  page: 1,
  perPage: 24,
  query: '',
  category: 'Все',
};

// ===== helpers =====
const qs = (s, r = document) => r.querySelector(s);

function getIntParam(name, def = 1) {
  const u = new URL(window.location.href);
  const v = parseInt(u.searchParams.get(name), 10);
  return Number.isFinite(v) && v > 0 ? v : def;
}
function setParam(name, value) {
  const u = new URL(window.location.href);
  if (value == null) u.searchParams.delete(name);
  else u.searchParams.set(name, String(value));
  history.replaceState({}, "", u.toString());
}
function fmtDateTime(input) {
  const d = input instanceof Date ? input : new Date(input || Date.now());
  if (isNaN(d.getTime())) return '';
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const yyyy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, '0');
  const mi = String(d.getMinutes()).padStart(2, '0');
  return `${dd}.${mm}.${yyyy}, ${hh}:${mi}`;
}
function escapeHtml(s = '') {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
function paginate(arr, page, perPage) {
  const total = arr.length;
  const pages = Math.max(1, Math.ceil(total / perPage));
  const clamped = Math.min(Math.max(1, page), pages);
  const start = (clamped - 1) * perPage;
  return { page: clamped, pages, total, items: arr.slice(start, start + perPage) };
}

// простенький хэш для стабильного id по ссылке
function hashId(s = '') {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return 'n' + Math.abs(h).toString(36);
}

// ===== render =====
function renderPager(total, page, perPage, mount) {
  const pages = Math.max(1, Math.ceil(total / perPage));
  if (!mount) return;
  if (pages <= 1) { mount.innerHTML = ""; return; }

  const mkBtn = (label, p, disabled = false, active = false) => {
    if (active) return `<span class="active">${label}</span>`;
    if (disabled) return `<span class="disabled">${label}</span>`;
    return `<a href="#" data-page="${p}">${label}</a>`;
  };

  const parts = [];
  parts.push(mkBtn("«", Math.max(1, page - 3), page <= 1, false));

  const windowSize = 3;
  const start = Math.max(1, page - windowSize);
  const end = Math.min(pages, page + windowSize);

  if (start > 1) parts.push(mkBtn("1", 1, false, page === 1), "<span>…</span>");
  for (let p = start; p <= end; p++) {
    parts.push(mkBtn(String(p), p, false, p === page));
  }
  if (end < pages) parts.push("<span>…</span>", mkBtn(String(pages), pages, false, page === pages));

  parts.push(mkBtn("»", Math.min(pages, page + 1), page >= pages, false));

  mount.innerHTML = parts.join(" ");
  mount.onclick = (e) => {
    const a = e.target.closest("a[data-page]");
    if (!a) return;
    e.preventDefault();
    const next = parseInt(a.dataset.page, 10);
    if (!Number.isFinite(next)) return;
    STATE.page = next;
    setParam("page", next);
    paint();
  };
}

function newsCard(it) {
  const href = `./article.html?id=${encodeURIComponent(it.id)}`; // локальная карточка
  const title = escapeHtml(it.title || '');
  const dateStr = fmtDateTime(it.date);
  const srcName = escapeHtml(it.source || it.domain || 'Источник');

  // короткий анонс (1 предложение)
  let desc = it.summary || '';
  const m = desc.match(/^.*?[.!?](\s|$)/);
  if (m) desc = m[0];
  desc = escapeHtml(desc);

  // картинка или плейсхолдер
 // внутри генерации карточки
const imgSrc = it.image || it.thumbnail || null;
const media = imgSrc
  ? `<img src="${escapeHtml(imgSrc)}" alt="" loading="lazy" referrerpolicy="no-referrer"
          onerror="this.closest('.thumb')?.classList.add('noimg'); this.remove();">`
  : '';
const thumb = `
  <div class="thumb ${imgSrc ? '' : 'noimg'}">
    ${media || `<div class="thumb-ph"></div>`}
  </div>`;

}

function renderList(items, mount) {
  if (!mount) return;
  if (!items.length) {
    mount.innerHTML = `<div class="empty">Пока нет элементов для отображения.</div>`;
    return;
  }
  mount.innerHTML = items.map(newsCard).join("");
}

// ===== filtering & paint =====
function currentList() {
  let arr = STATE.all;

  if (STATE.category && STATE.category !== 'Все') {
    arr = arr.filter(it => (it.category || it.section || '') === STATE.category);
  }
  if (STATE.query) {
    const s = STATE.query.toLowerCase();
    arr = arr.filter(it => (it.title || '').toLowerCase().includes(s));
  }
  return arr;
}

function paint() {
  const list = currentList();
  STATE.page = getIntParam("page", STATE.page || 1);

  const mount = document.querySelector("#news-list");
  const pager = document.querySelector("nav.pager") || document.querySelector("#pager");

  const { items, page, pages, total } = paginate(list, STATE.page, STATE.perPage);
  console.log(`[news] total=${total}, render=${items.length}, page=${page}/${pages}, per=${STATE.perPage}`);

  renderList(items, mount);
  renderPager(total, page, STATE.perPage, pager);
}

// ===== data loading & normalization =====
async function fetchJSONWithFallback(paths) {
  for (const p of paths) {
    try {
      const url = p + (p.includes('?') ? '' : `?v=${Date.now()}`);
      const res = await fetch(url, { cache: 'no-store' });
      if (res.ok) return await res.json();
      console.warn(`[news] ${url} -> HTTP ${res.status}`);
    } catch (e) {
      console.warn(`[news] fetch fail ${p}`, e);
    }
  }
  throw new Error('Не удалось загрузить news.json по ни одному из путей');
}
function possibleNewsPaths() {
  const loc = window.location;
  const path = loc.pathname;
  const base = path.endsWith('/') ? path : path.substring(0, path.lastIndexOf('/') + 1);
  return [
    `${base}data/news.json`,
    `data/news.json`,
    `/data/news.json`
  ];
}

function normalizeItem(it) {
  const dateStr = it.published_at || it.published || it.updated_at || it.created_at || it.date || it.pubDate;
  const date = dateStr ? new Date(dateStr) : new Date();

  const link = it.link || it.url || '#';
  let domain = it.domain;
  try {
    if (!domain && link && link !== '#') domain = new URL(link).hostname;
  } catch (e) { domain = ''; }

  return {
    id: hashId(link),                 // стабильный id по ссылке
    source: it.source || it.site || '',
    title: it.title || '(без заголовка)',
    link,
    summary: it.summary || it.description || '',
    image: it.image || it.thumbnail || null,
    domain,
    date
  };
}

async function loadNews() {
  const data = await fetchJSONWithFallback(possibleNewsPaths());
  if (!Array.isArray(data)) throw new Error('news.json не является массивом');
  console.log(`[news] загружено элементов: ${data.length}`);
  return data.map(normalizeItem).sort((a, b) => b.date - a.date);
}

// ===== init =====
async function initNews() {
  try {
    STATE.perPage = getIntParam('per', STATE.perPage);
    STATE.page = getIntParam('page', STATE.page);

    const items = await loadNews();
    STATE.all = items;

    paint();
  } catch (e) {
    console.error('[news] init error', e);
    const mount = document.querySelector('#news-list') || document.body;
    const div = document.createElement('div');
    div.className = 'empty';
    div.textContent = `Ошибка загрузки новостей: ${e.message}`;
    mount.appendChild(div);
  }
}
document.addEventListener('DOMContentLoaded', initNews);

// ====== LIVE AUTO-REFRESH ======
(function () {
  try {
    const sp = new URL(window.location.href).searchParams;
    const LIVE = sp.get('live');            // ?live=0 — отключить вручную
    if (LIVE === '0') return;               // автообновление выключено только если live=0

    function possibleMetaPaths(){
      const path = location.pathname;
      const base = path.endsWith('/') ? path : path.substring(0, path.lastIndexOf('/') + 1);
      return [
        `${base}data/news_meta.json`,
        `data/news_meta.json`,
        `/data/news_meta.json`
      ];
    }
    async function fetchMeta(){
      return await fetchJSONWithFallback(possibleMetaPaths());
    }

    let lastUpdated = null;

    async function checkAndRefresh(){
      try{
        const meta = await fetchMeta();
        // отладочный лог, чтобы видеть пульс в консоли/Network:
        console.log('[live] poll meta', meta?.updated_at);

        if (!meta || !meta.updated_at) return;
        if (lastUpdated === null){ lastUpdated = meta.updated_at; return; }

        if (meta.updated_at !== lastUpdated){
          lastUpdated = meta.updated_at;
          console.log('[live] detected update:', lastUpdated);

          const data = await fetchJSONWithFallback(possibleNewsPaths());
          if (Array.isArray(data)){
            const normalized = data.map(normalizeItem).sort((a,b)=>b.date - a.date);
            STATE.all = normalized;
            paint();
          }
        }
      }catch(e){
        console.warn('[live] update check failed', e);
      }
    }

    // первая проверка и интервал
    checkAndRefresh();
    const EVERY_SEC = Number(sp.get('every')) || 5*60;  // ?every=30
    setInterval(checkAndRefresh, EVERY_SEC * 1000);
  } catch(e){
    console.warn('[live] init error', e);
  }
})();

