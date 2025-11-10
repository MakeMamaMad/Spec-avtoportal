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
  const d = String(it?.domain||'').toLowerCase().trim();
  const u = String(it?.url||'').toLowerCase().trim();
  return BLOCKED.some(b => d.includes(b) || u.includes(b));
}

function pickImage(item){
  const cand = item?.image || item?.cover || item?.img || (Array.isArray(item?.images) ? item.images[0] : '');
  return (typeof cand === 'string' && cand.trim()) ? cand.trim() : '';
}
function placeholderFor(item){
  const domain = (item?.domain || 'news').replace(/^https?:\/\//,'').split('/')[0];
  const label = domain.length > 18 ? domain.slice(0,18)+'…' : domain;
  const svg = `
    <svg xmlns='http://www.w3.org/2000/svg' width='640' height='360'>
      <defs><linearGradient id='g' x1='0' x2='1' y1='0' y2='1'>
        <stop stop-color='#eff3f8' offset='0'/><stop stop-color='#e6ebf2' offset='1'/>
      </linearGradient></defs>
      <rect width='100%' height='100%' fill='url(#g)'/>
      <text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle'
            font-family='Inter,system-ui,Segoe UI,Roboto,Arial' font-size='28' fill='#667085'>${label}</text>
    </svg>`;
  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
}

function render(item){
  const {post,nf,actions} = ensure();

  if (!item || isBlocked(item)){
    nf.hidden = false; actions.hidden = false; post.innerHTML = ''; return;
  }

  const img = pickImage(item);
  const cover = img
    ? `<div class="cover"><img src="${img}" loading="eager" decoding="async" referrerpolicy="no-referrer"
         onerror="this.onerror=null;this.src='${placeholderFor(item)}'"></div>`
    : ``;

  const html = `
    <h1 class="title">${item.title || ''}</h1>
    <div class="meta">
      ${item.domain ? `<span>${item.domain}</span>` : ``}
      ${item.date ? `<span>•</span><time>${fmtDate(item.date)}</time>` : ``}
    </div>
    ${cover}
    ${item.summary ? `<p class="lead">${stripHTML(item.summary)}</p>` : ``}
  `;
  post.innerHTML = html;
  actions.hidden = false;
}

function getId(){
  const url = new URL(location.href);
  return url.searchParams.get('id');
}

function pickFromLocal(){
  try{
    const raw = localStorage.getItem('currentArticle');
    if (raw) return JSON.parse(raw);
  }catch{}
  return null;
}

async function main(){
  // мгновенный рендер из кеша
  const cached = pickFromLocal();
  if (cached) render(cached);

  // если открыли страницу без клика — пробуем достать из window.__ALL_NEWS__
  if (!cached && Array.isArray(window.__ALL_NEWS__)) {
    const id = getId();
    const n = Number(id);
    const list = window.__ALL_NEWS__;
    if (Number.isFinite(n) && list[n]) render(list[n]);
    else {
      const byId = list.find(x => String(x.id) === String(id));
      if (byId) render(byId);
    }
  }
}
document.addEventListener('DOMContentLoaded', main);
