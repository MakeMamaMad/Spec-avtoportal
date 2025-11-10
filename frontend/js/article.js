const NEWS_URL = 'data/news.json';
const BLOCKED = ['tass.ru', 'www.tass.ru'];

const $ = (sel, root = document) => root.querySelector(sel);

function fmtDate(iso) {
  const d = new Date(iso || Date.now());
  if (Number.isNaN(+d)) return '';
  const p = (n) => String(n).padStart(2,'0');
  return `${p(d.getDate())}.${p(d.getMonth()+1)}.${d.getFullYear()}, ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function ensureScaffold(){
  const post = $('#post') || (()=>{ const n=document.createElement('main'); n.id='post'; document.body.appendChild(n); return n; })();
  const nf   = $('#nf')   || (()=>{ const n=document.createElement('div'); n.id='nf'; n.hidden=true; n.textContent='Новость не найдена'; document.body.appendChild(n); return n; })();
  const actions = $('#bottom-actions') || (()=>{ const n=document.createElement('div'); n.id='bottom-actions'; n.hidden=true; n.innerHTML='<a href="index.html">← Вернуться к ленте</a>'; document.body.appendChild(n); return n; })();

  if (!$('#__article_inline_styles')) {
    const css = `
      .title{font-size:28px;line-height:1.2;margin:0 0 6px;font-weight:800}
      .meta{color:#6b7280;font-size:13px;display:flex;gap:6px;align-items:center;margin-bottom:10px}
      .cover{margin:12px 0 14px;border-radius:14px;overflow:hidden;background:#f2f4f7}
      .cover img{width:100%;height:auto;display:block}
      .lead{font-size:18px;line-height:1.6;margin:16px 0 8px;display:-webkit-box;-webkit-line-clamp:7;-webkit-box-orient:vertical;overflow:hidden}
    `.trim();
    const style = document.createElement('style');
    style.id = '__article_inline_styles';
    style.textContent = css;
    document.head.appendChild(style);
  }

  return { post, nf, actions };
}

function isBlocked(it){
  const d = (it?.domain || '').toLowerCase();
  const u = (it?.url || '').toLowerCase();
  return BLOCKED.some(b => d.includes(b) || u.includes(b));
}

async function loadAll(){
  const res = await fetch(NEWS_URL, { cache: 'no-store' });
  if (!res.ok) return [];
  try { return await res.json(); } catch { return []; }
}

function getIdFromURL(){
  const url = new URL(location.href);
  return url.searchParams.get('id') || null;
}

function pickItem(list){
  // 1) по ?id=
  const id = getIdFromURL();
  if (id != null) {
    const idx = Number.isFinite(+id) ? +id : null;
    if (idx != null && list[idx]) return list[idx];
    // пробуем найти по полю id, если оно есть
    const byId = list.find(x => String(x.id) === String(id));
    if (byId) return byId;
  }

  // 2) из localStorage — записывается при клике в ленте
  try {
    const raw = localStorage.getItem('currentArticle');
    if (raw) return JSON.parse(raw);
  } catch {}

  return null;
}

function render(item){
  const { post, nf, actions } = ensureScaffold();

  if (!item || isBlocked(item)) {
    nf.hidden = false;
    actions.hidden = false;
    post.innerHTML = '';
    return;
  }

  const dateStr = item.date ? fmtDate(item.date) : '';
  const meta = `
    <div class="meta">
      ${item.domain ? `<span>${item.domain}</span>` : ``}
      ${dateStr ? `<span>•</span><time>${dateStr}</time>` : ``}
    </div>
  `;
  const html = `
    <h1 class="title">${item.title || ''}</h1>
    ${meta}
    ${item.image ? `<div class="cover"><img src="${item.image}" alt=""></div>` : ``}
    ${item.summary ? `<p class="lead">${item.summary}</p>` : ``}
  `;

  post.innerHTML = html;
  actions.hidden = false;
}

async function main(){
  const list = await loadAll();
  const item = pickItem(list);
  render(item);
}

document.addEventListener('DOMContentLoaded', main);
