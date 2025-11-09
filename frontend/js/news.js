// frontend/js/news.js

// ===== Глобальное состояние =====
const STATE = {
  all: [],
  page: 1,
  perPage: 24,     // можно менять через ?per=48
  query: '',
  category: 'Все',
};

// ===== helpers =====
const qs = (s, r=document)=>r.querySelector(s);

function getIntParam(name, def=1){
  const u = new URL(window.location.href);
  const v = parseInt(u.searchParams.get(name), 10);
  return Number.isFinite(v) && v > 0 ? v : def;
}
function setParam(name, value){
  const u = new URL(window.location.href);
  if (value == null) u.searchParams.delete(name);
  else u.searchParams.set(name, String(value));
  history.replaceState({}, "", u.toString());
}
function fmtDateTime(input){
  const d = new Date(input || Date.now());
  if (isNaN(d.getTime())) return '';
  const dd = String(d.getDate()).padStart(2,'0');
  const mm = String(d.getMonth()+1).padStart(2,'0');
  const yyyy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2,'0');
  const mi = String(d.getMinutes()).padStart(2,'0');
  return `${dd}.${mm}.${yyyy}, ${hh}:${mi}`;
}
function escapeHtml(s=''){
  return String(s)
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;')
    .replace(/'/g,'&#39;');
}

function paginate(arr, page, perPage){
  const total = arr.length;
  const pages = Math.max(1, Math.ceil(total / perPage));
  const clamped = Math.min(Math.max(1, page), pages);
  const start = (clamped - 1) * perPage;
  return { page: clamped, pages, total, items: arr.slice(start, start + perPage) };
}

// ==== helpers для текста (новое) ====
function htmlToText(html='') {
  try {
    const el = document.createElement('div');
    el.innerHTML = html;
    return el.textContent || el.innerText || '';
  } catch {
    return html;
  }
}

function makeSnippet(item, maxChars = 700) {
  // Предпочитаем полноценный контент
  let raw = item.content_html ? htmlToText(item.content_html) : (item.summary || '');
  raw = (raw || '').replace(/\s+/g, ' ').trim();
  if (!raw) return '';

  if (raw.length > maxChars) {
    // Ищем естественный конец предложения недалеко после maxChars
    const zone = raw.slice(0, maxChars + 120);
    const endRe = /[.!?](?:\s|$)/g;
    let cutAt = maxChars;
    let m;
    while ((m = endRe.exec(zone)) !== null) {
      cutAt = m.index + 1;
    }
    // чтобы не обрезать слишком рано
    if (cutAt < 320) cutAt = maxChars;
    raw = zone.slice(0, cutAt).trim();
    if (!/[.!?]$/.test(raw)) raw += '…';
  }
  return raw;
}

// ====== Рендер ======
function renderPager(total, page, perPage, mount){
  const pages = Math.max(1, Math.ceil(total / perPage));
  if (!mount) return;
  if (pages <= 1){ mount.innerHTML = ""; return; }

  const mkBtn = (label, p, disabled=false, active=false) => {
    if (active) return `<span class="active">${label}</span>`;
    if (disabled) return `<span class="disabled">${label}</span>`;
    return `<a href="#" data-page="${p}">${label}</a>`;
  };

  const parts = [];
  parts.push(mkBtn("«", Math.max(1, page-3), page<=1, false));

  const windowSize = 3;
  const start = Math.max(1, page - windowSize);
  const end = Math.min(pages, page + windowSize);

  if (start > 1) parts.push(mkBtn("1", 1, false, page===1), "<span>…</span>");
  for (let p=start; p<=end; p++){
    parts.push(mkBtn(String(p), p, false, p===page));
  }
  if (end < pages) parts.push("<span>…</span>", mkBtn(String(pages), pages, false, page===pages));

  parts.push(mkBtn("»", Math.min(pages, page+1), page>=pages, false));

  mount.innerHTML = parts.join(" ");
  mount.onclick = (e)=>{
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

function newsCard(it){
  const href = `./article.html?id=${encodeURIComponent(it.id||'')}`;
  const title = escapeHtml(it.title || '');
  const dateStr = fmtDateTime(it.published_at);
  const srcName = escapeHtml(it.domain || (it.source && it.source.name) || 'Источник');

  const snippet = escapeHtml(makeSnippet(it)); // длинный тизер

  return `
    <a class="card" href="${href}">
      <div class="body">
        <h3>${title}</h3>
        <div class="card-meta"><span>${srcName}</span>${dateStr?`<span> • ${dateStr}</span>`:''}</div>
        ${snippet ? `<p class="teaser clamp-6">${snippet}</p>` : ``}
      </div>
    </a>
  `;
}

function renderList(items, mount){
  if (!mount) return;
  mount.innerHTML = items.map(newsCard).join("");
}

// ===== Фильтрация + отрисовка =====
function currentList(){
  let arr = STATE.all;

  if (STATE.category && STATE.category !== 'Все'){
    arr = arr.filter(it => (it.category || it.section || '') === STATE.category);
  }

  if (STATE.query){
    const s = STATE.query.toLowerCase();
    arr = arr.filter(it => (it.title || '').toLowerCase().includes(s));
  }

  return arr;
}

function paint(){
  const list = currentList();
  STATE.page = getIntParam("page", STATE.page || 1);

  // поддержка #news-list (основной) и запасного #news
  let mount = qs("#news-list") || qs("#news");
  if (!mount) {
    mount = document.createElement('div');
    mount.id = "news";
    document.body.appendChild(mount);
    console.warn("[news] контейнер не найден — создан #news");
  }
  const pager = qs("#pager");

  const {items, page, pages, total} = paginate(list, STATE.page, STATE.perPage);
  console.log(`[news] total=${total}, render=${items.length}, page=${page}/${pages}, per=${STATE.perPage}`);

  renderList(items, mount);
  renderPager(total, page, STATE.perPage, pager);
}

// ===== Загрузка ленты =====
async function loadNews() {
  const url = `data/news.json?v=${Date.now()}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`news.json ${res.status}`);
  const raw = await res.json();
  return raw.map(normalizeItem).sort((a, b) => b.date - a.date);
}

function normalizeItem(it) {
  const dateStr = it.published_at || it.published || it.updated_at || it.created_at || it.date || it.pubDate;
  const date = dateStr ? new Date(dateStr) : new Date();
  return {
    id: it.id || '',
    source: it.source || it.site || '',
    title: it.title || '(без заголовка)',
    link: it.link || it.url || '#',
    summary: it.summary || it.description || '',
    content_html: it.content_html || '',      // <--- используем для длинного тизера
    image: it.image || it.thumbnail || null,
    domain: it.domain || (it.link ? new URL(it.link).hostname : ''),
    date
  };
}

// ===== Инициализация =====
(async function boot(){
  try {
    const sp = new URL(window.location.href).searchParams;
    const per = parseInt(sp.get('per') || '', 10);
    if (Number.isFinite(per) && per > 0) STATE.perPage = per;

    const news = await loadNews();
    console.log("NEWS LOADED:", news?.length, news);
    STATE.all = news;
    paint();
  } catch (e) {
    console.error(e);
  }
})();

// ===== LIVE автообновление (по желанию) =====
(function() {
  try {
    const sp = new URL(window.location.href).searchParams;
    if (sp.get('live') === '1') {
      const META_URL = 'data/news_meta.json';
      let lastUpdated = null;

      async function checkAndRefresh() {
        try {
          const resp = await fetch(META_URL + '?t=' + Date.now(), { cache: 'no-store' });
          if (!resp.ok) return;
          const meta = await resp.json();
          console.log('[live] poll meta', meta?.updated_at);
          if (meta && meta.updated_at && meta.updated_at !== lastUpdated) {
            lastUpdated = meta.updated_at;
            const newsResp = await fetch('data/news.json?t=' + Date.now(), { cache: 'no-store' });
            const data = await newsResp.json();
            if (Array.isArray(data)) {
              STATE.all = data.map(normalizeItem).sort((a,b)=>b.date-a.date);
              paint();
            }
          }
        } catch (e) {
          console.warn('[live] update check failed', e);
        }
      }

      checkAndRefresh();
      setInterval(checkAndRefresh, 5 * 60 * 1000);
    }
  } catch (e) {
    console.warn('[live] init error', e);
  }
})();
