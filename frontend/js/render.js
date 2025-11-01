import {qs} from './utils.js';

// ===== настройки =====
const PER_PAGE = 10;

// внутреннее состояние для повторной отрисовки
let LAST_LIST = [];
let LAST_MOUNT = null;

// ===== утилиты =====
function formatDateTime(input){
  const d = new Date(input || Date.now());
  if (isNaN(d.getTime())) return '';
  const dd = String(d.getDate()).padStart(2,'0');
  const mm = String(d.getMonth()+1).padStart(2,'0');
  const yyyy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2,'0');
  const mi = String(d.getMinutes()).padStart(2,'0');
  return `${dd}.${mm}.${yyyy}, ${hh}:${mi}`;
}

function summarizeOneSentence(text){
  const t = String(text||"")
    .replace(/\u00A0/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if(!t) return "";
  const m = t.match(/^[\s\S]*?[\.!\?](?=(\s|$))/);
  const s = m ? m[0] : t;
  return s.trim();
}

function getIntParam(name, def=1){
  const u = new URL(window.location.href);
  const v = parseInt(u.searchParams.get(name) || '', 10);
  return Number.isFinite(v) && v > 0 ? v : def;
}
function setParam(name, value){
  const u = new URL(window.location.href);
  if (value == null) u.searchParams.delete(name);
  else u.searchParams.set(name, String(value));
  history.replaceState({}, "", u.toString());
}

// ===== пагинация =====
function paginate(arr, page, perPage){
  const total = arr.length;
  const pages = Math.max(1, Math.ceil(total / perPage));
  const clamped = Math.min(Math.max(1, page), pages);
  const start = (clamped - 1) * perPage;
  return { page: clamped, pages, total, items: arr.slice(start, start + perPage) };
}

// ===== карточка =====
function NewsListItem(it){
  const hasImg = !!it.image;
  const d = new Date(it.published_at || it.updated_at || it.date || Date.now());
  const dateStr = isNaN(d.getTime()) ? '—' : formatDateTime(d);
  const url = `article.html?id=${encodeURIComponent(it.id)}`;

  return `
  <a class="${hasImg ? 'news-row has-thumb' : 'news-row'}" href="${url}">
    ${hasImg ? `<div class="thumb"><img src="${it.image}" alt="${it.title}"></div>` : ``}
    <div class="row-body">
      <div class="row-title">${it.title}</div>
      <div class="row-meta">
        <span class="badge">${it.category || "Новости"}</span>
        ${it.source?.name ? `<span class="dot"></span><span>${it.source.name}</span>` : ``}
        <span class="dot"></span><span class="date">${dateStr}</span>
      </div>
      ${it.summary ? `<p class="row-summary">${summarizeOneSentence(it.summary)}</p>` : ``}
    </div>
  </a>`;
}

// ===== рендер пагинатора (AJAX, без перезагрузки; номера через запятую) =====
function renderPager(total, page, perPage, mount){
  const pages = Math.max(1, Math.ceil(total / perPage));
  if (!mount) return;
  if (pages <= 1){ mount.innerHTML = ""; return; }

  const numberParts = [];

  const addBtn = (p) => {
    if (p === page){
      numberParts.push(`<span class="active">${p}</span>`);
    } else {
      numberParts.push(`<a href="#" data-page="${p}">${p}</a>`);
    }
  };

  const windowSize = 3;
  const start = Math.max(1, page - windowSize);
  const end = Math.min(pages, page + windowSize);

  if (start > 1){
    addBtn(1);
    numberParts.push('…');
  }
  for (let p = start; p <= end; p++){
    addBtn(p);
  }
  if (end < pages){
    numberParts.push('…');
    addBtn(pages);
  }

  const numbersHtml = numberParts.join(', '); // ← запятые между номерами

  mount.innerHTML = `
    <a href="#" data-page="${Math.max(1, page-1)}" class="${page<=1?'disabled':''}">«</a>
    ${numbersHtml}
    <a href="#" data-page="${Math.min(pages, page+1)}" class="${page>=pages?'disabled':''}">»</a>
  `;

  // перехватываем клики — без перезагрузки
  mount.onclick = (e)=>{
    const a = e.target.closest('a[data-page]');
    if (!a) return;
    e.preventDefault();
    const next = parseInt(a.dataset.page, 10);
    if (!Number.isFinite(next)) return;
    // обновляем URL (?page=...) без перезагрузки
    setParam('page', next);
    // моментально перерисовываем
    doRender();
    // плавно скроллим к началу списка
    const top = document.getElementById('news-list');
    top?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
}

// ===== базовая отрисовка на основе LAST_LIST =====
function doRender(){
  if (!LAST_MOUNT) return;
  const pageFromUrl = getIntParam('page', 1);
  const {items, page, pages, total} = paginate(LAST_LIST || [], pageFromUrl, PER_PAGE);

  LAST_MOUNT.innerHTML = items.map(NewsListItem).join('');

  const pager = document.getElementById('pager');
  if (pager) renderPager(total, page, PER_PAGE, pager);
}

// ===== публичные API =====
export function renderNews(list, mount){
  LAST_LIST = Array.isArray(list) ? list : [];
  LAST_MOUNT = mount || qs('#news-list');
  doRender();
}

export function renderChips(options, mount, activeValue, onClick){
  mount.innerHTML = options.map(v => `<div class="chip ${v===activeValue?'active':''}" data-v="${v}">${v}</div>`).join('');
  mount.addEventListener('click', (e)=>{
    const el = e.target.closest('.chip'); if(!el) return;
    onClick?.(el.dataset.v);
  }, {once:true});
}

export function renderTagsTop(tags, mount){
  mount.innerHTML = tags.map(t => `<div class="chip">${t}</div>`).join('');
}

// совместимость со старым событием — больше не требуется
window.addEventListener('news:rerender', ()=>{});
