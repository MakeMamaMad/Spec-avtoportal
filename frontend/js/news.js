// ---------- Константы и состояние ----------
const PAGE_SIZE = 18;
const NEWS_URL = 'data/news.json'; // относительный путь для GitHub Pages
const BLOCKED = ['tass.ru', 'www.tass.ru']; // жёсткий фильтр TASS

const STATE = {
  all: [],
  page: 1,
};

// ---------- Утилиты ----------
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const byDateDesc = (a, b) => (new Date(b.date || 0)) - (new Date(a.date || 0));

function ensureContainers() {
  let grid = $('#news-list') || $('#news-grid');
  if (!grid) {
    grid = document.createElement('div');
    grid.id = 'news-list';
    document.body.appendChild(grid);
  }
  grid.classList.add('news-grid');

  let pager = $('#pager') || $('#paginator');
  if (!pager) {
    pager = document.createElement('nav');
    pager.id = 'pager';
    document.body.appendChild(pager);
  }
  pager.classList.add('pager');

  // инъекция минимальных стилей, если их нет
  if (!$('#__news_inline_styles')) {
    const css = `
      .news-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px;margin:16px 0 24px}
      .card{display:flex;flex-direction:column;gap:8px;padding:12px;border-radius:16px;background:#fff;box-shadow:0 1px 4px rgba(0,0,0,.06)}
      .card .cover{width:100%;height:140px;border-radius:12px;overflow:hidden;background:#f2f4f7;display:flex;align-items:center;justify-content:center}
      .card .cover img{width:100%;height:100%;object-fit:cover;display:block}
      .meta{color:#6b7280;font-size:12px;display:flex;gap:6px;align-items:center}
      .title{font-size:16px;line-height:1.25;font-weight:700;margin:0}
      .summary{color:#374151;font-size:14px;line-height:1.45;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}
      .pager{display:flex;gap:8px;margin:28px 0 8px;flex-wrap:wrap;justify-content:center}
      .pager .btn{padding:8px 12px;border-radius:10px;border:1px solid #e5e7eb;background:#fff;cursor:pointer}
      .pager .btn[disabled]{opacity:.5;cursor:not-allowed}
      .pager .num{padding:8px 10px;border-radius:10px;border:1px solid #e5e7eb;background:#fff;min-width:36px;text-align:center}
      .pager .num.active{background:#111827;color:#fff;border-color:#111827}
      @media (prefers-color-scheme: dark){
        .card{background:#111318;border:1px solid #222}
        .meta{color:#9aa0a6}
        .summary{color:#cbd5e1}
        .pager .btn,.pager .num{background:#111318;border-color:#222;color:#e5e7eb}
        .pager .num.active{background:#2563eb;border-color:#2563eb}
      }
    `.trim();
    const style = document.createElement('style');
    style.id = '__news_inline_styles';
    style.textContent = css;
    document.head.appendChild(style);
  }

  return { grid, pager };
}

function fmtDate(iso) {
  const d = new Date(iso || Date.now());
  if (Number.isNaN(+d)) return '';
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getDate())}.${p(d.getMonth()+1)}.${d.getFullYear()}, ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function stripHTML(s='') {
  const el = document.createElement('div');
  el.innerHTML = s;
  return (el.textContent || '').trim();
}

function safeSummary(item){
  // пытаемся взять summary/description/lead, потом fallback на первые строки текста
  const cand = item.summary || item.description || item.lead || item.text || '';
  return stripHTML(cand);
}

function cardHTML(item, idx){
  const cover = item.image ? `<div class="cover"><img src="${item.image}" alt=""></div>` : `<div class="cover"></div>`;
  const meta = `
    <div class="meta">
      ${item.domain ? `<span>${item.domain}</span>` : ``}
      ${item.date ? `<span>•</span><time>${fmtDate(item.date)}</time>` : ``}
    </div>
  `;
  const sum = safeSummary(item);

  // Сохраняем выбранную новость в localStorage, чтобы статья смогла её получить в любом случае
  const articleHref = `article.html?id=${encodeURIComponent(item.id ?? idx)}`;
  return `
  <article class="card">
    ${cover}
    ${meta}
    <h3 class="title"><a class="go-article" data-idx="${idx}" href="${articleHref}">${item.title || ''}</a></h3>
    ${sum ? `<p class="summary">${sum}</p>` : ``}
  </article>`;
}

// ---------- Загрузка и рендер ----------
async function loadAll(){
  const res = await fetch(NEWS_URL, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Failed to load ${NEWS_URL}: ${res.status}`);
  let items = await res.json();

  // Жёсткий фильтр TASS по домену и URL
  items = (Array.isArray(items) ? items : []).filter(n => {
    const d = (n?.domain || '').toLowerCase();
    const u = (n?.url || '').toLowerCase();
    return !BLOCKED.some(b => d.includes(b) || u.includes(b));
  });

  // сортировка по дате
  items.sort(byDateDesc);
  return items;
}

function renderPage(){
  const { grid, pager } = ensureContainers();
  const start = (STATE.page - 1) * PAGE_SIZE;
  const slice = STATE.all.slice(start, start + PAGE_SIZE);

  // сетка
  grid.innerHTML = slice.map((n, i) => cardHTML(n, start + i)).join('');

  // обработчик клика — кладём выбранную новость в localStorage (на всякий случай)
  $$('.go-article', grid).forEach(a => {
    a.addEventListener('click', (e) => {
      const idx = Number(e.currentTarget.getAttribute('data-idx'));
      const item = STATE.all[idx];
      try { localStorage.setItem('currentArticle', JSON.stringify(item)); } catch {}
    });
  });

  // пагинация
  const total = Math.max(1, Math.ceil(STATE.all.length / PAGE_SIZE));
  const btn = (label, go, disabled) =>
    `<button class="btn" ${disabled ? 'disabled' : ''} data-go="${go}">${label}</button>`;
  let nums = '';
  for(let i=1;i<=total;i++){
    nums += `<button class="num ${i===STATE.page?'active':''}" data-page="${i}">${i}</button>`;
    if (i>=10 && i<total-1) { // не распухать список
      nums += `<span class="num" disabled>…</span><button class="num" data-page="${total}">${total}</button>`;
      break;
    }
  }
  pager.innerHTML = [
    btn('«', 1, STATE.page===1),
    btn('‹', STATE.page-1, STATE.page===1),
    nums,
    btn('›', STATE.page+1, STATE.page===total),
    btn('»', total, STATE.page===total),
  ].join('');

  pager.onclick = (e)=>{
    const go = e.target.getAttribute('data-go');
    const pg = e.target.getAttribute('data-page');
    if (go) {
      STATE.page = Math.max(1, Math.min(Number(go), Math.ceil(STATE.all.length/PAGE_SIZE)));
      renderPage();
    } else if (pg) {
      STATE.page = Number(pg);
      renderPage();
    }
  };
}

async function main(){
  try{
    STATE.all = await loadAll();
    // восстановление страницы из query ?page=
    const url = new URL(location.href);
    const qp = Number(url.searchParams.get('page') || '1');
    if (qp > 0) STATE.page = qp;
    renderPage();
  }catch(err){
    console.error(err);
    const { grid } = ensureContainers();
    grid.innerHTML = `<div style="padding:16px">Не удалось загрузить новости.</div>`;
  }
}

// Старт
document.addEventListener('DOMContentLoaded', main);
