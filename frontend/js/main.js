// main.js v11 — грузит новости, вызывает paint(), устойчив к BFCache/гонкам

async function loadNews() {
  const url = 'data/news.json';
  try {
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
    const raw = await res.json();

    const arr = Array.isArray(raw) ? raw : (raw && Array.isArray(raw.items)) ? raw.items : [];
    console.log('NEWS LOADED (main.js):', arr.length);

    // кладём в глобал для article.js и повторной отрисовки
    window.__ALL_NEWS__ = arr;

    if (typeof window.paint === 'function') {
      console.log('main.js → calling paint(arr)');
      window.paint(arr);
    } else {
      console.warn('paint() is not defined yet (news.js not loaded?) — buffering');
      window.__pendingNews = arr;
    }
  } catch (e) {
    console.error('loadNews() failed:', e);
  }
}

// стандартный запуск
document.addEventListener('DOMContentLoaded', () => {
  loadNews();
});

// если вернулись со страницы статьи из BFCache (без перезапуска js)
// то принудительно перерисуем ЛЮБУЮ уже загруженную ленту,
// а если её нет — просто перезагрузим данные.
window.addEventListener('pageshow', (e) => {
  if (e.persisted) {
    console.log('pageshow (persisted) → restore feed');
    if (typeof window.paint === 'function' && Array.isArray(window.__ALL_NEWS__)) {
      window.paint(window.__ALL_NEWS__);
    } else {
      loadNews();
    }
  }
});
