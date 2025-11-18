// Лента новостей на главной

(function () {
  const NEWS_URL = './data/news.json';

  const els = {
    list: document.getElementById('news-list'),
    empty: document.getElementById('news-empty'),
    loading: document.getElementById('news-loading'),
    error: document.getElementById('news-error'),
    search: document.getElementById('search'),
    rubricFilters: document.getElementById('rubric-filters'),
    topTags: document.getElementById('top-tags'),
  };

  let allNews = [];
  let activeRubric = null;
  let searchQuery = '';

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

  function buildRubrics(list) {
    const set = new Set();
    for (const n of list) {
      const tags = n.tags || n.rubrics || [];
      if (Array.isArray(tags)) for (const t of tags) {
        const s = String(t || '').trim(); if (s) set.add(s);
      }
    }
    els.rubricFilters.innerHTML = '';
    const allBtn = document.createElement('button');
    allBtn.className = 'chip chip-active';
    allBtn.textContent = 'Все';
    allBtn.dataset.rubric = '';
    els.rubricFilters.appendChild(allBtn);

    [...set].sort().forEach((tag) => {
      const b = document.createElement('button');
      b.className = 'chip';
      b.textContent = tag;
      b.dataset.rubric = tag;
      els.rubricFilters.appendChild(b);
    });
  }

  function buildTopTags(list) {
    const cnt = new Map();
    for (const n of list) {
      const tags = n.tags || n.rubrics || [];
      if (Array.isArray(tags)) for (const t of tags) {
        const key = String(t || '').trim(); if (!key) continue;
        cnt.set(key, (cnt.get(key) || 0) + 1);
      }
    }
    const top = [...cnt.entries()].sort((a,b)=>b[1]-a[1]).slice(0,10);
    els.topTags.innerHTML = '';
    for (const [tag, num] of top) {
      const li = document.createElement('li');
      li.className = 'tag-pill';
      li.textContent = `${tag} (${num})`;
      els.topTags.appendChild(li);
    }
  }

  function render() {
    const q = searchQuery.trim().toLowerCase();
    const rubric = activeRubric;

    const filtered = allNews.filter((n) => {
      const title = get(n, ['title', 'headline', 'name'], '').toLowerCase();
      const tags = (n.tags || n.rubrics || []).map((t) => String(t).toLowerCase());
      if (q && !title.includes(q)) return false;
      if (rubric && !tags.includes(rubric.toLowerCase())) return false;
      return true;
    });

    els.list.innerHTML = '';

    if (!filtered.length) {
      els.empty.hidden = false;
      return;
    }
    els.empty.hidden = true;

    filtered.forEach((n, idx) => {
      const id = get(n, ['id', 'slug'], String(idx));
      const title = get(n, ['title', 'headline', 'name'], 'Без заголовка');
      const summary = get(n, ['summary', 'lead', 'description'], '');
      const date = fmtDate(get(n, ['published_at', 'date', 'pub_date']));
      const source = get(n, ['source_name', 'source', 'site'], '');
      const image = get(n, ['image_url', 'image', 'img'], '');
      const tags = n.tags || n.rubrics || [];

      const card = document.createElement('article');
      card.className = 'news-card';
      card.innerHTML = `
        ${image ? `<div class="news-card-image-wrap"><img src="${image}" alt="" class="news-card-image" loading="lazy"/></div>` : ''}
        <div class="news-card-body">
          <header class="news-card-header">
            <h3 class="news-card-title"><a href="article.html?id=${encodeURIComponent(id)}">${title}</a></h3>
            <div class="news-card-meta">
              ${date ? `<span class="news-card-meta-item">${date}</span>` : ''}
              ${source ? `<span class="news-card-meta-item">${source}</span>` : ''}
            </div>
          </header>
          ${summary ? `<p class="news-card-summary">${summary}</p>` : ''}
          <div class="news-card-footer">
            <a class="news-card-link" href="article.html?id=${encodeURIComponent(id)}">Читать полностью</a>
            <div class="news-card-tags">
              ${Array.isArray(tags) ? tags.map(t => `<button type="button" class="tag-badge" data-tag="${String(t)}">${String(t)}</button>`).join('') : ''}
            </div>
          </div>
        </div>
      `;
      els.list.appendChild(card);
    });
  }

  async function loadNews() {
    try {
      const r = await fetch(NEWS_URL, { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP '+r.status);
      const data = await r.json();
      allNews = Array.isArray(data) ? data : data.items || data.news || [];
      // сортируем от новых к старым, если есть дата
      allNews.sort((a,b)=> {
        const da = +new Date(get(a, ['published_at','date','pub_date'])||0);
        const db = +new Date(get(b, ['published_at','date','pub_date'])||0);
        return db - da;
      });
      buildRubrics(allNews);
      buildTopTags(allNews);
      render();
    } catch (e) {
      console.error('Не удалось загрузить новости', e);
      els.error.hidden = false;
    } finally {
      els.loading.style.display = 'none';
    }
  }

  // events
  els.search?.addEventListener('input', (e)=>{ searchQuery = e.target.value || ''; render(); });
  els.rubricFilters?.addEventListener('click', (e)=>{
    const b = e.target.closest('button[data-rubric]'); if (!b) return;
    activeRubric = b.dataset.rubric || null;
    for (const x of els.rubricFilters.querySelectorAll('.chip')) x.classList.toggle('chip-active', x===b);
    render();
  });
  els.list?.addEventListener('click', (e)=>{
    const b = e.target.closest('button.tag-badge'); if (!b) return;
    activeRubric = b.dataset.tag;
    for (const x of els.rubricFilters.querySelectorAll('.chip')) x.classList.toggle('chip-active', x.dataset.rubric===activeRubric);
    render();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
  window.addEventListener('keydown', (e)=>{ if (e.key==='/' && !e.target.closest('input,textarea')) { e.preventDefault(); els.search?.focus(); } });

  document.addEventListener('DOMContentLoaded', loadNews);
})();
