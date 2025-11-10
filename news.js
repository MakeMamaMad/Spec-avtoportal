/* frontend/js/news.js
 * Рендер ленты новостей (карточки на главной) + пагинация.
 * Ожидает, что STATE.all уже заполнен в main.js и отсортирован по дате.
 */
const BLOCKED_DOMAINS = new Set(['tass.ru', 'www.tass.ru']);

  // <-- фильтруем ТАСС здес
(function () {
  'use strict';

  // ---------- helpers ----------
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  function ensureContainer() {
    // Нужны контейнеры:
    //   <div id="news-grid"></div>
    //   <div id="paginator"></div>
    // Если их нет — создадим в <main> или <body>.
    let grid = $('#news-list') || $('#news-grid');
    if (!grid) {
      const host = $('main') || document.body;
      grid = document.createElement('div');
      grid.id = 'news-list';
      host.appendChild(grid);
    }

    let pager = $('#pager') || $('#paginator');
    if (!pager) {
      pager = document.createElement('div');
      pager.id = 'pager';
      grid.after(pager);
    }
    return { grid, pager };
  }

  function fmtDate(d) {
    try {
      const dd = new Date(d);
      const pad = (n) => String(n).padStart(2, '0');
      return `${pad(dd.getDate())}.${pad(dd.getMonth() + 1)}.${dd.getFullYear()}, ${pad(dd.getHours())}:${pad(dd.getMinutes())}`;
    } catch {
      return '';
    }
  }

  // Простой стабильный id по ссылке/заголовку/дате — чтобы article.html?id=...
  function makeId(item) {
    const base = (item.link || '') + '|' + (item.title || '') + '|' + (+item.date || 0);
    let h = 2166136261 >>> 0;
    for (let i = 0; i < base.length; i++) {
      h ^= base.charCodeAt(i);
      h = Math.imul(h, 16777619) >>> 0;
    }
    return h.toString(16);
  }

  function getPageParam() {
    try { return parseInt(new URLSearchParams(location.search).get('page') || STATE.page || 1, 10); }
    catch { return STATE.page || 1; }
  }

  function setPageParam(page) {
    const url = new URL(location.href);
    url.searchParams.set('page', page);
    history.replaceState(null, '', url);
  }

  // ---------- карточка ----------
  function cardHTML(item) {
    const id = item._id || makeId(item);
    item._id = id;

    // аккуратно берём картинку — если её нет, делаем скелет-превью
    const hasImg = !!item.image;
    const imgBlock = hasImg
      ? `<div class="card__thumb"><img loading="lazy" src="${item.image}" alt=""></div>`
      : `<div class="card__thumb card__thumb--empty" aria-hidden="true"></div>`;

    const src = item.domain ? item.domain : (item.link ? new URL(item.link).hostname : '');

    // ссылка на нашу статью (в article.html мы сможем вычитать по id/u)
    const u = encodeURIComponent(item.link || '');
    const href = `article.html?id=${id}&u=${u}${STATE.page ? `&from=${STATE.page}` : ''}`;

    const dateStr = fmtDate(item.date);

    return `
      <article class="card">
        <a class="card__wrap" href="${href}">
          ${imgBlock}
          <div class="card__body">
            <div class="card__meta">
              <span class="card__domain">${src}</span>
              ${dateStr ? `<span class="card__dot">•</span><time>${dateStr}</time>` : ''}
            </div>
            <h3 class="card__title">${item.title || ''}</h3>
            ${item.summary ? `<p class="card__desc">${item.summary}</p>` : ''}
          </div>
        </a>
      </article>
    `;
  }

  // ---------- пагинация ----------
  function buildPager(total, per, page) {
    const pages = Math.max(1, Math.ceil(total / per));
    if (pages <= 1) return '';

    const makeBtn = (p, text = String(p), isActive = false, disabled = false) =>
      `<button class="pager__btn${isActive ? ' is-active' : ''}" data-page="${p}" ${disabled ? 'disabled' : ''}>${text}</button>`;

    let html = '';
    html += makeBtn(Math.max(1, page - 1), '«', false, page <= 1);

    // Показываем «окно» из номеров (примерно до 10)
    const span = 4;
    const start = Math.max(1, page - span);
    const end = Math.min(pages, page + span);

    for (let p = start; p <= end; p++) {
      html += makeBtn(p, String(p), p === page, false);
    }

    html += makeBtn(Math.min(pages, page + 1), '»', false, page >= pages);
    return html;
  }

  function bindPager(grid, pager) {
    pager.addEventListener('click', (e) => {
      const btn = e.target.closest('.pager__btn');
      if (!btn) return;
      const p = parseInt(btn.dataset.page, 10);
      if (!isNaN(p)) {
        STATE.page = p;
        setPageParam(p);
        paint(); // перерисуем
        // небольшой скролл к началу
        grid.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  }

  // ---------- публичный рендер ----------
  window.paint = function paint() {
    const { grid, pager } = ensureContainer();

    const all = (Array.isArray(STATE.all) ? STATE.all : []).filter(n => n && !BLOCKED_DOMAINS.has(n.domain));
    const per = STATE.per || 24;
    const page = Math.max(1, getPageParam());

    const total = all.length;
    const from = (page - 1) * per;
    const to = Math.min(total, from + per);
    const slice = all.slice(from, to);

    // карточки
    grid.innerHTML = slice.map(cardHTML).join('');

    // пагинация
    pager.className = 'pager';
    pager.innerHTML = buildPager(total, per, page);

    // вешаем обработчики
    bindPager(grid, pager);
  };

  // ----- базовые стили (минимум), чтобы скелет выглядел прилично -----
  const css = `
  #news-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(260px, 1fr));
    gap: 24px;
  }
  @media (min-width: 980px) {
    #news-grid { grid-template-columns: repeat(3, 1fr); }
  }
  .card {
    border-radius: 16px;
    background: #fff;
    box-shadow: 0 2px 12px rgba(0,0,0,.06);
    overflow: hidden;
  }
  .card__wrap { display:block; color:inherit; text-decoration:none; }
  .card__thumb {
    width: 100%;
    aspect-ratio: 16/9;
    background: #f2f3f5;
    overflow: hidden;
  }
  .card__thumb--empty {
    background: linear-gradient(180deg, #f4f4f4, #eceff3);
  }
  .card__thumb img {
    width: 100%; height: 100%; object-fit: cover; display: block;
  }
  .card__body { padding: 14px 16px 18px; }
  .card__meta { color:#6b7280; font-size:12px; display:flex; gap:6px; align-items:center; margin-bottom:8px; }
  .card__dot { opacity:.6; }
  .card__title { font-size:18px; line-height:1.25; margin:0 0 8px; }
  .card__desc { margin:0; color:#374151; font-size:14px; line-height:1.4; max-height:3.9em; overflow:hidden; }
  .pager { display:flex; gap:8px; margin:28px 0 8px; flex-wrap:wrap; justify-content:center; }
  .pager__btn {
    border:1px solid #e5e7eb; background:#fff; border-radius:10px;
    padding:8px 12px; cursor:pointer; min-width:40px;
  }
  .pager__btn.is-active { background:#111827; color:#fff; border-color:#111827; }
  .pager__btn:disabled { opacity:.35; cursor:not-allowed; }
  `;
  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);
})();
