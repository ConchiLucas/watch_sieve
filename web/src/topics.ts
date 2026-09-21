import { DEFAULT_TOPIC, topicHref } from "./nav";
import type { ClassificationCatalog, ClassificationPage, ClassQueryState, NamedOption } from "./types";

type EscapeFn = (value: string) => string;

export function emptyClassCatalog(): ClassificationCatalog {
  return {
    uncategorized: { id: DEFAULT_TOPIC, label: "未分类", count: 0 },
    groups: [],
  };
}

export function emptyClassPage(): ClassificationPage {
  return {
    topic_id: DEFAULT_TOPIC,
    topic_label: "未分类",
    total: 0,
    page: 1,
    page_size: 50,
    items: [],
  };
}

export function knownTopicIds(catalog: ClassificationCatalog): string[] {
  return [
    catalog.uncategorized.id,
    ...catalog.groups.flatMap((group) => group.topics.map((item) => item.id)),
  ];
}

function option(id: string, name: string, selected: string, escapeAttr: EscapeFn, escapeHtml: EscapeFn) {
  return `<option value="${escapeAttr(id)}" ${id === selected ? "selected" : ""}>${escapeHtml(name)}</option>`;
}

function topicLink(
  item: { id: string; label: string; count: number },
  current: string,
  search: string,
  escapeAttr: EscapeFn,
  escapeHtml: EscapeFn,
) {
  const selected = item.id === current;
  return `<a href="${escapeAttr(topicHref(item.id, search))}" data-nav ${current && selected ? 'aria-current="page"' : ""}>
    <span>${escapeHtml(item.label)}</span>
    <span class="side-count">${item.count}</span>
  </a>`;
}

export function topicsBody(
  catalog: ClassificationCatalog,
  pageData: ClassificationPage,
  query: ClassQueryState,
  topicId: string,
  sites: NamedOption[],
  lastPage: number,
  loading: boolean,
  error: string,
  formatTime: (value: string | null) => string,
  escapeHtml: EscapeFn,
  escapeAttr: EscapeFn,
): string {
  const params = new URLSearchParams();
  if (query.q) params.set("q", query.q);
  if (query.site_id) params.set("site_id", query.site_id);
  if (query.page > 1) params.set("page", String(query.page));
  const search = params.toString() ? `?${params.toString()}` : "";
  const heading = pageData.topic_label || "未分类";
  const empty = topicId === DEFAULT_TOPIC ? "还没有未分类的标题" : "这一类还没有标题";
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
          <td data-label="主分类">${escapeHtml(item.topic_label)}</td>
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
            <th>主分类</th>
            <th>时间</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
      <nav class="pager">
        <span>共 ${pageData.total} 条</span>
        <div>
          <button class="ghost" type="button" data-class-prev ${pageData.page <= 1 ? "disabled" : ""}>上一页</button>
          <span>${pageData.page} / ${lastPage}</span>
          <button class="ghost" type="button" data-class-next ${pageData.page >= lastPage ? "disabled" : ""}>下一页</button>
        </div>
      </nav>`;
  }
  return `
    <div class="split">
      <aside class="side" aria-label="主题分类">
        <p class="side-label">分类</p>
        <nav class="side-list">
          ${topicLink(catalog.uncategorized, topicId, search, escapeAttr, escapeHtml)}
          ${catalog.groups
            .map(
              (group) => `
            <p class="side-group-label">${escapeHtml(group.label)}</p>
            ${group.topics.map((item) => topicLink(item, topicId, search, escapeAttr, escapeHtml)).join("")}`,
            )
            .join("")}
        </nav>
      </aside>
      <div class="split-main">
        <div class="page-head">
          <h1>${escapeHtml(heading)}</h1>
          <p class="when">按主分类查看标题，和标题页的筛选、列不是同一套。</p>
        </div>
        <form class="filters filters--class" id="class-filters">
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
            <button class="ghost" type="button" data-class-reset>重置</button>
          </div>
        </form>
        <p class="fail" role="status" ${error ? "" : "hidden"}>${escapeHtml(error)}</p>
        <main id="main" class="board" tabindex="-1" aria-busy="${loading ? "true" : "false"}">
          ${main}
        </main>
      </div>
    </div>
  `;
}
