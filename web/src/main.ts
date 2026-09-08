import type { FilterMeta, QueryState, TopicPage } from "./types";
import "./styles.css";

function requireApp(): HTMLDivElement {
  const el = document.querySelector<HTMLDivElement>("#app");
  if (!el) {
    throw new Error("missing #app");
  }
  return el;
}

const root = requireApp();
const pageSize = 20;

let meta: FilterMeta = { sites: [], categories: [] };
let query: QueryState = readQuery();
let pageData: TopicPage = emptyPage();
let refreshing = false;

boot();

async function boot() {
  meta = await fetchJson<FilterMeta>("/api/filters");
  pageData = await loadTopics(query);
  render();
  if (!pageData.fetched_at) {
    await refresh();
  }
}

async function loadTopics(next: QueryState): Promise<TopicPage> {
  const params = new URLSearchParams();
  if (next.q) params.set("q", next.q);
  if (next.site_id) params.set("site_id", next.site_id);
  if (next.category) params.set("category", next.category);
  if (next.date) params.set("date", next.date);
  params.set("page", String(next.page));
  params.set("page_size", String(pageSize));
  return fetchJson<TopicPage>(`/api/topics?${params.toString()}`);
}

async function refresh() {
  if (refreshing) {
    return;
  }
  refreshing = true;
  render();
  try {
    await fetch("/api/refresh", { method: "POST" });
    pageData = await loadTopics(query);
  } catch {
    pageData = { ...pageData, refreshing: false };
  } finally {
    refreshing = false;
    render();
  }
}

function render() {
  const lastPage = Math.max(1, Math.ceil(pageData.total / pageData.page_size) || 1);
  root.innerHTML = `
    <div class="page">
      <header class="top">
        <div>
          <h1>WatchSieve</h1>
          <p class="when">${whenLabel()}</p>
        </div>
        <button class="refresh" type="button" ${refreshing ? "disabled" : ""}>
          ${refreshing ? "抓取中" : "刷新"}
        </button>
      </header>
      <form class="filters" id="filters">
        <label>关键词
          <input name="q" type="search" value="${escapeAttr(query.q)}" placeholder="搜标题" />
        </label>
        <label>来源
          <select name="site_id">
            <option value="">全部</option>
            ${meta.sites.map((site) => option(site.id, site.name, query.site_id)).join("")}
          </select>
        </label>
        <label>类型
          <select name="category">
            <option value="">全部</option>
            ${meta.categories.map((item) => option(item.id, item.name, query.category)).join("")}
          </select>
        </label>
        <label>日期
          <input name="date" type="date" value="${escapeAttr(query.date)}" />
        </label>
        <div class="filter-actions">
          <button class="search" type="submit">查询</button>
          <button class="ghost" type="button" data-reset>重置</button>
        </div>
      </form>
      ${pageData.failed_sites.length ? `<p class="fail">${escapeHtml(pageData.failed_sites.join("、"))} 抓取失败</p>` : ""}
      <main class="board" aria-busy="${refreshing ? "true" : "false"}">
        ${tableBody(lastPage)}
      </main>
    </div>
  `;
  root.querySelector(".refresh")?.addEventListener("click", () => {
    void refresh();
  });
  root.querySelector("#filters")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const form = event.target as HTMLFormElement;
    const data = new FormData(form);
    query = {
      q: String(data.get("q") || "").trim(),
      site_id: String(data.get("site_id") || ""),
      category: String(data.get("category") || ""),
      date: String(data.get("date") || ""),
      page: 1,
    };
    writeQuery(query);
    void search();
  });
  root.querySelector("[data-reset]")?.addEventListener("click", () => {
    query = { q: "", site_id: "", category: "", date: "", page: 1 };
    writeQuery(query);
    void search();
  });
  root.querySelector("[data-prev]")?.addEventListener("click", () => {
    query = { ...query, page: Math.max(1, query.page - 1) };
    writeQuery(query);
    void search();
  });
  root.querySelector("[data-next]")?.addEventListener("click", () => {
    query = { ...query, page: query.page + 1 };
    writeQuery(query);
    void search();
  });
}

async function search() {
  pageData = await loadTopics(query);
  render();
}

function tableBody(lastPage: number) {
  if (refreshing) {
    return `<div class="skeletons" aria-hidden="true">${"<span></span>".repeat(8)}</div>`;
  }
  if (!pageData.items.length) {
    return `<p class="empty">${pageData.fetched_at ? "没有符合条件的标题" : "还没有标题，点刷新"}</p>`;
  }
  const rows = pageData.items
    .map(
      (item) => `
        <tr>
          <td data-label="标题">${titleCell(item.title, item.url)}</td>
          <td data-label="来源"><a href="${escapeAttr(item.site_url)}" target="_blank" rel="noreferrer">${escapeHtml(item.site_name)}</a></td>
          <td data-label="类型">${escapeHtml(item.category_label)}</td>
          <td data-label="时间">${escapeHtml(formatTime(item.fetched_at))}</td>
          <td data-label="原文">${item.url ? `<a href="${escapeAttr(item.url)}" target="_blank" rel="noreferrer">打开</a>` : "—"}</td>
        </tr>`,
    )
    .join("");
  return `
    <table class="list">
      <thead>
        <tr>
          <th>标题</th>
          <th>来源</th>
          <th>类型</th>
          <th>时间</th>
          <th>原文</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    <nav class="pager">
      <span>共 ${pageData.total} 条</span>
      <div>
        <button class="ghost" type="button" data-prev ${pageData.page <= 1 ? "disabled" : ""}>上一页</button>
        <span>${pageData.page} / ${lastPage}</span>
        <button class="ghost" type="button" data-next ${pageData.page >= lastPage ? "disabled" : ""}>下一页</button>
      </div>
    </nav>
  `;
}

function titleCell(title: string, url: string) {
  const label = escapeHtml(title);
  return url
    ? `<a class="topic" href="${escapeAttr(url)}" target="_blank" rel="noreferrer">${label}</a>`
    : `<span class="topic">${label}</span>`;
}

function option(id: string, name: string, selected: string) {
  return `<option value="${escapeAttr(id)}" ${id === selected ? "selected" : ""}>${escapeHtml(name)}</option>`;
}

function whenLabel() {
  if (refreshing) {
    return "正在抓取标题";
  }
  if (!pageData.fetched_at) {
    return "还没有抓过";
  }
  return `共 ${pageData.total} 条 · ${relativeTime(pageData.fetched_at)}`;
}

function relativeTime(value: string) {
  const then = new Date(value).getTime();
  const delta = Date.now() - then;
  if (delta < 60_000) {
    return "刚刚";
  }
  const minutes = Math.floor(delta / 60_000);
  if (minutes < 60) {
    return `${minutes} 分钟前`;
  }
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function formatTime(value: string | null) {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleString("zh-CN", { hour12: false, month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function readQuery(): QueryState {
  const params = new URLSearchParams(window.location.search);
  return {
    q: params.get("q") || "",
    site_id: params.get("site_id") || "",
    category: params.get("category") || "",
    date: params.get("date") || "",
    page: Math.max(1, Number(params.get("page") || 1) || 1),
  };
}

function writeQuery(next: QueryState) {
  const params = new URLSearchParams();
  if (next.q) params.set("q", next.q);
  if (next.site_id) params.set("site_id", next.site_id);
  if (next.category) params.set("category", next.category);
  if (next.date) params.set("date", next.date);
  if (next.page > 1) params.set("page", String(next.page));
  const qs = params.toString();
  history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
}

function emptyPage(): TopicPage {
  return {
    total: 0,
    page: 1,
    page_size: pageSize,
    fetched_at: null,
    refreshing: false,
    failed_sites: [],
    items: [],
  };
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url} failed`);
  }
  return response.json();
}

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeAttr(value: string) {
  return escapeHtml(value);
}
