// frontend/js/news.js  — robust loader + rendering with images + article view links

const STATE = {
  all: [],
  page: 1,
  perPage: 24,
  query: '',
  category: 'Все',
};

// ---- helpers ----
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

// ---- robust fetch with fallbacks ----
function basePath(){
  const path = location.pathname;
  return path.endsWith('/') ? path : path.substring(0, path.lastIndexOf('/') + 1);
}
function possibleNewsPaths(){
  const b = basePath();
  return [
    `${b}data/news.json`,
    `data/news.json`,
    `/data/news.json`,
    `${b}../data/news.json`,
    `../data/news.json`,
  ];
}
function possibleMetaPaths(){
  const b = basePath();
  return [
    `${b}data/news_meta.json`,
    `data/news_meta.json`,
    `/data/news_meta.json`,
    `${b}../data/news_meta.json`,
    `../data/news_meta.json`,
  ];
}
async function fetchJSONWithFallback(paths){
  let lastErr;
  for (const p of paths){
    try{
      const res = await fetch(p + `?t=${Date.now()}`, {cache:'no-store'});
      if (res.ok) return await res.json();
      lastErr = new Error(res.status + ' ' + res.statusText);
    }catch(e){ lastErr = e; }
  }
  console.warn('fetchJSONWithFallback failed', lastErr);
  return null;
}

// ---- normalization ----
function normalizeItem(it){
  const dateStr = it.published_at || it.published || it.updated_at || it.created_at || it.date || it.pubDate;
  const date = dateStr ? new Date(dateStr) : new Date();
  const id = it.id || (it.link ? btoa(unescape(encodeURIComponent(it.link))).slice(0,16) : Math.random().toString(36).slice(2,18));
  return {
    id,
    source: it.source || it.site || '',
    title: it.title || '(без заголовка)',
    link: it.link || it.url || '#',
    summary: it.summary || it.description || '',
    content_html: it.content_html || '',
    image: it.image || it.thumbnail || null,
    domain: it.domain || (it.link ? new URL(it.link).hostname : ''),
    published_at: dateStr,
    date,
  };
}

// ---- rendering ----
function newsCard(it){
 const href = `./article.html?id=${encodeURIComponent(it.id)}&u=${encodeURIComponent(it.link||'')}`;
  const title = escapeHtml(it.title || '');
  const dateStr = fmtDateTime(it.published_at);
  const srcName = escapeHtml(it.source || (it.domain || 'Источник'));
  const desc = escapeHtml((it.summary || '').trim());

  const img = it.image ? `<img class="thumb" src="${it.image}" alt="" loading="lazy"/>`
                       : `<div class="thumb placeholder"></div>`;

  return `
    <a class="card" href="${href}" data-id="${it.id}">
      <div class="thumb-wrap">${img}</div>
      <div class="body">
        <h3>${title}</h3>
        <div class="card-meta"><span>${srcName}</span>${dateStr?`<span> • ${dateStr}</span>`:''}</div>
        ${desc ? `<p>${desc}</p>` : ``}
      </div>
    </a>
  `;
}

function renderList(items, mount){
  if (!mount) return;
  mount.innerHTML = items.map(newsCard).join("");
}

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
    history.replaceState({}, "", `?page=${next}`);
    paint();
  };
}

// ---- state & paint ----
function currentList(){
  let arr = STATE.all;
  // category filter: reserved
  if (STATE.query){
    const s = STATE.query.toLowerCase();
    arr = arr.filter(it => (it.title || '').toLowerCase().includes(s));
  }
  return arr;
}

function paint(){
  const list = currentList();
  STATE.page = getIntParam("page", STATE.page || 1);
  const mount = qs("#news-list") || qs("#news") || (()=>{
    const d = document.createElement('div'); d.id='news-list'; document.body.appendChild(d); return d;
  })();
  const pager = qs("#pager") || (()=>{
    const n = document.createElement('nav'); n.id='pager'; document.body.appendChild(n); return n;
  })();

  const {items, page, pages, total} = paginate(list, STATE.page, STATE.perPage);
  console.log(`[news] total=${total}, render=${items.length}, page=${page}/${pages}`);
  renderList(items, mount);
  renderPager(total, page, STATE.perPage, pager);
}

// ---- boot: load news ----
async function loadNews(){
  const data = await fetchJSONWithFallback(possibleNewsPaths());
  if (!Array.isArray(data)) throw new Error("news.json not loaded");
  const norm = data.map(normalizeItem).sort((a,b)=>b.date - a.date);
  STATE.all = norm;
  console.log('[news] loaded items:', norm.length);
  paint();
}

// ---- LIVE AUTO-REFRESH (always on unless ?live=0) ----
(function(){
  try{
    const sp = new URL(window.location.href).searchParams;
    const liveParam = sp.get('live');
    if (liveParam === '0') return;

    async function checkAndRefresh(){
      try{
        const meta = await fetchJSONWithFallback(possibleMetaPaths());
        console.log('[live] poll meta', meta && meta.updated_at);
        if (!meta || !meta.updated_at) return;
        if (!window.__LAST_META_TS){
          window.__LAST_META_TS = meta.updated_at;
          return;
        }
        if (window.__LAST_META_TS !== meta.updated_at){
          window.__LAST_META_TS = meta.updated_at;
          const data = await fetchJSONWithFallback(possibleNewsPaths());
          if (Array.isArray(data)){
            STATE.all = data.map(normalizeItem).sort((a,b)=>b.date - a.date);
            paint();
            const box = document.getElementById('live-indicator') || (()=>{
              const d = document.createElement('div');
              d.id='live-indicator';
              d.style.cssText='position:fixed;right:12px;bottom:12px;padding:8px 10px;border-radius:10px;background:#111827;color:#fff;font:12px/1.2 system-ui;z-index:9999;opacity:.9;display:block';
              document.body.appendChild(d);
              return d;
            })();
            box.textContent = 'Лента обновлена — ' + new Date(meta.updated_at).toLocaleTimeString();
            clearTimeout(window.__live_to);
            window.__live_to = setTimeout(()=>{ box.style.display='none'; }, 5000);
          }
        }
      }catch(e){ console.warn('[live] update check failed', e); }
    }

    checkAndRefresh();
    const EVERY_SEC = Number(sp.get('every')) || 5*60;
    setInterval(checkAndRefresh, EVERY_SEC*1000);
  }catch(e){ console.warn('[live] init error', e); }
})();

// start
loadNews().catch(err => console.error('NEWS load error', err));
