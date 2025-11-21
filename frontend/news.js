// news.js — клиентская лента с ручным обновлением по кнопке
// --------------------------------------------------------

// URL статичной ленты (то, что лежит в GitHub Pages артефакте)
const NEWS_URL_PAGES = 'data/news.json';

// URL живой ленты прямо из репозитория main
// (сюда пишет GitHub Action ingest & publish)
const NEWS_URL_RAW =
  'https://raw.githubusercontent.com/MakeMamaMad/Spec-avtoportal/main/frontend/data/news.json';

// Как часто проверяем, появились ли новые новости (мс)
// Ингест крутится раз в 30 минут, опрашиваем, например, каждые 5 минут.
const POLL_INTERVAL = 5 * 60 * 1000;

let currentNews = [];
let pendingNews = null;
let pollTimer = null;

// DOM-элементы (заполним после DOMContentLoaded)
let elList, elEmpty, elLoading, elError;
let elBanner, elBannerText, elBannerBtn;

document.addEventListener('DOMContentLoaded', () => {
  elList = document.querySelector('[data-role="news-list"]');
  elEmpty = document.querySelector('[data-role="news-empty"]');
  elLoading = document.querySelector('[data-role="news-loading"]');
  elError = document.querySelector('[data-role="news-error"]');

  elBanner = document.querySelector('[data-role="news-refresh-banner"]');
  elBannerText = document.querySelector('[data-role="news-refresh-text"]');
  elBannerBtn = document.querySelector('[data-role="news-refresh-btn"]');

  if (elBannerBtn) {
    elBannerBtn.addEventListener('click', onApplyUpdatesClick);
  }

  // Стартуем: грузим текущую ленту и запускаем опрос
  loadInitialNews().then(() => {
    startPollingForUpdates();
  });
});

// ------------------------
// Загрузка и обновление
// ------------------------

async function loadInitialNews() {
  showState('loading');

  try {
    // Пытаемся сразу взять живую ленту из RAW
    const items = await fetchNews(NEWS_URL_RAW);
    currentNews = items;
    renderNewsList(currentNews);
    showState(currentNews.length ? 'ok' : 'empty');
  } catch (errRaw) {
    console.warn('Не удалось загрузить RAW-ленту, пробуем Pages:', errRaw);
    try {
      const items = await fetchNews(NEWS_URL_PAGES);
      currentNews = items;
      renderNewsList(currentNews);
      showState(currentNews.length ? 'ok' : 'empty');
    } catch (errPages) {
      console.error('Не удалось загрузить ленту совсем:', errPages);
      showState('error');
    }
  }
}

/**
 * Опрос GitHub RAW: появились ли новые новости.
 */
function startPollingForUpdates() {
  if (pollTimer) {
    clearInterval(pollTimer);
  }

  pollTimer = setInterval(async () => {
    try {
      const fresh = await fetchNews(NEWS_URL_RAW);
      const diffCount = countNewItems(currentNews, fresh);

      if (diffCount > 0) {
        pendingNews = fresh;
        showUpdateBanner(diffCount);
      }
    } catch (e) {
      console.warn('Не удалось проверить обновления ленты:', e);
    }
  }, POLL_INTERVAL);
}

/**
 * Клик по кнопке "Ок, посмотреть" в верхнем баннере.
 */
function onApplyUpdatesClick() {
  if (pendingNews && Array.isArray(pendingNews)) {
    currentNews = pendingNews;
    pendingNews = null;
    renderNewsList(currentNews);
    showState(currentNews.length ? 'ok' : 'empty');
  }

  hideUpdateBanner();
}

// ------------------------
// Вспомогательные функции
// ------------------------

async function fetchNews(url) {
  const res = await fetch(withCacheBuster(url));
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} при загрузке ${url}`);
  }

  const data = await res.json();

  // Лента может быть либо массивом, либо объектом с полем items/news
  if (Array.isArray(data)) return data;
  if (Array.isArray(data.items)) return data.items;
  if (Array.isArray(data.news)) return data.news;

  console.warn('Неожиданный формат news.json, жду массив, пришло:', data);
  return [];
}

function withCacheBuster(url) {
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}_=${Date.now()}`;
}

function countNewItems(oldArr, newArr) {
  if (!Array.isArray(oldArr) || !Array.isArray(newArr)) return 0;

  const oldIds = new Set(
    oldArr.map((n) => normalizeId(n)).filter(Boolean),
  );

  let count = 0;
  for (const item of newArr) {
    const id = normalizeId(item);
    if (id && !oldIds.has(id)) {
      count++;
    } else {
      // как только дошли до старых — дальше, скорее всего, тоже старые
      // можно досрочно выйти, но оставим простой вариант
    }
  }
  return count;
}

function normalizeId(item) {
  return (
    item.id ||
    item._id ||
    item.uid ||
    item.slug ||
    item.url ||
    item.link ||
    null
  );
}

// ------------------------
// Рендер ленты
// ------------------------

function renderNewsList(items) {
  if (!elList) return;

  elList.innerHTML = '';

  if (!Array.isArray(items) || items.length === 0) {
    return;
  }

  for (const item of items) {
    const cardEl = renderNewsCard(item);
    elList.appendChild(cardEl);
  }
}

function renderNewsCard(item) {
  const {
    title,
    description,
    summary,
    text,
    url,
    link,
    source,
    source_name,
    domain,
    published,
    published_at,
    date,
    datetime,
    image,
    image_url,
  } = item;

  const card = document.createElement('article');
  card.className = 'news-card';

  const titleEl = document.createElement('h3');
  titleEl.className = 'news-card__title';
  titleEl.textContent = title || item.headline || 'Без заголовка';

  const metaEl = document.createElement('div');
  metaEl.className = 'news-card__meta';

  const formattedDate = formatDate(
    published_at || published || datetime || date,
  );
  const srcName = source_name || source || domain || '';

  if (formattedDate) {
    const dateEl = document.createElement('span');
    dateEl.className = 'news-card__date';
    dateEl.textContent = formattedDate;
    metaEl.appendChild(dateEl);
  }

  if (srcName) {
    const srcEl = document.createElement('span');
    srcEl.className = 'news-card__source';
    srcEl.textContent = ` ${srcName}`;
    metaEl.appendChild(srcEl);
  }

  const bodyEl = document.createElement('p');
  bodyEl.className = 'news-card__description';
  bodyEl.textContent =
    summary || description || text || item.lead || 'Описание новости отсутствует.';

  const linkHref = url || link || item.source_url || '#';
  const readMore = document.createElement('a');
  readMore.className = 'news-card__link';
  readMore.href = linkHref;
  readMore.target = '_blank';
  readMore.rel = 'noopener noreferrer';
  readMore.textContent = 'Читать полностью';

  // Картинка, если есть
  const imgSrc = image || image_url || item.imageUrl || item.thumb;
  if (imgSrc) {
    const imgWrap = document.createElement('div');
    imgWrap.className = 'news-card__image-wrap';

    const img = document.createElement('img');
    img.className = 'news-card__image';
    img.src = imgSrc;
    img.alt = title || '';

    imgWrap.appendChild(img);
    card.appendChild(imgWrap);
  }

  card.appendChild(titleEl);
  card.appendChild(metaEl);
  card.appendChild(bodyEl);
  card.appendChild(readMore);

  return card;
}

function formatDate(value) {
  if (!value) return '';

  try {
    const d = new Date(value);
    if (Number.isNaN(+d)) return '';

    const pad = (n) => String(n).padStart(2, '0');
    return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`;
  } catch {
    return '';
  }
}

// ------------------------
// Состояния (loading / empty / error)
// ------------------------

function showState(state) {
  if (!elLoading || !elEmpty || !elError) return;

  elLoading.hidden = state !== 'loading';
  elEmpty.hidden = state !== 'empty';
  elError.hidden = state !== 'error';
}

function showUpdateBanner(count) {
  if (!elBanner || !elBannerText) return;
  elBannerText.textContent = `Лента новостей обновилась (+${count})`;
  elBanner.classList.remove('is-hidden');
}

function hideUpdateBanner() {
  if (!elBanner) return;
  elBanner.classList.add('is-hidden');
}
