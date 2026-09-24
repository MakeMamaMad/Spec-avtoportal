// news.js — redesign v1
(function () {
  const NEWS_URLS = ["data/news-index.json", "frontend/data/news-index.json"];
  const PAGE_SIZE = 12;
  const TOPICS = [
    { slug: "rynok-i-proizvodstvo", name: "Рынок и производство", needles: ["рынок","продаж","производ","завод","manufactur"] },
    { slug: "gruzovaya-tehnika", name: "Грузовая техника", needles: ["маз","камаз","тягач","грузовик","truck"] },
    { slug: "pritsepnaya-tehnika", name: "Прицепная техника", needles: ["полуприцеп","прицеп","trailer"] },
    { slug: "sobytiya-otrasli", name: "События отрасли", needles: ["выстав","форум","конференц","expo","show"] },
    { slug: "novye-tehnologii", name: "Новые технологии", needles: ["электр","водород","батар","автомат","робот","цифров"] },
    { slug: "tamozhnya-i-logistika", name: "Таможня и логистика", needles: ["тамож","границ","логист","перевоз"] }
  ];
  const $ = (id) => document.getElementById(id);
  const els = {
    list: $("news-list"), loading: $("news-loading"), error: $("news-error"),
    search: $("search"), rubrics: $("rubric-filters"), topTags: $("top-tags"),
    primary: $("featured-primary"), secondary: $("featured-secondary"), featured: $("featured-section"),
    newsCount: $("news-count"), latestDate: $("latest-date"), resultCount: $("result-count"), loadMore: $("load-more"),
    scroller: $("news-scroll")
  };

  let allNews = [];
  let activeRubric = null;
  let searchQuery = "";
  let visibleCount = PAGE_SIZE;
  let loadObserver = null;
  let autoLoadPending = false;

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

  function cleanText(value) {
    if (!value) return "";
    const box = document.createElement("div");
    box.innerHTML = String(value);
    box.querySelectorAll("script, style, iframe, figure, img, figcaption").forEach(function (node) {
      node.remove();
    });
    return (box.textContent || box.innerText || "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function clampText(value, limit) {
    const text = cleanText(value);
    if (text.length <= limit) return text;
    const slice = text.slice(0, limit - 1);
    const cleanCut = slice.replace(/\s+\S*$/, "").trim();
    return (cleanCut || slice.trim()) + "…";
  }

  function summaryText(item) {
    const direct = ["summary", "lead", "description"];
    for (const key of direct) {
      const text = cleanText(item && item[key]);
      if (text) return text;
    }

    const original = cleanText(item && item.original_summary);
    if (original && (!item.translation_status || /[А-Яа-яЁё]/.test(original))) {
      return original;
    }
    return "";
  }

  function tags(item) {
    const value = item.tags || item.rubrics || [];
    return Array.isArray(value) ? value.filter(Boolean).map(String) : [];
  }

  function topics(item) {
    const haystack = (
      String(field(item, ["title", "headline", "name"], "")) + " " +
      summaryText(item)
    ).toLowerCase();
    return TOPICS.filter(function (topic) {
      return topic.needles.some(function (needle) { return haystack.includes(needle); });
    });
  }

  function articleImage(item) {
    const value = String(field(item, ["image_url", "image", "img"], "") || "").trim();
    return /^https?:\/\//i.test(value) ? value : "";
  }

  function articleUrl(item) {
    const slug = String(item.slug || "").trim();
    return slug ? "/news/" + encodeURIComponent(slug) + "/" : "/";
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
      topics(item).forEach(function (topic) {
        map.set(topic.name, (map.get(topic.name) || 0) + 1);
      });
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
        const topic = TOPICS.find(function (item) { return item.name === pair[0]; });
        if (!topic) return;
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = "topics/" + topic.slug + "/";
        a.textContent = pair[0] + " · " + pair[1];
        li.appendChild(a);
        els.topTags.appendChild(li);
      });
  }

  function featuredMarkup(item, primary) {
    const title = esc(field(item, ["title", "headline", "name"], "Без заголовка"));
    const summary = esc(clampText(summaryText(item), primary ? 230 : 115));
    const image = esc(articleImage(item));
    const date = dateFmt(field(item, ["published_at", "date", "pub_date"], ""));
    const source = esc(field(item, ["source_name", "source", "site"], ""));
    const tag = esc(tags(item)[0] || "Новости");
    let html = "";
    if (image) {
      html += '<a class="featured-media" href="' + articleUrl(item) + '" aria-label="' + title + '">';
      html += '<img src="' + image + '" alt="" class="featured-image" loading="' + (primary ? "eager" : "lazy") + '" onerror="this.closest(\'.featured-media\').remove()"></a>';
    }
    html += '<div class="featured-content"><div class="featured-topline"><span class="featured-tag">' + tag + '</span></div>';
    html += '<h3><a href="' + articleUrl(item) + '">' + title + '</a></h3>';
    if (summary) html += '<p class="featured-summary">' + summary + '</p>';
    html += '<div class="featured-meta">';
    if (date) html += '<span>' + date + '</span>';
    if (source) html += '<span>' + source + '</span>';
    html += '</div></div>';
    return html;
  }

  function renderFeatured() {
    let picks = allNews.filter(function (item) { return !!articleImage(item); }).slice(0, 3);
    if (picks.length < 3) {
      const used = new Set(picks.map(function (item) { return item.__index; }));
      allNews.some(function (item) {
        if (!used.has(item.__index)) picks.push(item);
        return picks.length >= 3;
      });
    }
    if (!picks.length) { els.featured.hidden = true; return; }

    picks = picks.map(function (item, index) {
      return Object.assign({}, item, { __featuredPos: index + 1 });
    });

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
      const summary = summaryText(item).toLowerCase();
      const itemTags = tags(item).map(function (t) { return t.toLowerCase(); });
      const itemTopics = topics(item).map(function (topic) { return topic.name.toLowerCase(); });
      if (q && !title.includes(q) && !summary.includes(q) && !itemTags.some(function (t) { return t.includes(q); }) && !itemTopics.some(function (t) { return t.includes(q); })) return false;
      if (activeRubric && !itemTopics.includes(activeRubric.toLowerCase())) return false;
      return true;
    });
  }

  function card(item, position, total) {
    const title = esc(field(item, ["title", "headline", "name"], "Без заголовка"));
    const summary = esc(clampText(summaryText(item), position === 0 ? 320 : 220));
    const date = dateFmt(field(item, ["published_at", "date", "pub_date"], ""));
    const source = esc(field(item, ["source_name", "source", "site"], ""));
    const itemTags = tags(item).slice(0, 3);
    const itemTopics = topics(item);
    const primaryTag = esc((itemTopics[0] && itemTopics[0].name) || itemTags[0] || "Новости");
    const lead = position === 0;
    const cardsAfterLead = Math.max(0, total - 1);
    const wide = position === total - 1 && position > 0 && cardsAfterLead % 2 === 1;
    let html = '<article class="news-card' + (lead ? ' news-card--lead' : '') + (wide ? ' news-card--wide' : '') + '">';
    html += '<div class="news-card-body"><span class="news-card-category">' + primaryTag + '</span><div class="news-card-meta">';
    if (date) html += '<span>' + date + '</span>';
    if (source) html += '<span>' + source + '</span>';
    html += '</div><h3 class="news-card-title"><a href="' + articleUrl(item) + '">' + title + '</a></h3>';
    if (summary) html += '<p class="news-card-summary">' + summary + '</p>';
    html += '<div class="news-card-footer"><a class="news-card-read" href="' + articleUrl(item) + '">Открыть материал <span>↗</span></a><div class="news-card-tags">';
    itemTags.slice(1).forEach(function (tag) {
      html += '<button type="button" class="tag-badge" data-tag="' + esc(tag) + '">' + esc(tag) + '</button>';
    });
    html += '</div></div></div></article>';
    return html;
  }

  function render() {
    const data = filtered();
    const visible = data.slice(0, visibleCount);
    els.resultCount.textContent = data.length ? data.length.toLocaleString("ru-RU") + " материалов" : "";
    els.list.innerHTML = visible.map(function (item, index) { return card(item, index, visible.length); }).join("");
    els.loadMore.hidden = visibleCount >= data.length;
    if (!els.loadMore.hidden) els.loadMore.textContent = "Показать больше новостей";
  }

  function resumeAutoLoad() {
    autoLoadPending = false;
    if (loadObserver && !els.loadMore.hidden) {
      loadObserver.observe(els.loadMore);
    }
  }

  function loadNextPage() {
    if (autoLoadPending) return;
    const total = filtered().length;
    if (visibleCount >= total) return;

    autoLoadPending = true;
    if (loadObserver) loadObserver.unobserve(els.loadMore);

    visibleCount = Math.min(visibleCount + PAGE_SIZE, total);
    render();

    window.setTimeout(resumeAutoLoad, 250);
  }

  function setupAutoLoad() {
    if (!("IntersectionObserver" in window)) return;

    loadObserver = new IntersectionObserver(function (entries) {
      const entry = entries[0];
      if (!entry || !entry.isIntersecting || els.loadMore.hidden) return;
      loadNextPage();
    }, {
      root: els.scroller || null,
      rootMargin: "500px 0px 200px",
      threshold: 0.01
    });

    loadObserver.observe(els.loadMore);
  }

  function resetFeedScroll() {
    if (!els.scroller) return;
    els.scroller.scrollTo({ top: 0, behavior: "smooth" });
  }

  function setRubric(tag) {
    activeRubric = tag || null;
    visibleCount = PAGE_SIZE;
    els.rubrics.querySelectorAll(".chip").forEach(function (chip) {
      chip.classList.toggle("chip-active", (chip.dataset.rubric || "") === (tag || ""));
    });
    render();
    resetFeedScroll();
  }

  function setupEvents() {
    els.search.addEventListener("input", function (e) {
      searchQuery = e.target.value || "";
      visibleCount = PAGE_SIZE;
      render();
      resetFeedScroll();
    });
    els.rubrics.addEventListener("click", function (e) {
      const btn = e.target.closest("button[data-rubric]"); if (btn) setRubric(btn.dataset.rubric || null);
    });
    els.list.addEventListener("click", function (e) {
      const btn = e.target.closest("button.tag-badge");
      if (btn) { setRubric(btn.dataset.tag || null); $("latest").scrollIntoView({ behavior: "smooth" }); }
    });
    els.loadMore.addEventListener("click", loadNextPage);
    window.addEventListener("keydown", function (e) {
      if (e.key === "/" && !e.target.closest("input, textarea")) { e.preventDefault(); els.search.focus(); }
    });
  }

  function bootstrapNews() {
    const node = document.getElementById("seo-news-bootstrap");
    if (!node) return [];
    try {
      const data = JSON.parse(node.textContent || "[]");
      return Array.isArray(data) ? data : [];
    } catch (_) {
      return [];
    }
  }

  async function loadNews() {
    allNews = bootstrapNews();
    if (allNews.length) {
      normalize();
      buildRubrics();
      buildTopTags();
      els.loading.hidden = true;
    }

    for (const url of NEWS_URLS) {
      try {
        const resp = await fetch(url, { cache: "default" });
        if (!resp.ok) continue;
        const data = await resp.json();
        const loaded = Array.isArray(data) ? data : (data.items || []);
        if (loaded.length) {
          allNews = loaded;
          break;
        }
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
    setupAutoLoad();
    loadNews();
  });
})();