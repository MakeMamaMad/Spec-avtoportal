/* Рендер одной статьи. Ожидает query:
   - id: стабильный id (из news.js/main.js)
   - u : исходная ссылка (urlencoded)
   - from: номер страницы ленты (для возврата)
*/

(function () {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);

  // ---------- url params ----------
  const params = new URLSearchParams(location.search);
  const idParam = params.get('id') || '';
  const srcUrl = (() => {
    try { return decodeURIComponent(params.get('u') || ''); } catch { return ''; }
  })();
  const fromPage = params.get('from');

  // назначим ссылку «назад»
  const backBtn = $('#backBtn');
  if (fromPage) {
    const u = new URL('index.html', location.href);
    u.searchParams.set('page', fromPage);
    backBtn.href = u.toString();
  }

  // кнопка «Читать в источнике»
  const srcBtn = $('#srcBtn');
  if (srcUrl) srcBtn.href = srcUrl;

  // ---------- загрузка данных ----------
  async function loadJson(path) {
    const resp = await fetch(path, { cache: 'no-store' });
    if (!resp.ok) throw new Error('fetch failed ' + path);
    return await resp.json();
  }

  function normalizeItems(list) {
    const out = [];
    for (const it of list || []) {
      if (!it) continue;
      const date = it.published_at || it.date || it.publishedAt;
      const d = date ? new Date(date) : null;
      out.push({
        _id: it._id || makeId(it),
        title: it.title || '',
        link: it.link || '',
        domain: it.domain || (it.link ? new URL(it.link).hostname : ''),
        date: d ? d.toISOString() : '',
        image: it.image || null,
        summary: it.summary || '',
        content_html: it.content_html || it.content || ''
      });
    }
    return out;
  }

  // тот же FNV хэш, что и в news.js
  function makeId(item) {
    const base = (item.link || '') + '|' + (item.title || '') + '|' + (+new Date(item.published_at || item.date || '') || 0);
    let h = 2166136261 >>> 0;
    for (let i = 0; i < base.length; i++) {
      h ^= base.charCodeAt(i);
      h = Math.imul(h, 16777619) >>> 0;
    }
    return h.toString(16);
  }

  function pickItem(all) {
    if (idParam) {
      const found = all.find(n => n._id === idParam);
      if (found) return found;
    }
    if (srcUrl) {
      const found = all.find(n => n.link === srcUrl);
      if (found) return found;
    }
    return null;
  }

  function sanitize(html) {
    // Простой ограниченный беллист: убираем <script>, on* атрибуты и iframes.
    const tpl = document.createElement('template');
    tpl.innerHTML = html || '';
    const bad = ['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'EMBED'];
    const walker = document.createTreeWalker(tpl.content, NodeFilter.SHOW_ELEMENT, null);
    let node;
    while ((node = walker.nextNode())) {
      if (bad.includes(node.tagName)) {
        node.remove();
        continue;
      }
      // вычистим on* обработчики
      [...node.attributes].forEach(a => {
        if (/^on/i.test(a.name)) node.removeAttribute(a.name);
      });
      // изображения: загружаем «лениво»
      if (node.tagName === 'IMG' && !node.hasAttribute('loading')) {
        node.setAttribute('loading', 'lazy');
      }
    }
    return tpl.innerHTML;
  }

  function fmtDate(d) {
    if (!d) return '';
    try {
      const dd = new Date(d);
      const pad = n => String(n).padStart(2, '0');
      return `${pad(dd.getDate())}.${pad(dd.getMonth()+1)}.${dd.getFullYear()}, ${pad(dd.getHours())}:${pad(dd.getMinutes())}`;
    } catch { return ''; }
  }

  function render(item) {
    const post = $('#post');
    const nf = $('#nf');
    const actions = $('#bottom-actions');

    if (!item) {
      nf.hidden = false;
      actions.hidden = false; // оставить «назад»
      return;
    }

    const dateStr = fmtDate(item.date);

    const html = `
      <h1 class="title">${item.title || ''}</h1>
      <div class="meta">
        ${item.domain ? `<span>${item.domain}</span>` : ''}
        ${dateStr ? `<span>•</span><time>${dateStr}</time>` : ''}
      </div>

      ${item.image ? `
      <div class="cover">
        <img src="${item.image}" loading="eager" alt="">
      </div>` : ''}

      <div class="content">${sanitize(item.content_html || item.summary || '')}</div>
    `;
    post.innerHTML = html;

    // показать нижние кнопки
    actions.hidden = false;
  }

  async function main() {
    try {
      const data = await loadJson('data/news.json');
      const all = normalizeItems(data);
      render(pickItem(all));
    } catch (e) {
      console.error(e);
      render(null);
    }
  }

  main();
})();
