import type { NamedOption, WatchPage, WatchQueryState } from "./types";

type EscapeFn = (value: string) => string;

export function emptyWatchPage(): WatchPage {
  return {
    total: 0,
    page: 1,
    page_size: 50,
    keywords: "",
    revision: 1,
    model: "",
    running: false,
    items: [],
  };
}

function option(id: string, name: string, selected: string, escapeAttr: EscapeFn, escapeHtml: EscapeFn) {
  return `<option value="${escapeAttr(id)}" ${id === selected ? "selected" : ""}>${escapeHtml(name)}</option>`;
}

export function watchBody(
  pageData: WatchPage,
  query: WatchQueryState,
  keywords: string,
  sites: NamedOption[],
  lastPage: number,
  loading: boolean,
  running: boolean,
  error: string,
  notice: string,
  formatTime: (value: string | null) => string,
  escapeHtml: EscapeFn,
  escapeAttr: EscapeFn,
): string {
  const empty = keywords.trim() ? "还没有关注的标题" : "请先填写兴趣关键词";
  let main = "";
  if (loading && !pageData.items.length && !error) {
    main = `<div class="skeletons" aria-hidden="true">${"<span></span>".repeat(8)}</div>`;
  } else if (!pageData.items.length) {
    main = `<p class="empty">${escapeHtml(empty)}</p>`;
  } else {
    const rows = pageData.items
      .map(
        (item) => `
        <tr>
          <td data-label="标题">${item.url
            ? `<a class="topic" href="${escapeAttr(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a>`
            : `<span class="topic">${escapeHtml(item.title)}</span>`}</td>
          <td data-label="来源">${escapeHtml(item.site_name)}</td>
          <td data-label="兴趣">${escapeHtml(item.interest || "—")}</td>
          <td data-label="原因">${escapeHtml(item.reason || "—")}</td>
          <td data-label="时间">${escapeHtml(formatTime(item.fetched_at))}</td>
        </tr>`,
      )
      .join("");
    main = `
      <table class="list">
        <thead>
          <tr>
            <th>标题</th>
            <th>来源</th>
            <th>兴趣</th>
            <th>原因</th>
            <th>时间</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
      <nav class="pager">
        <span>共 ${pageData.total} 条</span>
        <div>
          <button class="ghost" type="button" data-watch-prev ${pageData.page <= 1 ? "disabled" : ""}>上一页</button>
          <span>${pageData.page} / ${lastPage}</span>
          <button class="ghost" type="button" data-watch-next ${pageData.page >= lastPage ? "disabled" : ""}>下一页</button>
        </div>
      </nav>`;
  }
  const modelHint = pageData.model ? `当前模型 ${pageData.model}` : "用本机网关筛选";
  return `
    <div class="page">
      <div class="page-head">
        <h1>关注</h1>
        <p class="when">${escapeHtml(modelHint)}</p>
      </div>
      <form class="cli-run" data-watch-interests>
        <label>兴趣
          <textarea name="keywords" rows="3" ${running ? "disabled" : ""}>${escapeHtml(keywords)}</textarea>
        </label>
        <button class="ghost" type="submit" ${running ? "disabled" : ""}>保存兴趣</button>
      </form>
      <form class="filters filters--class" id="watch-filters">
        <label>关键词
          <input name="q" type="search" value="${escapeAttr(query.q)}" placeholder="搜标题" />
        </label>
        <label>来源
          <select name="site_id">
            <option value="">全部</option>
            ${sites.map((site) => option(site.id, site.name, query.site_id, escapeAttr, escapeHtml)).join("")}
          </select>
        </label>
        <div class="filter-actions">
          <button class="search" type="submit">查询</button>
          <button class="ghost" type="button" data-watch-reset>重置</button>
        </div>
      </form>
      <p class="fail" role="status" ${error ? "" : "hidden"}>${escapeHtml(error)}</p>
      <p class="ai-notice" role="status" ${notice ? "" : "hidden"}>${escapeHtml(notice)}</p>
      <main id="main" class="board" tabindex="-1" aria-busy="${loading || running ? "true" : "false"}">
        ${main}
      </main>
    </div>
  `;
}
