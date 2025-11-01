import {qs} from './utils.js';

const TYPES = ["ГОСТ","ТР ТС","ПДД","Закон","ОСАГО","ТО","Приказ","Методика"];

async function load(){
  const res = await fetch('./data/regulations.json');
  const {items=[]} = await res.json();
  const chips = document.getElementById('law-chips');
  chips.innerHTML = ["Все", ...TYPES].map(t => `<div class="chip" data-t="${t}">${t}</div>`).join('');
  const tbody = document.querySelector('#law-table tbody');

  function paint(filterType="Все", q=""){
    const safeQ = (q||"").toLowerCase();
    const filtered = items.filter(it => (filterType==="Все" || it.type===filterType) &&
      (it.title.toLowerCase().includes(safeQ) || it.code.toLowerCase().includes(safeQ) || (it.keywords||[]).join(" ").toLowerCase().includes(safeQ)));
    tbody.innerHTML = filtered.map(it => `
      <tr>
        <td>${it.type}</td>
        <td>${it.code||""}</td>
        <td>${it.title}</td>
        <td>${new Date(it.date).toLocaleDateString('ru-RU')}</td>
        <td><a href="${it.url}" target="_blank" rel="noopener">Открыть</a></td>
      </tr>`).join('');
  }

  paint();
  chips.addEventListener('click', (e)=>{
    const el = e.target.closest('.chip'); if(!el) return;
    q.value="";
    q.dispatchEvent(new Event('input'));
    [...chips.children].forEach(c => c.classList.toggle('active', c===el));
    paint(el.dataset.t);
  });
  const q = document.getElementById('law-q');
  q.addEventListener('input', ()=>{
    const active = chips.querySelector('.chip.active');
    paint(active ? active.dataset.t : "Все", q.value);
  });
}

load();
