const NEWS_CANDIDATES = [
  'data/news.json',
  './data/news.json',
  './news.json',
  'specavto-portal/frontend/data/news.json'
];
const BLOCKED = ['tass.ru','www.tass.ru','tass.com','tass'];

const $ = (s,r=document)=>r.querySelector(s);

function fmtDate(iso){
  const d = new Date(iso||Date.now());
  if (Number.isNaN(+d)) return '';
  const p = n=> String(n).padStart(2,'0');
  return `${p(d.getDate())}.${p(d.getMonth()+1)}.${d.getFullYear()}, ${p(d.getHours())}:${p(d.getMinutes())}`;
}
function stripHTML(s=''){ const el=document.createElement('div'); el.innerHTML=s; return (el.textContent||'').trim(); }

function ensure(){
  const post = $('#post') || (()=>{ const n=document.createElement('main'); n.id='post'; document.body.appendChild(n); return n; })();
  const nf   = $('#nf')   || (()=>{ const n=document.createElement('div');  n.id='nf'; n.hidden=true; n.textContent='Новость не найдена'; document.body.appendChild(n); return n; })();
  const actions = $('#bottom-actions') || (()=>{ const n=document.createElement('div'); n.id='bottom-actions'; n.hidden=true; n.innerHTML='<a href="index.html">← Вернуться к ленте</a>'; document.body.appendChild(n); return n; })();

  if (!$('#__article_inline_styles')) {
    const css = `
      .title{font-size:28px;line-height:1.2;margin:0 0 6px;font-weight:800}
      .meta{color:#6b7280;font-size:13px;display:flex;gap:6px;align-items:center;margin-bottom:10px}
      .cover{margin:12px 0 14px;border-radius:14px;overflow:hidden;background:#f2f4f7}
      .cover img{width:100%;height:auto;display:block}
      .lead{font-size:18px;line-height:1.6;margin:16px 0 8px;display:-webkit-box;-webkit-line-clamp:7;-webkit-box-orient:vertical;overflow:hidden}
    `.trim();
    const st=document.createElement('style'); st.id='__article_inline_styles'; st.textContent=css; document.head.appendChild(st);
  }
  return {post,nf,actions};
}

function isBlocked(it){
  const d = String(it?.domain||'').toLowerCase();
  const u = String(it?.url||'').toLowerCase();
  return BLOCKED.some(b => d.includes(b) || u.includes(b));
}

async function loadJSON(){
  for (const url of NEWS_CANDIDATES){
    try{
      const res = await fetch(url, { cache: 'no-store' });
      if (res.ok) return await res.json();
    }catch{}
  }
  return [];
}

function getId(){
  const url = new URL(location.href);
  return url.searchParams.get('id');
}

function pickItem(list){
  const id = getId();
  if (id != null){
    const n = Number(id);
    if (Number.isFinite(n) && list[n]) return list[n];
    const byId = list.find(x => String(x.id) === String(id));
    if (byId) return byId;
  }
  try{
    const raw = localStorage.getItem('currentArticle');
    if (raw) return JSON.parse(raw);
  }catch{}
  return null;
}

function render(item){
  const {post,nf,actions} = ensure();

  if (!item || isBlocked(item)){
    nf.hidden = false; actions.hidden = false; post.innerHTML = ''; return;
  }

  const html = `
    <h1 class="title">${item.title || ''}</h1>
    <div class="meta">
      ${item.domain ? `<span>${item.domain}</span>` : ``}
      ${item.date ? `<span>•</span><time>${fmtDate(item.date)}</time>` : ``}
    </div>
    ${item.image ? `<div class="cover"><img src="${item.image}" alt=""></div>` : ``}
    ${item.summary ? `<p class="lead">${stripHTML(item.summary)}</p>` : ``}
  `;
  post.innerHTML = html;
  actions.hidden = false;
}

async function main(){
  const list = await loadJSON();
  const item = pickItem(list);
  render(item);
}
document.addEventListener('DOMContentLoaded', main);
