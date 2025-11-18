// news.js — универсальная лента новостей для «СпецТрейлеры»
// Поддерживает и data/news_meta.json, и data/news.json,
// не падает, если структура JSON немного отличается.

'use strict';

// Возможные пути к данным — что-то одно у тебя точно есть.
const DATA_PATHS = [
  './data/news_meta.json',
  './data/news.json'
];

// Удобный короткий селектор
const $ = (sel, root = document) => root.querySelector(sel);

// Форматирование даты "DD.MM.YYYY, HH:MM"
function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(+d)) return '';
  const p = n => String(n).padStart(2, '0');
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()}, ${p(d.getHours())}:${p(d.getMinutes())}`;
}

// Достаём значение по нескольким возможным ключам
// keys: ['title', 'headline', 'data.title'] и т.п.
function pickField(obj, keys, fallback = '') {
  for (const key of keys) {
    const parts = key.split('.');
    let cur = obj;
    for (const part of parts) {
      if (cur && Object.prototype.hasOwnProperty.call(cur, part)) {
        cur = cur[part];
      } else {
        cur = undefined;
        break;
      }
    }
    if (cur !== undefined && cur !== null) return cur;
  }
  return fallback;
}

// Грузим JSON: пробуем несколько файлов, пока один не сработает
async function loadNewsData() {
  let lastError = null;

  for (const path of DATA_PATHS) {
    try {
      const res = await fetch(path, { cache: 'no-store' });
      if (!res.ok) {
        lastError = new Error(`${path}: HTTP ${res.status}`);
        continue;
      }
      return await res.json();
    } catch (err) {
      lastError = err;
    }
  }

  throw lastError || new Error('Не удалось загрузить данные новостей');
}

// Приводим сырые данные к единому виду
function normalizeItems(raw) {
  const list = Array.isArray(raw) ? raw : (raw?.items || raw?.news || []);

  return list.map((item, idx) => {
    const title = pickField(item, ['title', 'headline'], 'Без заголовка');
    const summary = pickField(item, ['summary', 'description', 'lead'], '');
    const category = pickField(item, ['category', 'rubric'], '');
    const source = pickField(item, ['source', 'source.name', 'source_title'], '');
    const published = pickField(item, ['published_at', 'pubDate', 'date'], '');
    const image = pickField(item, ['image_url', 'image', 'enclosure.url'], '');
    const url = pickField(item, ['url', 'link'], '');

    return {
      idx,          // индекс в массиве — будем передавать в article.html
      raw: item,    // оригинальный объект (на всякий случай)
      title,
      summary,
      category,
      source,
      published,
      image,
      url
    };
  });
}

// Создаём DOM карточки новости
function createCard(item) {
  const article = document.createElement('article');
  article.className = 'news-card';

  const linkHref = `article.html?idx=${encodeURIComponent(item.idx)}`;

  article.innerHTML = `
    <a class="news-card__link" href="${linkHref}">
      ${
        item.image
          ? `<div class="news-card__image-wrap">
               <img src="${item.image}" alt="">
             </div>`
          : ''
      }
      <div class="news-card__body">
        <div class="news-card__meta">
          ${item.category ? `<span class="news-card__badge">${item.category}</span>` : ''}
          ${item.published ? `<time class="news-card__date">${fmtDate(item.published)}</time>` : ''}
        </div>
        <h2 class="news-card__title">${item.title}</h2>
        ${item.summary ? `<p class="news-card__summary">${item.summary}</p>` : ''}
        ${item.source ? `<div class="news-card__source">Источник: ${item.source}</div>` : ''}
      </div>
    </a>
  `;

  return article;
}

// Точка входа
async function initNews() {
  const listEl = $('#news-list');
  const errorEl = $('#news-error');

  // Если на странице нет контейнера — просто выходим (например, это не главная)
  if (!listEl) return;

  try {
    const data = await loadNewsData();
    const items = normalizeItems(data);

    if (!items.length) {
      if (errorEl) errorEl.textContent = 'Пока нет новостей.';
      return;
    }

    items.forEach(item => {
      listEl.appendChild(createCard(item));
    });
  } catch (err) {
    console.error('Ошибка при загрузке новостей:', err);
    if (errorEl) {
      errorEl.textContent =
        'Ошибка при загрузке новостей. Проверь, что в папке data лежит news_meta.json или news.json.';
    }
  }
}

document.addEventListener('DOMContentLoaded', initNews);
