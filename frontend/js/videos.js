async function load(){
  const res = await fetch('./data/videos.json');
  const {items=[]} = await res.json();
  const list = document.getElementById('video-list');

  function mediaClass(v){
    return v.is_short ? "media media--vertical" : "media";
  }
  function badge(v){
    const base = `<span class="badge">${v.platform||"YouTube"}</span>`;
    return v.is_short ? base + `<span class="badge">Shorts</span>` : base;
  }

  list.innerHTML = items.map(v => `
    <article class="card">
      <a class="${mediaClass(v)}" href="${v.url}" target="_blank" rel="noopener">
        ${v.thumbnail
          ? `<img src="${v.thumbnail}" alt="${v.title}">`
          : `<div style="width:100%;height:100%;
               background:linear-gradient(135deg, rgba(255,106,0,.16), rgba(44,182,125,.16))"></div>`}
      </a>
      <div class="body">
        <div class="badges">${badge(v)}</div>
        <h3><a href="${v.url}" target="_blank" rel="noopener">${v.title}</a></h3>
        <p>${v.channel||""}</p>
      </div>
    </article>`).join('');
}
load();



