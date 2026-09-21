import {
  currentNavId,
  currentTopicId,
  NAV_ITEMS,
} from "./nav";
import { emptyClassCatalog, emptyClassPage, knownTopicIds, topicsBody } from "./topics";
import { emptyWatchPage, watchBody } from "./watch";
import type {
  ClassificationCatalog,
  ClassificationPage,
  ClassQueryState,
  FilterMeta,
  QueryState,
  TopicPage,
  WatchPage,
  WatchQueryState,
} from "./types";
import "./styles.css";

function requireApp(): HTMLDivElement {
  const el = document.querySelector<HTMLDivElement>("#app");
  if (!el) {
    throw new Error("missing #app");
  }
  return el;
}

const root = requireApp();
const pageSize = 50;

let meta: FilterMeta = { sites: [], categories: [] };
let query: QueryState = readQuery();
let pageData: TopicPage = emptyPage();
let classQuery: ClassQueryState = readClassQuery();
let classCatalog: ClassificationCatalog = emptyClassCatalog();
let classPage: ClassificationPage = emptyClassPage();
let classLoading = false;
let classError = "";
let watchQuery: WatchQueryState = readWatchQuery();
let watchPage: WatchPage = emptyWatchPage();
let watchKeywords = "";
let watchLoading = false;
let watchRunning = false;
let watchError = "";
let watchNotice = "";
let requestError = "";

function currentPage() {
  return currentNavId(window.location.pathname);
}

boot();
window.addEventListener("popstate", onLocationChange);
window.addEventListener("hashchange", onLocationChange);

function onLocationChange() {
  render();
  if (currentPage() === "topics") {
    classQuery = readClassQuery();
    void loadClassifications();
  }
  if (currentPage() === "watch") {
    watchQuery = readWatchQuery();
    void loadWatches();
  }
}

async function boot() {
  render();
  try {
    meta = await fetchJson<FilterMeta>("/api/filters");
    pageData = await loadTopics(query);
    render();
    if (!pageData.fetched_at && currentPage() === "titles") {
      void refresh();
    }
    if (currentPage() === "topics") {
      await loadClassifications();
    }
    if (currentPage() === "watch") {
      await loadWatches();
    }
  } catch {
    requestError = "加载失败，请稍后重试";
    updateResults();
  }
  window.setTimeout(poll, 2000);
}

async function poll() {
  try {
    const snapshot = JSON.stringify(query);
    const next = await loadTopics(query);
    if (snapshot === JSON.stringify(query)) {
      pageData = next;
      requestError = "";
      updateResults();
    }
  } catch {
    requestError = "连接失败，暂时无法更新标题";
    updateResults();
  } finally {
    window.setTimeout(poll, 2000);
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

function activeTopicId() {
  return currentTopicId(window.location.hash, knownTopicIds(classCatalog));
}

async function loadClassifications() {
  classLoading = true;
  classError = "";
  render();
  try {
    const catalogParams = new URLSearchParams();
    if (classQuery.q) catalogParams.set("q", classQuery.q);
    if (classQuery.site_id) catalogParams.set("site_id", classQuery.site_id);
    classCatalog = await fetchJson<ClassificationCatalog>(
      `/api/classifications/catalog${catalogParams.toString() ? `?${catalogParams.toString()}` : ""}`,
    );
    const topic = currentTopicId(window.location.hash, knownTopicIds(classCatalog));
    const params = new URLSearchParams();
    if (topic) params.set("topic", topic);
    if (classQuery.q) params.set("q", classQuery.q);
    if (classQuery.site_id) params.set("site_id", classQuery.site_id);
    params.set("page", String(classQuery.page));
    params.set("page_size", String(pageSize));
    classPage = await fetchJson<ClassificationPage>(`/api/classifications?${params.toString()}`);
    classError = "";
  } catch {
    classError = "无法加载分类，请稍后重试";
  } finally {
    classLoading = false;
    render();
  }
}

async function loadWatches() {
  watchLoading = true;
  watchError = "";
  render();
  try {
    const params = new URLSearchParams();
    if (watchQuery.q) params.set("q", watchQuery.q);
    if (watchQuery.site_id) params.set("site_id", watchQuery.site_id);
    params.set("page", String(watchQuery.page));
    params.set("page_size", String(pageSize));
    watchPage = await fetchJson<WatchPage>(`/api/watches?${params.toString()}`);
    watchKeywords = watchPage.keywords;
    watchError = "";
  } catch {
    watchError = "无法加载关注，请稍后重试";
  } finally {
    watchLoading = false;
    render();
  }
}

async function saveWatchKeywords() {
  watchError = "";
  watchNotice = "";
  render();
  try {
    const response = await fetch("/api/watches/interests", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keywords: watchKeywords }),
    });
    if (!response.ok) {
      throw new Error("save failed");
    }
    const payload = await response.json();
    watchKeywords = String(payload.keywords || watchKeywords);
    watchNotice = "兴趣已保存";
  } catch {
    watchError = "兴趣保存失败";
  } finally {
    render();
  }
}

async function runWatches() {
  if (watchRunning) {
    return;
  }
  watchRunning = true;
  watchError = "";
  watchNotice = "";
  render();
  try {
    const response = await fetch("/api/watches/run", { method: "POST" });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(typeof payload?.detail === "string" ? payload.detail : "筛选失败");
    }
    watchNotice = String(payload.message || "筛选完成");
    await loadWatches();
  } catch (cause) {
    watchError = cause instanceof Error ? cause.message : "筛选失败";
  } finally {
    watchRunning = false;
    render();
  }
}

async function refresh() {
  try {
    const response = await fetch("/api/refresh", { method: "POST" });
    if (!response.ok) throw new Error("refresh failed");
  } catch {
    requestError = "刷新失败，请稍后重试";
    updateResults();
  }
}

function render() {
  const lastPage = Math.max(1, Math.ceil(pageData.total / pageData.page_size) || 1);
  const classLastPage = Math.max(1, Math.ceil(classPage.total / classPage.page_size) || 1);
  const watchLastPage = Math.max(1, Math.ceil(watchPage.total / watchPage.page_size) || 1);
  const page = currentPage();
  let action = "";
  if (page === "watch") {
    action = `<button class="refresh" type="button" data-watch-run ${watchRunning ? "disabled" : ""}>${watchRunning ? "筛选中" : "筛选"}</button>`;
  } else if (page !== "topics") {
    action = `<button class="refresh" type="button">刷新</button>`;
  }
  let body = titlesBody(lastPage);
  if (page === "topics") {
    body = topicsBody(
      classCatalog,
      classPage,
      classQuery,
      activeTopicId(),
      meta.sites,
      classLastPage,
      classLoading,
      classError,
      formatTime,
      escapeHtml,
      escapeAttr,
    );
  } else if (page === "watch") {
    body = watchBody(
      watchPage,
      watchQuery,
      watchKeywords,
      meta.sites,
      watchLastPage,
      watchLoading,
      watchRunning,
      watchError,
      watchNotice,
      formatTime,
      escapeHtml,
      escapeAttr,
    );
  }
  root.innerHTML = `
    <a class="skip" href="#main">跳到内容</a>
    <header class="app-bar">
      <div class="app-bar-inner">
        <a class="brand" href="/" data-nav>WatchSieve</a>
        <nav class="menu" aria-label="主导航">
          ${NAV_ITEMS.map((item) => {
            const current = item.id === page;
            return `<a href="${escapeAttr(item.href)}" data-nav ${current ? 'aria-current="page"' : ""}>${escapeHtml(item.label)}</a>`;
          }).join("")}
        </nav>
        ${action}
      </div>
    </header>
    ${body}
  `;
  bindShell();
  if (page === "topics") {
    bindTopics();
  } else if (page === "watch") {
    bindWatch();
  } else {
    bindTitles();
  }
}

function titlesBody(lastPage: number) {
  return `
    <div class="page">
      <div class="page-head">
        <h1>标题</h1>
        <p class="when">${whenLabel()}</p>
      </div>
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
      <p class="fail" role="status" ${failureLabel() ? "" : "hidden"}>${escapeHtml(failureLabel())}</p>
      <main id="main" class="board" tabindex="-1">
        ${tableBody(lastPage)}
      </main>
    </div>
  `;
}

function bindShell() {
  root.querySelectorAll<HTMLAnchorElement>("[data-nav]").forEach((link) => {
    link.addEventListener("click", (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return;
      }
      event.preventDefault();
      const next = new URL(link.href);
      const nextUrl = `${next.pathname}${next.hash}`;
      const here = `${window.location.pathname}${window.location.hash}`;
      if (nextUrl === here) {
        return;
      }
      history.pushState(null, "", nextUrl);
      if (next.pathname === "/topics") {
        classQuery = readClassQuery();
      }
      if (next.pathname === "/watch") {
        watchQuery = readWatchQuery();
      }
      render();
      if (currentPage() === "topics") {
        void loadClassifications();
      }
      if (currentPage() === "watch") {
        void loadWatches();
      }
    });
  });
}

function bindTitles() {
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
  bindPagination();
}

function bindTopics() {
  root.querySelector("#class-filters")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const form = event.target as HTMLFormElement;
    const data = new FormData(form);
    classQuery = {
      q: String(data.get("q") || "").trim(),
      site_id: String(data.get("site_id") || ""),
      page: 1,
    };
    writeClassQuery(classQuery);
    void loadClassifications();
  });
  root.querySelector("[data-class-reset]")?.addEventListener("click", () => {
    classQuery = { q: "", site_id: "", page: 1 };
    writeClassQuery(classQuery);
    void loadClassifications();
  });
  root.querySelector("[data-class-prev]")?.addEventListener("click", () => {
    classQuery = { ...classQuery, page: Math.max(1, classQuery.page - 1) };
    writeClassQuery(classQuery);
    void loadClassifications();
  });
  root.querySelector("[data-class-next]")?.addEventListener("click", () => {
    classQuery = { ...classQuery, page: classQuery.page + 1 };
    writeClassQuery(classQuery);
    void loadClassifications();
  });
}

function bindWatch() {
  root.querySelector("[data-watch-run]")?.addEventListener("click", () => {
    void runWatches();
  });
  root.querySelector("[data-watch-interests]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const form = event.target as HTMLFormElement;
    watchKeywords = String(new FormData(form).get("keywords") || "");
    void saveWatchKeywords();
  });
  root.querySelector("#watch-filters")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const form = event.target as HTMLFormElement;
    const data = new FormData(form);
    watchQuery = {
      q: String(data.get("q") || "").trim(),
      site_id: String(data.get("site_id") || ""),
      page: 1,
    };
    writeWatchQuery(watchQuery);
    void loadWatches();
  });
  root.querySelector("[data-watch-reset]")?.addEventListener("click", () => {
    watchQuery = { q: "", site_id: "", page: 1 };
    writeWatchQuery(watchQuery);
    void loadWatches();
  });
  root.querySelector("[data-watch-prev]")?.addEventListener("click", () => {
    watchQuery = { ...watchQuery, page: Math.max(1, watchQuery.page - 1) };
    writeWatchQuery(watchQuery);
    void loadWatches();
  });
  root.querySelector("[data-watch-next]")?.addEventListener("click", () => {
    watchQuery = { ...watchQuery, page: watchQuery.page + 1 };
    writeWatchQuery(watchQuery);
    void loadWatches();
  });
}

function bindPagination() {
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
  try {
    const snapshot = JSON.stringify(query);
    const next = await loadTopics(query);
    if (snapshot !== JSON.stringify(query)) return;
    pageData = next;
    requestError = "";
  } catch {
    requestError = "查询失败，请稍后重试";
  }
  render();
}

function failureLabel() {
  return requestError || (pageData.failed_sites.length
    ? `${pageData.failed_sites.join("、")} 抓取失败；如有历史标题则保留，时间为原抓取时间`
    : "");
}

function updateResults() {
  if (currentPage() !== "titles") {
    return;
  }
  // Polling must not replace the filter form or interrupt Chinese IME input.
  const label = root.querySelector(".when");
  if (label) label.textContent = whenLabel();
  const failure = root.querySelector<HTMLParagraphElement>(".fail");
  if (failure) {
    failure.hidden = !failureLabel();
    failure.textContent = failureLabel();
  }
  const board = root.querySelector(".board");
  if (board) {
    const lastPage = Math.max(1, Math.ceil(pageData.total / pageData.page_size) || 1);
    const body = tableBody(lastPage);
    if (board.innerHTML !== body && !board.contains(document.activeElement)) {
      board.innerHTML = body;
      bindPagination();
    }
  }
}

function tableBody(lastPage: number) {
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
  if (window.location.pathname && window.location.pathname !== "/") {
    return { q: "", site_id: "", category: "", date: "", page: 1 };
  }
  const params = new URLSearchParams(window.location.search);
  return {
    q: params.get("q") || "",
    site_id: params.get("site_id") || "",
    category: params.get("category") || "",
    date: params.get("date") || "",
    page: Math.max(1, Number(params.get("page") || 1) || 1),
  };
}

function readClassQuery(): ClassQueryState {
  if (window.location.pathname !== "/topics") {
    return { q: "", site_id: "", page: 1 };
  }
  const params = new URLSearchParams(window.location.search);
  return {
    q: params.get("q") || "",
    site_id: params.get("site_id") || "",
    page: Math.max(1, Number(params.get("page") || 1) || 1),
  };
}

function writeClassQuery(next: ClassQueryState) {
  const params = new URLSearchParams();
  if (next.q) params.set("q", next.q);
  if (next.site_id) params.set("site_id", next.site_id);
  if (next.page > 1) params.set("page", String(next.page));
  const qs = params.toString();
  const hash = activeTopicId();
  history.replaceState(null, "", `/topics${qs ? `?${qs}` : ""}#${hash}`);
}

function readWatchQuery(): WatchQueryState {
  if (window.location.pathname !== "/watch") {
    return { q: "", site_id: "", page: 1 };
  }
  const params = new URLSearchParams(window.location.search);
  return {
    q: params.get("q") || "",
    site_id: params.get("site_id") || "",
    page: Math.max(1, Number(params.get("page") || 1) || 1),
  };
}

function writeWatchQuery(next: WatchQueryState) {
  const params = new URLSearchParams();
  if (next.q) params.set("q", next.q);
  if (next.site_id) params.set("site_id", next.site_id);
  if (next.page > 1) params.set("page", String(next.page));
  const qs = params.toString();
  history.replaceState(null, "", `/watch${qs ? `?${qs}` : ""}`);
}

function writeQuery(next: QueryState) {
  const params = new URLSearchParams();
  if (next.q) params.set("q", next.q);
  if (next.site_id) params.set("site_id", next.site_id);
  if (next.category) params.set("category", next.category);
  if (next.date) params.set("date", next.date);
  if (next.page > 1) params.set("page", String(next.page));
  const qs = params.toString();
  history.replaceState(null, "", qs ? `/?${qs}` : "/");
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
