// Страница одной статьи

(function () {
  const NEWS_URL = './data/news.json';

  const articleEl = document.getElementById('article');
  const relatedEl = document.getElementById('related');

  const get = (obj, keys, fallback = '') => {
    for (const k of keys) if (obj?.[k] != null && obj[k] !== '') return obj[k];
    return fallback;
  };
  const fmtDate = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(+d)) return '';
    const p = (n) => String(n).padStart(2, '0');
    return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()}`;
  };

  function notFound(msg) {
    articleEl.innerHTML = `
      <div class="empty-state">
        <h1>Статья не найдена</h1>
        <p>${msg}</p>
        <p><a class="news-card-link" href="./index.html">Вернуться к ленте</a></p>
      </div>`;
  }

  function renderArticle(item, allNews) {
    const title = get(item, ['title','headline','name'], 'Без заголовка');
    const summary = get(item, ['summary','lead','description'], '');
    const date = fmtDate(get(item, ['published_at','date','pub_date']));
    const source = get(item, ['source_name','source','site'], '');
    const url = get(item, ['url','link','source_url'], '');
    const image = get(item, ['image_url','image','img'], '');
    const tags = item.tags || item.rubrics || [];
    const body = get(item, ['content_html','body_html']) ||
                 get(item, ['content','body','text','full_text','article'], summary);

    document.title = `${title} — СпецТрейлеры`;

    articleEl.innerHTML = `
      <header class="article-header">
        <p class="article-breadcrumbs"><a href="./index.html">Новости</a>${tags?.length ? ` · <span>${tags.join(', ')}</span>` : ''}</p>
        <h1 class="article-title">${title}</h1>
        <div class="article-meta">
          ${date ? `<span class="article-meta-item">${date}</span>` : ''}
          ${source ? `<span class="article-meta-item">${source}</span>` : ''}
        </div>
      </header>
      ${image ? `<div class="article-image-wrap"><img src="${image}" class="article-image" alt=""/></div>` : ''}
      <section class="article-body">
        ${body && /<\/?[a-z][\s\S]*>/i.test(body) ? body : `<p>${(body || '').replace(/\n{2,}/g,'</p><p>')}</p>`}
      </section>
      <footer class="article-footer">
        ${url ? `<a class="primary-btn" href="${url}" target="_blank" rel="noopener noreferrer">Читать в источнике</a>` : ''}
        <a class="secondary-btn" href="./index.html">Назад к ленте</a>
      </footer>
    `;

    // простые «похожие» по первой метке
    const tag0 = (tags && tags[0]) || null;
    const id = get(item, ['id','slug'], null);
    const related = allNews.filter(n => {
      const nid = get(n, ['id','slug'], null);
      if (id && nid === id) return false;
      if (!tag0) return true;
      const t = n.tags || n.rubrics || [];
      return Array.isArray(t) && t.includes(tag0);
    }).slice(0,5);

    relatedEl.innerHTML = '';
    for (const r of related) {
      const rid = get(r, ['id','slug'], '');
      const rTitle = get(r, ['title','headline','name'], 'Без заголовка');
      const rDate = fmtDate(get(r, ['published_at','date','pub_date']));
      const a = document.createElement('a');
      a.className = 'related-item';
      a.href = `./article.html?id=${encodeURIComponent(rid)}`;
      a.innerHTML = `<span class="related-title">${rTitle}</span>${rDate ? `<span class="related-date">${rDate}</span>` : ''}`;
      relatedEl.appendChild(a);
    }
  }

  async function init() {
    const params = new URLSearchParams(window.location.search);
    const id = params.get('id');
    if (!id) return notFound('Не передан параметр ?id=...');

    let news = [];
    try {
      const r = await fetch(NEWS_URL, { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP '+r.status);
      const data = await r.json();
      news = Array.isArray(data) ? data : data.items || [];
    } catch (e) {
      console.error('Не удалось загрузить базу новостей', e);
      return notFound('Ошибка загрузки базы новостей.');
    }

    const item = news.find(n => String(get(n,['id','slug'],'')).trim() === id.trim());
    if (!item) return notFound('Новость с таким идентификатором не найдена.');
    renderArticle(item, news);
  }

  document.addEventListener('DOMContentLoaded', init);
})();
