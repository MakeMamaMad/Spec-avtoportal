// main.js v11 — грузит новости, вызывает paint(), устойчив к BFCache/гонкам

async function loadNews() {
const NEWS_JSON_URL = (window.fixPath ? window.fixPath('/frontend/data/news.json')
                                      : 'frontend/data/news.json');

fetch(NEWS_JSON_URL)
  .then(r => r.json())
  .then(arr => {
    console.log('NEWS LOADED (main.js):', Array.isArray(arr) ? arr.length : 0);
    // ... дальше твой код отрисовки
  })
  .catch(err => console.error('load news.json failed', err));


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
