import {html, timeAgo} from "../utils.js";

export function NewsCard(item){
  const badges = item.tags?.slice(0,3).map(t => `<span class='badge'>${t}</span>`).join('') || '';
  const img = item.image
    ? `<img alt='${item.title}' src='${item.image}'>`
    : `<div style="width:100%;height:100%;background:linear-gradient(135deg, rgba(255,106,0,.16), rgba(44,182,125,.16))"></div>`;
  return html`
  <article class="card">
    <a class="media" href="article.html?id=${encodeURIComponent(item.id)}">${img}</a>
    <div class="body">
      <div class="badges"><span class="badge">${item.category}</span>${badges}</div>
      <h3><a href="article.html?id=${encodeURIComponent(item.id)}">${item.title}</a></h3>
      <p>${item.summary || ""}</p>
      <div class="meta">
        <span>${item.source?.name || "Источник"}</span>
        <span class="dot"></span>
        <span>${timeAgo(item.published_at)}</span>
      </div>
    </div>
  </article>`;
}
