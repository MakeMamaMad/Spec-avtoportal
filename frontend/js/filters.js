export const SUBRUBRICS = [
  "Выставки","Новые модели","Новые производители","Рынок","Уникальные факты",
  "Производители грузовиков/моторов","Дилеры"
];
export function filterBySubrubric(items, sub){
  if(!sub || sub==="Все") return items;
  return items.filter(i => i.category === sub);
}
export function topTags(items, n=10){
  const m = new Map();
  for(const it of items){
    for(const t of (it.tags||[])){
      m.set(t, (m.get(t)||0)+1);
    }
  }
  return [...m.entries()].sort((a,b)=>b[1]-a[1]).slice(0,n).map(([t])=>t);
}
