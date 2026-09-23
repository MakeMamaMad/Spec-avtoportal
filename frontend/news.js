// news.js — redesign v1
(function () {
  const NEWS_URLS = ["data/news.json", "frontend/data/news.json"];
  const PAGE_SIZE = 12;
  const $ = (id) => document.getElementById(id);
  const els = {
    list: $("news-list"), empty: $("news-empty"), loading: $("news-loading"), error: $("news-error"),
    search: $("search"), rubrics: $("rubric-filters"), topTags: $("top-tags"),
    primary: $("featured-primary"), secondary: $("featured-secondary"), featured: $("featured-section"),
    newsCount: $("news-count"), latestDate: $("latest-date"), resultCount: $("result-count"), loadMore: $("load-more")
  };

  let allNews = [];
  let activeRubric = null;
  let searchQuery = "";
  let visibleCount = PAGE_SIZE;

  function field(obj, keys, fallback) {
    for (const key of keys) if (obj && obj[key] != null && obj[key] !== "") return obj[key];
    return fallback || "";
  }

  function dateFmt(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(+d)) return "";
    return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short", year: "numeric" })
      .format(d).replace(" г.", "");
  }

  function esc(value) {
    return String(value == null ? "" : value)
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }

  function tags(item) {
    const value = item.tags || item.rubrics || [];
    return Array.isArray(value) ? value.filter(Boolean).map(String) : [];
  }

  function articleUrl(item) {
    return "article.html?i=" + encodeURIComponent(item.__index);
  }

  function normalize() {
    allNews.sort(function (a, b) {
      const da = new Date(field(a, ["published_at", "date", "pub_date"], 0)).getTime();
      const db = new Date(field(b, ["published_at", "date", "pub_date"], 0)).getTime();
      return db - da;
    });
    allNews = allNews.map(function (item, index) {
      return Object.assign({}, item, { __index: index });
    });
  }

  function counts() {
    const map = new Map();
    allNews.forEach(function (item) {
      tags(item).forEach(function (tag) { map.set(tag, (map.get(tag) || 0) + 1); });
    });
    return map;
  }

  function buildRubrics() {
    const map = counts();
    els.rubrics.innerHTML = "";
    const all = document.createElement("button");
    all.type = "button"; all.className = "chip chip-active"; all.dataset.rubric = ""; all.textContent = "Все";
    els.rubrics.appendChild(all);

    Array.from(map.entries()).sort(function (a, b) { return b[1] - a[1]; }).slice(0, 18)
      .forEach(function (pair) {
        const btn = document.createElement("button");
        btn.type = "button"; btn.className = "chip"; btn.dataset.rubric = pair[0]; btn.textContent = pair[0];
        els.rubrics.appendChild(btn);
      });
  }

  function buildTopTags() {
    const map = counts();
    els.topTags.innerHTML = "";
    Array.from(map.entries()).sort(function (a, b) { return b[1] - a[1]; }).slice(0, 10)
      .forEach(function (pair) {
        const li = document.createElement("li");
        li.textContent = pair[0] + " · " + pair[1];
        li.dataset.tag = pair[0]; li.tabIndex = 0; li.setAttribute("role", "button");
        els.topTags.appendChild(li);
      });
  }

  function featuredMarkup(item, primary) {
    const title = esc(field(item, ["title", "headline", "name"], "Без заголовка"));
    const image = esc(field(item, ["image_url", "image", "img"], ""));
    const date = dateFmt(field(item, ["published_at", "date", "pub_date"], ""));
    const source = esc(field(item, ["source_name", "source", "site"], ""));
    const tag = esc(tags(item)[0] || "Новости");
    let html = "";
    if (image) {
      html += '<a class="featured-media" href="' + articleUrl(item) + '" aria-label="' + title + '">';
      html += '<img src="' + image + '" alt="" loading="' + (primary ? "eager" : "lazy") + '"></a>';
    }
    html += '<div class="featured-content"><span class="featured-tag">' + tag + '</span>';
    html += '<h3><a href="' + articleUrl(item) + '">' + title + '</a></h3>';
    html += '<div class="featured-meta">';
    if (date) html += '<span>' + date + '</span>';
    if (source) html += '<span>' + source + '</span>';
    html += '</div></div>';
    return html;
  }

  function renderFeatured() {
    let picks = allNews.filter(function (item) { return !!field(item, ["image_url", "image", "img"], ""); });
    if (picks.length < 3) picks = allNews;
    picks = picks.slice(0, 3);
    if (!picks.length) { els.featured.hidden = true; return; }

    els.primary.classList.remove("featured-placeholder");
    els.primary.innerHTML = featuredMarkup(picks[0], true);
    els.secondary.innerHTML = picks.slice(1).map(function (item) {
      return '<article class="featured-mini">' + featuredMarkup(item, false) + '</article>';
    }).join("");
  }

  function filtered() {
    const q = searchQuery.trim().toLowerCase();
    return allNews.filter(function (item) {
      const title = String(field(item, ["title", "headline", "name"], "")).toLowerCase();
      const summary = String(field(item, ["summary", "lead", "description"], "")).toLowerCase();
      const itemTags = tags(item).map(function (t) { return t.toLowerCase(); });
      if (q && !title.includes(q) && !summary.includes(q) && !itemTags.some(function (t) { return t.includes(q); })) return false;
      if (activeRubric && !itemTags.includes(activeRubric.toLowerCase())) return false;
      return true;
    });
  }

  function card(item) {
    const title = esc(field(item, ["title", "headline", "name"], "Без заголовка"));
    const summary = esc(field(item, ["summary", "lead", "description"], ""));
    const date = dateFmt(field(item, ["published_at", "date", "pub_date"], ""));
    const source = esc(field(item, ["source_name", "source", "site"], ""));
    const image = esc(field(item, ["image_url", "image", "img"], ""));
    const itemTags = tags(item).slice(0, 3);
    let html = '<article class="news-card">';
    if (image) html += '<a class="news-card-image-wrap" href="' + articleUrl(item) + '" aria-label="' + title + '"><img src="' + image + '" alt="" class="news-card-image" loading="lazy"></a>';
    html += '<div class="news-card-body"><div class="news-card-meta">';
    if (date) html += '<span>' + date + '</span>';
    if (source) html += '<span>' + source + '</span>';
    html += '</div><h3 class="news-card-title"><a href="' + articleUrl(item) + '">' + title + '</a></h3>';
    if (summary) html += '<p class="news-card-summary">' + summary + '</p>';
    html += '<div class="news-card-footer"><a class="news-card-read" href="' + articleUrl(item) + '">Читать материал →</a><div class="news-card-tags">';
    itemTags.forEach(function (tag) {
      html += '<button type="button" class="tag-badge" data-tag="' + esc(tag) + '">' + esc(tag) + '</button>';
    });
    html += '</div></div></div></article>';
    return html;
  }

  function render() {
    const data = filtered();
    const visible = data.slice(0, visibleCount);
    els.resultCount.textContent = data.length ? data.length.toLocaleString("ru-RU") + " материалов" : "";
    els.list.innerHTML = visible.map(card).join("");
    els.empty.hidden = data.length !== 0;
    els.loadMore.hidden = visibleCount >= data.length;
    if (!els.loadMore.hidden) els.loadMore.textContent = "Показать ещё · " + Math.min(PAGE_SIZE, data.length - visibleCount);
  }

  function setRubric(tag) {
    activeRubric = tag || null;
    visibleCount = PAGE_SIZE;
    els.rubrics.querySelectorAll(".chip").forEach(function (chip) {
      chip.classList.toggle("chip-active", (chip.dataset.rubric || "") === (tag || ""));
    });
    render();
  }

  function setupEvents() {
    els.search.addEventListener("input", function (e) { searchQuery = e.target.value || ""; visibleCount = PAGE_SIZE; render(); });
    els.rubrics.addEventListener("click", function (e) {
      const btn = e.target.closest("button[data-rubric]"); if (btn) setRubric(btn.dataset.rubric || null);
    });
    els.list.addEventListener("click", function (e) {
      const btn = e.target.closest("button.tag-badge");
      if (btn) { setRubric(btn.dataset.tag || null); $("latest").scrollIntoView({ behavior: "smooth" }); }
    });
    els.topTags.addEventListener("click", function (e) {
      const li = e.target.closest("li[data-tag]");
      if (li) { setRubric(li.dataset.tag); $("latest").scrollIntoView({ behavior: "smooth" }); }
    });
    els.loadMore.addEventListener("click", function () { visibleCount += PAGE_SIZE; render(); });
    window.addEventListener("keydown", function (e) {
      if (e.key === "/" && !e.target.closest("input, textarea")) { e.preventDefault(); els.search.focus(); }
    });
  }

  async function loadNews() {
    for (const url of NEWS_URLS) {
      try {
        const resp = await fetch(url, { cache: "no-store" });
        if (!resp.ok) continue;
        const data = await resp.json();
        allNews = Array.isArray(data) ? data : (data.items || []);
        if (allNews.length) break;
      } catch (_) {}
    }

    if (!allNews.length) {
      els.loading.hidden = true;
      els.error.hidden = false;
      return;
    }

    normalize();
    buildRubrics();
    buildTopTags();
    renderFeatured();
    els.newsCount.textContent = allNews.length.toLocaleString("ru-RU");
    els.latestDate.textContent = dateFmt(field(allNews[0], ["published_at", "date", "pub_date"], "")) || "сегодня";
    render();
    els.loading.hidden = true;
  }

  document.addEventListener("DOMContentLoaded", function () {
    setupEvents();
    loadNews();
  });
})();