// article.js v13 — полная версия с фолбэком загрузки news.json и корректной кнопкой «Читать в источнике»

/* =====================[ Константы и утилиты ]===================== */

const BLOCKED = ['tass.ru', 'www.tass.ru', 'tass.com', 'tass'];

const $ = (s, r = document) => r.querySelector(s);

function fmtDate(iso) {
  const d = new Date(iso || Date.now());
  if (Number.isNaN(+d)) return '';
  const p = n => String(n).padStart(2, '0');
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()}, ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function stripHTML(s = '') {
  const el = document.createElement('div');
  el.innerHTML = s;
  return (el.textContent || '').trim();
}

/* =====================[ DOM-обёртки ]===================== */

function ensure() {
  const post = $('#post') || (() => {
    const n = document.createElement('main');
    n.id = 'post';
    document.body.appendChild(n);
    return n;
  })();

  const nf = $('#nf') || (() => {
    const n = document.createElement('div');
    n.id = 'nf';
    n.hidden = true;
    n.textContent = 'Новость не найдена';
    document.body.appendChild(n);
    return n;
  })();

  const actions = $('#bottom-actions') || (() => {
    const n = document.createElement('div');
    n.id = 'bottom-actions';
    n.hidden = true;
    n.innerHTML = `
      <a id="back-link" href="index.html">← Вернуться к ленте</a>
      <a id="read-source" href="#" hidden rel="noopener noreferrer" target="_blank" style="margin-left:12px;">Читать в источнике ↗</a>
    `;
    document.body.appendChild(n);
    return n;
  })();

  return { post, nf, actions };
}

/* =====================[ Вспомогательные функции ]===================== */

const isBlocked = (it) => {
  const d = String(it?.domain || '').toLowerCase().trim();
  const u = String(it?.url || '').toLowerCase().trim();
  return BLOCKED.some(b => d.includes(b) || u.includes(b));
};

const pickImage = (it) => {
  const cand = it?.image || it?.cover || it?.img || (Array.isArray(it?.images) ? it.images[0] : '');
  return (typeof cand === 'string' && cand.trim()) ? cand.trim() : '';
};

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

/* === Поиск исходного URL для кнопки «Читать в источнике» === */

function pickSourceField(item) {
  const candidates = [
    item?.url, item?.link, item?.href, item?.source,
    item?.source_url, item?.origin_url, item?.original_url, item?.canonical
  ];
  return candidates.find(v => typeof v === 'string' && v.trim());
}

function buildSourceUrl(item) {
  const raw = pickSourceField(item);
  const domain = (item?.domain || '').replace(/^https?:\/\//, '').split('/')[0];

  if (!raw) return '';

  const u = String(raw).trim();

  // локальные ссылки на нашу страницу — игнорируем
  if (/^(\.?\/)?article\.html(\?|#|$)/i.test(u)) return '';

  // абсолютный URL
  if (/^https?:\/\//i.test(u)) return u;

  // протокол-относительный
  if (u.startsWith('//')) return 'https:' + u;

  // относительный путь -> приклеиваем домен
  if (u.startsWith('/')) {
    if (domain) return `https://${domain}${u}`;
    return '';
  }

  // прочие случаи — если есть домен, считаем относительным к домену
  if (domain) return `https://${domain}/${u}`;

  return '';
}

/* =====================[ Отрисовка статьи ]===================== */

function render(item) {
  const { post, nf, actions } = ensure();

  if (!item || isBlocked(item)) {
    nf.hidden = false;
    actions.hidden = false;
    post.innerHTML = '';
    return;
  }

  const img = pickImage(item);
  const cover = img
    ? `<div class="cover"><img src="${img}" loading="eager" decoding="async" referrerpolicy="no-referrer"
         onerror="this.onerror=null;this.src='${placeholderFor(item)}'"></div>`
    : ``;

  post.innerHTML = `
    <h1 class="title">${item.title || ''}</h1>
    <div class="meta">
      ${item.domain ? `<span>${item.domain}</span>` : ''}
      ${item.date ? `<span>•</span><time>${fmtDate(item.date)}</time>` : ''}
    </div>
    ${cover}
    ${item.summary ? `<p class="lead">${stripHTML(item.summary)}</p>` : ''}
  `;

  // панель действий
  actions.hidden = false;

  // «Читать в источнике»
  const readBtn = $('#read-source') || (() => {
    const a = document.createElement('a');
    a.id = 'read-source';
    a.textContent = 'Читать в источнике ↗';
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.hidden = true;
    ensure().actions.appendChild(a);
    return a;
  })();

  const src = buildSourceUrl(item);
  if (src) {
    readBtn.href = src;
    readBtn.hidden = false;
  } else {
    readBtn.hidden = true;
  }
}

/* =====================[ Загрузка данных ]===================== */

function getId() {
  const u = new URL(location.href);
  return u.searchParams.get('id');
}

function pickFromLocal() {
  try {
    const raw = localStorage.getItem('currentArticle');
    if (raw) return JSON.parse(raw);
  } catch {}
  return null;
}

function newsJsonUrl() {
  // Совместимо с GitHub Pages: если в <head> добавлен fixPath — используем его
  const raw = '/frontend/data/news.json';
  if (typeof window.fixPath === 'function') return window.fixPath(raw);
  // локальная/относительная подстановка
  return 'frontend/data/news.json';
}

async function loadAllNewsIfNeeded() {
  if (Array.isArray(window.__ALL_NEWS__) && window.__ALL_NEWS__.length) return window.__ALL_NEWS__;
  try {
    const url = newsJsonUrl();
    const res = await fetch(url, { cache: 'no-store' });
    const arr = await res.json();
    if (Array.isArray(arr)) {
      window.__ALL_NEWS__ = arr;
      return arr;
    }
  } catch (e) {
    console.error('Failed to load news.json', e);
  }
  return [];
}

/* =====================[ Точка входа ]===================== */

document.addEventListener('DOMContentLoaded', async () => {
  // 1) Если есть кэш в localStorage — отрисуем сразу (быстрое ощущение «мгновенно»)
  const cached = pickFromLocal();
  if (cached) render(cached);

  // 2) Если в окне уже есть все новости — ищем там
  let list = Array.isArray(window.__ALL_NEWS__) ? window.__ALL_NEWS__ : null;

  // 3) Если нет — подгружаем из news.json
  if (!list) {
    list = await loadAllNewsIfNeeded();
  }

  const id = getId();
  const n = Number(id);

  // 4) Поиск по индексу или по полю id
  let item = Number.isFinite(n) && list[n] ? list[n] : null;
  if (!item && id != null) {
    item = list.find(x => String(x?.id) === String(id)) || null;
  }

  if (!cached || (item && cached?.title !== item?.title)) {
    // если не было кэша или нашли «получше» — отрисуем окончательно
    render(item || cached || null);
  }
});
