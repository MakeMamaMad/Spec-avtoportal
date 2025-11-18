// frontend/article.js

const NEWS_URLS = ["./data/news_meta.json", "./data/news.json"];

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const yyyy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${dd}.${mm}.${yyyy}, ${hh}:${min}`;
}

function pick(obj, keys, fallback = "") {
  for (const key of keys) {
    const v = obj?.[key];
    if (v !== undefined && v !== null && String(v).trim() !== "") {
      return v;
    }
  }
  return fallback;
}

function normalizeList(raw) {
  const list = Array.isArray(raw)
    ? raw
    : Array.isArray(raw?.items)
    ? raw.items
    : Array.isArray(raw?.news)
    ? raw.news
    : [];

  return list.map((item, idx) => {
    const title = pick(item, ["title", "headline", "name"], "Без названия");
    const summary = pick(
      item,
      ["summary", "description", "lead", "snippet"],
      ""
    );
    const body = pick(
      item,
      ["content_html", "content", "full_text", "text"],
      summary
    );
    const date = pick(item, ["published_at", "pub_date", "date", "timestamp"], "");
    const source = pick(item, ["source", "source_name", "feed", "site"], "");
    const url = pick(item, ["url", "link", "source_url"], "");
    const image = pick(
      item,
      ["image", "image_url", "thumbnail", "cover", "picture"],
      ""
    );

    return {
      idx,
      title,
      body,
      summary,
      date,
      source,
      url,
      image,
    };
  });
}

async function loadNewsData() {
  for (const url of NEWS_URLS) {
    try {
      const resp = await fetch(url, { cache: "no-store" });
      if (!resp.ok) continue;
      const data = await resp.json();
      const list = normalizeList(data);
      if (list.length) return list;
    } catch (e) {
      console.warn("failed to load", url, e);
    }
  }
  throw new Error("no data");
}

function renderArticle(item) {
  const root = document.getElementById("article-root");
  const errorEl = document.getElementById("article-error");
  if (!root) return;

  root.innerHTML = "";

  const title = document.createElement("h1");
  title.className = "article__title";
  title.textContent = item.title;
  root.appendChild(title);

  const meta = document.createElement("p");
  meta.className = "article__meta";
  const bits = [];
  if (item.source) bits.push(item.source);
  if (item.date) bits.push(formatDate(item.date));
  meta.textContent = bits.join(" · ");
  root.appendChild(meta);

  if (item.image) {
    const img = document.createElement("img");
    img.className = "article__image";
    img.src = item.image;
    img.alt = "";
    root.appendChild(img);
  }

  const body = document.createElement("div");
  body.className = "article__body";

  if (item.body && /<\/?[a-z][\s\S]*>/i.test(item.body)) {
    body.innerHTML = item.body;
  } else {
    const text = item.body || item.summary || "";
    for (const chunk of String(text).split(/\n{2,}/)) {
      const p = document.createElement("p");
      p.textContent = chunk.trim();
      body.appendChild(p);
    }
  }
  root.appendChild(body);

  if (item.url) {
    const link = document.createElement("a");
    link.className = "article__source-link";
    link.href = item.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Читать в источнике →";
    root.appendChild(link);
  }

  if (errorEl) errorEl.hidden = true;
}

async function init() {
  const params = new URLSearchParams(location.search);
  const idxStr = params.get("idx");
  const errorEl = document.getElementById("article-error");

  let idx = Number.parseInt(idxStr ?? "", 10);
  if (!Number.isFinite(idx) || idx < 0) idx = 0;

  try {
    const list = await loadNewsData();
    const item = list.find((x) => x.idx === idx) ?? list[0];
    if (!item) throw new Error("no item");
    renderArticle(item);
  } catch (e) {
    console.error(e);
    if (errorEl) errorEl.hidden = false;
  }
}

document.addEventListener("DOMContentLoaded", init);
