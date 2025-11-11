// article.js v11 — быстрый рендер, правильная ссылка «Читать в источнике»

const BLOCKED = ['tass.ru','www.tass.ru','tass.com','tass'];
const $ = (s,r=document)=>r.querySelector(s);

function fmtDate(iso){ const d=new Date(iso||Date.now()); if(Number.isNaN(+d))return''; const p=n=>String(n).padStart(2,'0'); return `${p(d.getDate())}.${p(d.getMonth()+1)}.${p(d.getHours())}:${p(d.getMinutes())}`.replace('..', '.'); }
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
    <rect width='100%' height='100%' fill='#eef2f7'/><text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle'
    font-family='Inter,system-ui,Segoe UI,Roboto,Arial' font-size='28' fill='#667085'>${label}</text></svg>`;
  return 'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);
}

// нормализуем URL источника: если без протокола — добавим домен
function buildSourceUrl(item) {
  let u = (item && item.url) ? String(item.url).trim() : '';
  const d = (item && item.domain) ? String(item.domain).replace(/^https?:\/\//,'').split('/')[0] : '';
  if (!u) return '';
  if (/^https?:\/\//i.test(u)) return u;
  if (u.startsWith('//')) return 'https:' + u;
  if (d) return `https://${d}${u.startsWith('/') ? u : '/' + u}`;
  return '';
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

  // Читать в источнике
  const readBtn = document.getElementById('read-source');
  if (readBtn) {
    const src = buildSourceUrl(item);
    if (src) {
      readBtn.href = src;
      readBtn.target = '_blank';
      readBtn.rel = 'noopener noreferrer';
      readBtn.hidden = false;
      readBtn.onclick = (e) => { e.stopPropagation(); }; // не мешаем другим обработчикам
    } else {
      readBtn.hidden = true;
    }
  }
}

function getId(){ const u=new URL(location.href); return u.searchParams.get('id'); }
function pickFromLocal(){ try{ const raw=localStorage.getItem('currentArticle'); if(raw) return JSON.parse(raw); }catch{} return null; }

document.addEventListener('DOMContentLoaded', () => {
  const cached = pickFromLocal();
  if (cached) render(cached);

  if (!cached && Array.isArray(window.__ALL_NEWS__)) {
    const id = getId();
    const n = Number(id);
    const list = window.__ALL_NEWS__;
    if (Number.isFinite(n) && list[n]) render(list[n]);
    else {
      const byId = list.find(x => String(x?.id) === String(id));
      if (byId) render(byId);
    }
  }
});
