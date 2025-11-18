// article.js — полная статья для «СпецТрейлеры»
// Берёт индекс статьи из параметра ?idx=N, грузит те же JSON,
// блокирует переходы на TASS через список BLOCKED.

'use strict';

const BLOCKED = ['tass.ru', 'www.tass.ru', 'tass.com', 'tass'];

const DATA_PATHS = [
  './data/news_meta.json',
  './data/news.json'
];

const $ = (sel, root = document) => root.querySelector(sel);

function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(+d)) return '';
  const p = n => String(n).padStart(2, '0');
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()}, ${p(d.getHours())}:${p(d.getMinutes())}`;
}

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
    const contentHtml = pickField(item, ['content_html', 'content', 'body'], '');

    return {
      idx,
      raw: item,
      title,
      summary,
      category,
      source,
      published,
      image,
      url,
      contentHtml
    };
  });
}

function getIdxFromQuery() {
  const params = new URLSearchParams(window.location.search);
  const idxStr = params.get('idx');
  if (idxStr === null) return null;
  const n = Number.parseInt(idxStr, 10);
  return Number.isNaN(n) ? null : n;
}

function getHost(url) {
  try {
    return new URL(url).hostname;
  } catch {
    return '';
  }
}

function showError(msg) {
  const errorEl = $('#article-error');
  if (errorEl) {
    errorEl.textContent = msg;
    errorEl.style.display = 'block';
  } else {
    alert(msg);
  }
}

async function initArticle() {
  const idx = getIdxFromQuery();
  if (idx === null) {
    showError('Не передан параметр статьи (?idx=...).');
    return;
  }

  try {
    const data = await loadNewsData();
    const items = normalizeItems(data);

    if (idx < 0 || idx >= items.length) {
      showError('Статья не найдена. Возможно, лента обновилась.');
      return;
    }

    const item = items[idx];

    const titleEl = $('#article-title');
    const metaEl = $('#article-meta');
    const imgWrapEl = $('#article-image-wrap');
    const bodyEl = $('#article-body');
    const sourceLinkEl = $('#article-source-link');
    const sourceHostEl = $('#article-source-host');

    if (titleEl) {
      titleEl.textContent = item.title;
    }

    if (metaEl) {
      const parts = [];
      if (item.category) parts.push(item.category);
      if (item.source) parts.push(item.source);
      if (item.published) parts.push(fmtDate(item.published));
      metaEl.textContent = parts.join(' · ');
    }

    if (imgWrapEl) {
      if (item.image) {
        imgWrapEl.innerHTML = `<img src="${item.image}" alt="">`;
      } else {
        imgWrapEl.style.display = 'none';
      }
    }

    if (bodyEl) {
      if (item.contentHtml) {
        // Предполагаем, что контент уже из доверенного источника (агрегатор)
        bodyEl.innerHTML = item.contentHtml;
      } else if (item.summary) {
        bodyEl.innerHTML = `<p>${item.summary}</p>`;
      } else {
        bodyEl.innerHTML = '<p>Текст статьи недоступен.</p>';
      }
    }

    const host = item.url ? getHost(item.url) : '';

    if (sourceHostEl) {
      sourceHostEl.textContent = host || (item.source || '');
    }

    if (sourceLinkEl) {
      if (!item.url) {
        sourceLinkEl.style.display = 'none';
      } else if (BLOCKED.includes(host)) {
        // TASS и т.п. — ссылку не даём, только текст
        sourceLinkEl.style.display = 'none';
        if (sourceHostEl) {
          sourceHostEl.textContent = 'Источник скрыт редакцией (TASS)';
        }
      } else {
        sourceLinkEl.href = item.url;
        sourceLinkEl.target = '_blank';
        sourceLinkEl.rel = 'noopener noreferrer';
      }
    }
  } catch (err) {
    console.error('Ошибка при загрузке статьи:', err);
    showError('Ошибка при загрузке статьи. Проверь, что JSON-файлы в папке data доступны.');
  }
}

document.addEventListener('DOMContentLoaded', initArticle);
