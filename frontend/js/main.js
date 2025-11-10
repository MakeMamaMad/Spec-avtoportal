/* frontend/js/main.js
 * Инициализация страницы: загружаем /data/news.json и вызываем paint()
 * (paint() определяется в news.js). Есть мягкий live-poll по news_meta.json.
 */

(function () {
  'use strict';

  // ---------- Глобальное состояние ----------
  window.STATE = window.STATE || {
    all: [],     // все новости
    per: 24,     // карточек на странице
    page: 1      // текущая страница
  };

  // ---------- Утилиты ----------
  function getParam(name) {
    try { return new URLSearchParams(location.search).get(name); }
    catch { return null; }
  }

  function fetchJSON(url, opts) {
    return fetch(url, opts).then(r => {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  async function fetchJSONWithFallback(paths) {
    for (const p of paths) {
      try {
        return await fetchJSON(p, { cache: 'no-cache' });
      } catch (_) { /* попробуем следующий путь */ }
    }
    throw new Error('No JSON found in fallbacks: ' + paths.join(', '));
  }

  // Нормализация записи новости — аккуратно и без падений
  function normalizeItem(x) {
    const link = x.link || x.url || '';
    let domain = x.domain;
    if (!domain && link) {
      try { domain = new URL(link).hostname; } catch { domain = ''; }
    }

    const published =
      x.published_at || x.pubDate || x.date || x.time || x.created_at || null;

    let dateObj = null;
    if (published) {
      try { dateObj = new Date(published); } catch { /* noop */ }
    }
    if (!(dateObj instanceof Date) || isNaN(+dateObj)) {
      dateObj = new Date(0); // очень старое, если дата нечитабельна
    }

    // предпросмотр картинки: image либо enclosure.url
    const image =
      x.image ?? (x.enclosure && (x.enclosure.url || x.enclosure.link)) ?? null;

    return {
      ...x,
      title: x.title || '',
      link,
      domain: domain || '',
      date: dateObj,
      image
    };
  }

  // ---------- Live poll по news_meta.json (опционально) ----------
  function startLivePoll() {
    let lastUpdated = null;

    async function tick() {
      try {
        const meta = await fetchJSONWithFallback([
          '/data/news_meta.json',
          './data/news_meta.json',
          'data/news_meta.json'
        ]);
        if (!meta || !meta.updated_at) return;

        if (meta.updated_at !== lastUpdated) {
          lastUpdated = meta.updated_at;
          const data = await fetchJSONWithFallback([
            '/data/news.json',
            './data/news.json',
            'data/news.json'
          ]);
          if (Array.isArray(data)) {
            STATE.all = data.map(normalizeItem).sort((a, b) => b.date - a.date);
            console.log('[live] refresh:', STATE.all.length);
            if (typeof window.paint === 'function') window.paint();
          }
        }
      } catch (e) {
        console.warn('[live] poll failed:', e.message || e);
      }
    }

    tick();                        // первая проверка сразу
    setInterval(tick, 5 * 60 * 1000); // затем раз в 5 минут
  }

  // ---------- Bootstrap ----------
  async function boot() {
    // читаем параметры страницы (не обязательно, но удобно)
    const pageParam = parseInt(getParam('page') || '1', 10);
    if (!isNaN(pageParam) && pageParam > 0) STATE.page = pageParam;

    // грузим новости
    let data = [];
    try {
      data = await fetchJSONWithFallback([
        '/data/news.json',
        './data/news.json',
        'data/news.json'
      ]);
    } catch (e) {
      console.warn('[boot] news.json not loaded:', e.message || e);
    }

    if (Array.isArray(data) && data.length) {
      STATE.all = data.map(normalizeItem).sort((a, b) => b.date - a.date);
      console.log('NEWS LOADED:', STATE.all.length);

      // сразу рисуем карточки (реализация paint в news.js)
      if (typeof window.paint === 'function') {
        window.paint();
      } else {
        console.warn('paint() is not defined yet (news.js not loaded?)');
      }
    } else {
      console.warn('[boot] empty data array — nothing to render');
    }

    // включаем лайв-обновления, если добавлен ?live=1
    if (getParam('live') === '1') {
      startLivePoll();
    }
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
