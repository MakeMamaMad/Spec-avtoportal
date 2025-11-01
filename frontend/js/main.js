import {CONFIG} from './config.js';
import {qs, qsa} from './utils.js';
import {renderNews, renderChips, renderTagsTop} from './render.js';
import {SUBRUBRICS, filterBySubrubric, topTags} from './filters.js';

const state = {
  all: [],
  filtered: [],
  sub: "Все"
};

async function load(){
  const res = await fetch(`${CONFIG.DATA_BASE}/news.json`);
  const data = await res.json();
  console.log("NEWS LOADED:", data.items?.length, data);
  state.all = data.items || [];
  state.filtered = state.all;
  paint();
}

function paint(){
  const listEl = qs('#news-list');
  renderNews(state.filtered, listEl);
  renderChips(["Все", ...SUBRUBRICS], qs('#chips'), state.sub, (v)=>{
    state.sub = v;
    state.filtered = filterBySubrubric(state.all, v);
    paint();
  });
  renderTagsTop(topTags(state.all, 12), qs('#top-tags'));
}

load();

// Поиск по нажатию /
window.addEventListener('keydown', (e)=>{
  if(e.key==='/'){
    e.preventDefault();
    const q = prompt('Поиск по заголовкам:');
    if(q){
      const s = q.trim().toLowerCase();
      state.filtered = state.all.filter(it => it.title.toLowerCase().includes(s));
      paint();
    }
  }
});
