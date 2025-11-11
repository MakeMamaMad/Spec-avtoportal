const BLOCKED = ['tass.ru','www.tass.ru','tass.com','tass'];
const $ = (s,r=document)=>r.querySelector(s);

function fmtDate(iso){ const d=new Date(iso||Date.now()); if(Number.isNaN(+d))return''; const p=n=>String(n).padStart(2,'0'); return `${p(d.getDate())}.${p(d.getMonth()+1)}.${d.getFullYear()}, ${p(d.getHours())}:${p(d.getMinutes())}`; }
function stripHTML(s=''){ const el=document.createElement('div'); el.innerHTML=s; return (el.textContent||'').trim(); }

function ensure(){
  const post = $('#post') || (()=>{ const n=document.createElement('main'); n.id='post'; document.body.appendChild(n); return n; })();
  const nf   = $('#nf')   || (()=>{ const n=document.createElement('div');  n.id='nf'; n.hidden=true; n.textContent='Новость не найдена'; document.body.appendChild(n); return n; })();
  const actions = $('#bottom-actions') || (()=>{ const n=document.createElement('div'); n.id='bottom-actions'; n.hidden=true; n.innerHTML='<a href="index.html">← Вернуться к ленте</a>'; document.body.appendChild(n); return n; })();
  return {post,nf,actions};
}

const isBlocked = (it)=> {
  const d=String(it?.domain||'').toLowerCase().trim();
  const u=String(it?.url||'').toLowerCase().trim();
  return BLOCKED.some(b=>d.includes(b)||u.includes(b));
};
const pickImage = (it)=> {
  const cand=it?.image||it?.cover||it?.img||(Array.isArray(it?.images)?it.images[0]:'');
  return (typeof cand==='string' && cand.trim()) ? cand.trim() : '';
};
function placeholderFor(it){
  const domain=(it?.domain||'news').replace(/^https?:\/\//,'').split('/')[0];
  const label=domain.length>18?domain.slice(0,18)+'…':domain;
  const svg=`<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360'>
    <defs><linearGradient id='g' x1='0' x2='1' y1='0' y2='1'><stop stop-color='#eff3f8' offset='0'/><stop stop-color='#e6ebf2' offset='1'/></linearGradient></defs>
    <rect width='100%' height='100%' fill='url(#g)'/>
    <text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle' font-family='Inter,system-ui,Segoe UI,Roboto,Arial' font-size='28' fill='#667085'>${label}</text>
  </svg>`;
  return 'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);
}

function render(item){
  const {post,nf,actions}=ensure();
  if(!item || isBlocked(item)){ nf.hidden=false; actions.hidden=false; post.innerHTML=''; return; }

  const img=pickImage(item);
  const cover = img ? `<div class="cover"><img src="${img}" loading="eager" decoding="async" referrerpolicy="no-referrer"
                    onerror="this.onerror=null;this.src='${placeholderFor(item)}'"></div>` : ``;

  post.innerHTML = `
    <h1 class="title">${item.title||''}</h1>
    <div class="meta">
      ${item.domain?`<span>${item.domain}</span>`:''}
      ${item.date?`<span>•</span><time>${fmtDate(item.date)}</time>`:''}
    </div>
    ${cover}
    ${item.summary?`<p class="lead">${stripHTML(item.summary)}</p>`:''}
  `;

  // Кнопки
  actions.hidden = false;
  const readBtn = document.getElementById('read-source');
  if (item.url) {
    readBtn.href = item.url;
    readBtn.hidden = false;
  } else {
    readBtn.hidden = true;
  }
}

function getId(){ const u=new URL(location.href); return u.searchParams.get('id'); }
function pickFromLocal(){ try{ const raw=localStorage.getItem('currentArticle'); if(raw) return JSON.parse(raw); }catch{} return null; }

document.addEventListener('DOMContentLoaded', () => {
  // 1) Мгновенный рендер из кеша
  const cached = pickFromLocal();
  if (cached) render(cached);

  // 2) Если открыли по прямой ссылке — попробуем из окна главной (когда переходили со страницы ленты)
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
});
