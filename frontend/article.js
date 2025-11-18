// frontend/article.js

const NEWS_URL = "./data/news.json";
const articleRoot = document.getElementById("article-root");
const relatedList = document.getElementById("related-list");
const footerYearEl = document.getElementById("footer-year");

if (footerYearEl) {
  footerYearEl.textContent = new Date().getFullYear();
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const yyyy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${dd}.${mm}.${yyyy}, ${hh}:${mi}`;
}

function normalizeNews(raw) {
  if (!raw) return [];
  let items = Array.isArray(raw) ? raw : raw.items || raw.news || raw.data || [];
  if (!Array.isArray(items)) return [];

  return items.map((item, index) => {
    const title =
      item.title ||
      item.headline ||
      item.name ||
      `Новость #${index + 1}`;

    const url = item.url || item.link || null;
    const source = item.source || item.source_name || "";
    const tags = item.tags || item.rubrics || item.categories || [];
    const dt =
      item.published_at ||
      item.pub_date ||
      item.date ||
      item.datetime ||
      null;
    const snippet =
      item.snippet || item.summary || item.description || "";

    return {
      _index: index,
      raw: item,
      title,
      url,
      source,
      tags: Array.isArray(tags) ? tags : typeof tags === "string" ? [tags] : [],
      published_at: dt,
      snippet,
    };
  });
}

function renderArticle(item) {
  articleRoot.innerHTML = "";

  const titleEl = document.createElement("h1");
  titleEl.className = "article-title";
  titleEl.textContent = item.title;

  const metaEl = document.createElement("div");
  metaEl.className = "article-meta";

  if (item.source) {
    const s = document.createElement("span");
    s.className = "news-source";
    s.textContent = item.source;
    metaEl.appendChild(s);
  }

  if (item.published_at) {
    const d = document.createElement("span");
    d.className = "news-date";
    d.textContent = formatDate(item.published_at);
    metaEl.appendChild(d);
  }

  if (item.url) {
    const link = document.createElement("a");
    link.href = item.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Читать в источнике";
    link.className = "tag tag-primary";
    metaEl.appendChild(link);
  }

  const bodyEl = document.createElement("div");
  bodyEl.className = "article-body";

  const rawBody =
    item.raw?.content ||
    item.raw?.body ||
    item.raw?.text ||
    item.snippet ||
    "";

  if (rawBody && /<\/?[a-z][\s\S]*>/i.test(rawBody)) {
    // похоже на HTML
    bodyEl.innerHTML = rawBody;
  } else {
    const p = document.createElement("p");
    p.textContent = rawBody || "Текст статьи недоступен.";
    bodyEl.appendChild(p);
  }

  articleRoot.appendChild(titleEl);
  articleRoot.appendChild(metaEl);
  articleRoot.appendChild(bodyEl);
}

function renderRelated(allItems, currentIndex) {
  if (!relatedList) return;
  relatedList.innerHTML = "";

  const current = allItems[currentIndex];
  if (!current) return;

  const currentTag = (current.tags && current.tags[0]) || null;

  const candidates = allItems.filter(
    (item, idx) =>
      idx !== currentIndex &&
      (!currentTag || (item.tags || []).includes(currentTag))
  );

  candidates.slice(0, 5).forEach((item) => {
    const li = document.createElement("li");
    li.className = "related-item";
    const a = document.createElement("a");
    const url = new URL("./article.html", window.location.href);
    url.searchParams.set("index", String(item._index));
    a.href = url.toString();
    a.textContent = item.title;
    li.appendChild(a);
    relatedList.appendChild(li);
  });
}

async function main() {
  const params = new URLSearchParams(window.location.search);
  const indexStr = params.get("index");
  const index = indexStr ? Number.parseInt(indexStr, 10) : NaN;

  if (Number.isNaN(index)) {
    articleRoot.innerHTML =
      "<p>Не указан идентификатор статьи. Вернитесь на главную страницу.</p>";
    return;
  }

  try {
    const res = await fetch(NEWS_URL, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const raw = await res.json();
    const items = normalizeNews(raw);

    if (!items.length || !items[index]) {
      articleRoot.innerHTML =
        "<p>Статья не найдена. Возможно, она была удалена или лента обновилась.</p>";
      return;
    }

    renderArticle(items[index]);
    renderRelated(items, index);
  } catch (err) {
    console.error("Ошибка загрузки статьи:", err);
    articleRoot.innerHTML =
      "<p>Не удалось загрузить статью. Попробуйте позже.</p>";
  }
}

main();
