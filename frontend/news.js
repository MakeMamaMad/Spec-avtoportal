// news.js — простой и устойчивый вариант

const NEWS_URL = 'data/news.json';

// Формат даты "21.11.2025"
function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(+d)) return '';
  const p = n => String(n).padStart(2, '0');
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()}`;
}

// Обрезаем HTML до текста
function stripHtml(html) {
  if (!html) return '';
  const tmp = document.createElement('div');
  tmp.innerHTML = html;
  return tmp.textContent || tmp.innerText || '';
}

// Рендер одной карточки новости
function renderNewsCard(item) {
  const id =
    item.id ||
    item.slug ||
    item.guid ||
    item.uid ||
    '';

  const sourceName =
    item.source_name ||
    item.source ||
    (item.domain && String(item.domain).replace(/^https?:\/\//, '')) ||
    '';

  const published =
    item.published ||
    item.published_at ||
    item.date ||
    item.datetime ||
    '';

  const title =
    item.title ||
    item.headline ||
    'Без заголовка';

  const summary =
    stripHtml(
      item.summary ||
      item.description ||
      item.lead ||
      item.snippet ||
      ''
    );

  // ссылка на внутреннюю страницу статьи (как раньше)
  const internalUrl = id
    ? `article.html?id=${encodeURIComponent(id)}`
    : (item.url || item.link || '#');

  const card = document.createElement('article');
  card.className = 'news-card';

  card.innerHTML = `
    <header class="news-card__header">
      <h3 class="news-card__title">
        <a href="${internalUrl}">
          ${title}
        </a>
      </h3>
      <div class="news-card__meta">
        ${published ? `<span class="news-card__date">${fmtDate(published)}</span>` : ''}
        ${sourceName ? `<span class="news-card__source">${sourceName}</span>` : ''}
      </div>
    </header>
    <div class="news-card__body">
      ${summary ? `<p>${summary}</p>` : ''}
    </div>
    <footer class="news-card__footer">
      <a class="news-card__more" href="${internalUrl}">Читать полностью</a>
    </footer>
  `;

  return card;
}

// Рендер ленты
function renderNewsList(container, items) {
  container.innerHTML = '';
  const frag = document.createDocumentFragment();

  items.forEach(item => {
    try {
      const card = renderNewsCard(item);
      frag.appendChild(card);
    } catch (e) {
      console.error('[news] ошибка при рендере карточки', e, item);
    }
  });

  container.appendChild(frag);
}

// Кнопка "Ок, посмотреть" — просто перезагрузить страницу
function setupUpdateBanner() {
  const banner = document.querySelector('[data-role="news-update-banner"]');
  const btn = document.querySelector('[data-role="news-update-button"]');

  if (banner && btn) {
    btn.addEventListener('click', function () {
      // просто перезагружаем страницу, подтягиваются свежие news.json
      window.location.reload();
    });
  }
}

// Основная загрузка новостей
async function loadNews() {
  const listEl = document.querySelector('[data-role="news-list"]');
  const loadingEl = document.querySelector('[data-role="news-loading"]');
  const errorEl = document.querySelector('[data-role="news-error"]');
  const emptyEl = document.querySelector('[data-role="news-empty"]');

  if (!listEl) {
    console.warn('[news] контейнер ленты не найден');
    return;
  }

  function showState(state) {
    const states = [
      ['loading', loadingEl],
      ['error', errorEl],
      ['empty', emptyEl]
    ];

    states.forEach(([name, el]) => {
      if (!el) return;
      el.classList.toggle('is-hidden', state !== name);
    });

    if (state === 'ok') {
      if (loadingEl) loadingEl.classList.add('is-hidden');
      if (errorEl) errorEl.classList.add('is-hidden');
      if (emptyEl) emptyEl.classList.add('is-hidden');
    }
  }

  showState('loading');

  try {
    // cache-buster, чтобы браузер не тянул старый кэш
    const resp = await fetch(NEWS_URL + '?_=' + Date.now());
    if (!resp.ok) {
      throw new Error('HTTP ' + resp.status);
    }

    const data = await resp.json();

    let items = [];
    if (Array.isArray(data)) items = data;
    else if (Array.isArray(data.items)) items = data.items;
    else if (Array.isArray(data.news)) items = data.news;
    else if (Array.isArray(data.results)) items = data.results;

    if (!items.length) {
      console.warn('[news] news.json пустой или формат не распознан', data);
      showState('empty');
      return;
    }

    renderNewsList(listEl, items);
    showState('ok');
  } catch (err) {
    console.error('[news] не удалось загрузить ленту', err);
    if (errorEl) {
      errorEl.textContent =
        'Не удалось загрузить новости. Попробуйте обновить страницу.';
    }
    showState('error');
  }
}

// Старт
document.addEventListener('DOMContentLoaded', function () {
  setupUpdateBanner();
  loadNews();
});
