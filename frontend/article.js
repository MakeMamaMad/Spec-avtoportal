// frontend/article.js

(function () {
  const NEWS_URL = 'data/news.json';

  const articleEl = document.getElementById('article');
  const relatedEl = document.getElementById('related');

  function fmtDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(+d)) return '';
    const p = (n) => String(n).padStart(2, '0');
    return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()}`;
  }

  function getField(obj, candidates, fallback = '') {
    for (const key of candidates) {
      if (obj && obj[key] != null && obj[key] !== '') return obj[key];
    }
    return fallback;
  }

  function renderNotFound(message) {
    articleEl.innerHTML = `
      <div class="empty-state">
        <h1>Статья не найдена</h1>
        <p>${message}</p>
        <p><a href="index.html" class="news-card-link">Вернуться к ленте</a></p>
      </div>
    `;
  }

  function renderArticle(item, allNews) {
    const title = getField(item, ['title', 'headline', 'name'], 'Без заголовка');
    const summary = getField(item, ['summary', 'lead', 'description'], '');
    const dateRaw = getField(item, ['published_at', 'date', 'pub_date']);
    const date = fmtDate(dateRaw);
    const sourceName = getField(item, ['source_name', 'source', 'site'], '');
    const sourceUrl = getField(item, ['url', 'link', 'source_url'], '');
    const image = getField(item, ['image_url', 'image', 'img'], '');
    const tags = item.tags || item.rubrics || [];
    const bodyHtml =
      getField(item, ['content_html', 'body_html']) ||
      getField(item, ['content', 'body', 'text', 'full_text', 'article'], summary);

    document.title = `${title} — СпецТрейлеры`;

    articleEl.innerHTML = `
      <header class="article-header">
        <p class="article-breadcrumbs">
          <a href="index.html">Новости</a> ·
          ${tags && tags.length ? `<span>${tags.map((t) => String(t)).join(', ')}</span>` : ''}
        </p>
        <h1 class="article-title">${title}</h1>
        <div class="article-meta">
          ${date ? `<span class="article-meta-item">${date}</span>` : ''}
          ${sourceName ? `<span class="article-meta-item">${sourceName}</span>` : ''}
        </div>
      </header>

      ${image ? `<div class="article-image-wrap"><img src="${image}" alt="" class="article-image"/></div>` : ''}

      <section class="article-body">
        ${
          bodyHtml && /<\/?[a-z][\s\S]*>/i.test(bodyHtml)
            ? bodyHtml
            : `<p>${(bodyHtml || '').replace(/\n{2,}/g, '</p><p>')}</p>`
        }
      </section>

      <footer class="article-footer">
        ${
          sourceUrl
            ? `<a class="primary-btn" href="${sourceUrl}" target="_blank" rel="noopener noreferrer">
                 Читать в источнике
               </a>`
            : ''
        }
        <a href="index.html" class="secondary-btn">Назад к ленте</a>
      </footer>
    `;

    // простые "похожие" материалы
    const sameTag = (tags && tags[0]) || null;
    const currentId = getField(item, ['id', 'slug'], null);

    const related = allNews
      .filter((n) => {
        if (!currentId) return true;
        const nid = getField(n, ['id', 'slug'], null);
        if (nid === currentId) return false;
        if (!sameTag) return true;
        const nTags = n.tags || n.rubrics || [];
        return Array.isArray(nTags) && nTags.includes(sameTag);
      })
      .slice(0, 5);

    relatedEl.innerHTML = '';

    for (const r of related) {
      const rid = getField(r, ['id', 'slug'], '');
      const rTitle = getField(r, ['title', 'headline', 'name'], 'Без заголовка');
      const rDate = fmtDate(getField(r, ['published_at', 'date', 'pub_date']));
      const a = document.createElement('a');
      a.className = 'related-item';
      a.href = `article.html?id=${encodeURIComponent(rid)}`;
      a.innerHTML = `
        <span class="related-title">${rTitle}</span>
        ${rDate ? `<span class="related-date">${rDate}</span>` : ''}
      `;
      relatedEl.appendChild(a);
    }
  }

  async function init() {
    const params = new URLSearchParams(window.location.search);
    const id = params.get('id');

    if (!id) {
      renderNotFound('Не передан идентификатор статьи в параметре URL ?id=...');
      return;
    }

    let data;
    try {
      const resp = await fetch(NEWS_URL, { cache: 'no-store' });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      data = await resp.json();
    } catch (e) {
      console.error('Не удалось загрузить новости для статьи', e);
      renderNotFound('Ошибка при загрузке базы новостей.');
      return;
    }

    const news = Array.isArray(data) ? data : data.items || [];
    const item =
      news.find((n) => String(getField(n, ['id', 'slug'], '')).trim() === id.trim()) || null;

    if (!item) {
      renderNotFound('Новость с таким идентификатором не найдена.');
      return;
    }

    renderArticle(item, news);
  }

  document.addEventListener('DOMContentLoaded', init);
})();
