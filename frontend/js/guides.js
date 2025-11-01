import {qs} from './utils.js';

const SECTIONS = ["Подбор прицепа","Обслуживание","Тюнинг","FAQ"];

async function load(){
  const res = await fetch('./data/guides.json');
  const {items=[]} = await res.json();
  const list = document.getElementById('guides-list');
  const chips = document.getElementById('guide-chips');
  chips.innerHTML = ["Все", ...SECTIONS].map(t => `<div class="chip" data-t="${t}">${t}</div>`).join('');

  function card(it){
    return `<article class="card">
      <a class="media" href="article.html?id=${encodeURIComponent(it.id)}"><div style="width:100%;height:100%;background:linear-gradient(135deg, rgba(255,106,0,.16), rgba(44,182,125,.16))"></div></a>
      <div class="body">
        <div class="badges"><span class="badge">${it.section}</span>${(it.tags||[]).slice(0,2).map(t=>`<span class='badge'>${t}</span>`).join('')}</div>
        <h3><a href="article.html?id=${encodeURIComponent(it.id)}">${it.title}</a></h3>
        <p>${it.summary||""}</p>
      </div>
    </article>`;
  }

  function paint(section="Все"){
    const filtered = (section==="Все") ? items : items.filter(i=>i.section===section);
    list.innerHTML = filtered.map(card).join('');
  }
  paint();

  chips.addEventListener('click', (e)=>{
    const el = e.target.closest('.chip'); if(!el) return;
    [...chips.children].forEach(c => c.classList.toggle('active', c===el));
    paint(el.dataset.t);
  });
}

load();
