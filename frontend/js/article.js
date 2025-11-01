// frontend/js/article.js

function hashId(s=''){ let h=0; for(let i=0;i<s.length;i++) h=((h<<5)-h+s.charCodeAt(i))|0; return 'n'+Math.abs(h).toString(36); }
function fmtDateTime(d){ const dd=String(d.getDate()).padStart(2,'0'); const mm=String(d.getMonth()+1).padStart(2,'0'); const yyyy=d.getFullYear(); const hh=String(d.getHours()).padStart(2,'0'); const mi=String(d.getMinutes()).padStart(2,'0'); return `${dd}.${mm}.${yyyy}, ${hh}:${mi}`; }
function escapeHtml(s=''){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}

function normalizeItem(it){
  const link = it.link || it.url || '#';
  const dateStr = it.published_at || it.published || it.updated_at || it.created_at || it.date || it.pubDate;
  let domain = it.domain;
  if (!domain && link && link !== '#'){ try{ domain = new URL(link).hostname; }catch(_){ domain=''; } }
  return {
    id: hashId(link),
    title: it.title || '(без заголовка)',
    source: it.source || it.site || domain || 'Источник',
    link,
    summary: (it.summary || it.description || '').trim(),
    content_html: it.content_html || null,
    image: it.image || it.thumbnail || null,
    date: dateStr ? new Date(dateStr) : new Date(),
    domain
  };
}

function toParagraphs(text){
  if (!text) return '';
  let t = text.replace(/\r/g,'').replace(/\n{3,}/g,'\n\n').trim();
  const looksHTML = /<\/?[a-z][\s\S]*>/i.test(t);
  if (looksHTML) return t; // сервер уже положил html
  const parts = t.split(/\n\n+/).map(p=>p.trim()).filter(Boolean);
  return parts.map(p=>`<p>${escapeHtml(p)}</p>`).join('');
}

async function loadNews(){
  const res = await fetch('data/news.json?v='+Date.now(), {cache:'no-store'});
  if (!res.ok) throw new Error('Не удалось загрузить news.json');
  const raw = await res.json();
  return raw.map(normalizeItem);
}

async function init(){
  const mount = document.getElementById('article');
  const u = new URL(window.location.href);
  const id = u.searchParams.get('id');
  if (!id){ mount.innerHTML = '<p>Не указан id новости.</p>'; return; }

  const items = await loadNews();
  const item = items.find(x => x.id === id) || items.find(x => decodeURIComponent(id) === x.link);
  if (!item){ mount.innerHTML = '<p>Новость не найдена.</p>'; return; }

  const bodyHtml = item.content_html ? item.content_html : toParagraphs(item.summary);

  mount.innerHTML = `
    <h1>${escapeHtml(item.title)}</h1>
    <div class="meta"><span>${escapeHtml(item.source)}</span><span> • ${fmtDateTime(item.date)}</span></div>
    <div class="cover">${item.image ? `<img src="${item.image}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ``}</div>
    <div class="desc">${bodyHtml || ''}</div>
    <div class="actions">
      <a class="btn" href="./">← Вернуться к новостям</a>
      <a class="btn primary" href="${item.link}" target="_blank" rel="noopener">Читать в источнике</a>
    </div>
  `;
}
document.addEventListener('DOMContentLoaded', ()=>{ init().catch(err=>{
  const mount=document.getElementById('article');
  mount.innerHTML=`<p>Ошибка: ${escapeHtml(err.message)}</p>`;
}); });
