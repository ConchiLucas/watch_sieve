---
version: 0.17
name: WatchSieve Title Admin
description: A quiet admin table for titles from many watched sites, a classification page, and a watch page for LLM-matched interests.
colors:
  canvas: "#FAF8F5"
  surface: "#FFFFFF"
  ink: "#1C1917"
  body: "#44403C"
  muted: "#78716C"
  hairline: "#E7E5E4"
  primary: "#1C1917"
  primary-hover: "#44403C"
  on-primary: "#FAF8F5"
  focus: "#1C1917"
  success: "#3F6212"
  error: "#B42318"
  skeleton: "#E7E5E4"
  nav: "#FFFFFF"
typography:
  display:
    fontFamily: "ui-sans-serif, PingFang SC, Noto Sans SC, system-ui, sans-serif"
    fontSize: 22px
    fontWeight: 600
    lineHeight: 28px
  brand:
    fontFamily: "ui-sans-serif, PingFang SC, Noto Sans SC, system-ui, sans-serif"
    fontSize: 15px
    fontWeight: 600
    lineHeight: 24px
  nav:
    fontFamily: "ui-sans-serif, PingFang SC, Noto Sans SC, system-ui, sans-serif"
    fontSize: 14px
    fontWeight: 500
    lineHeight: 20px
  label:
    fontFamily: "ui-sans-serif, PingFang SC, Noto Sans SC, system-ui, sans-serif"
    fontSize: 13px
    fontWeight: 500
    lineHeight: 18px
  title:
    fontFamily: "ui-sans-serif, PingFang SC, Noto Sans SC, system-ui, sans-serif"
    fontSize: 15px
    fontWeight: 500
    lineHeight: 24px
  meta:
    fontFamily: "ui-sans-serif, PingFang SC, Noto Sans SC, system-ui, sans-serif"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 20px
rounded:
  sm: 6px
  md: 10px
spacing:
  sm: 8px
  md: 16px
  lg: 24px
  xl: 40px
components:
  app-bar:
    backgroundColor: "{colors.nav}"
    borderBottom: "{colors.hairline}"
    sticky: true
    minHeight: 56px
  nav-item:
    color: "{colors.muted}"
    currentColor: "{colors.ink}"
    currentBackground: "{colors.canvas}"
    minHeight: 40px
    rounded: "{rounded.sm}"
  button-primary:
    backgroundColor: "{colors.primary}"
    hoverBackground: "{colors.primary-hover}"
    textColor: "{colors.on-primary}"
    height: 40px
    rounded: "{rounded.md}"
---

# WatchSieve UI

App shell is a full-width top menu. Three pages: the title list, 分类, and 关注. Sites are rows of metadata, not extra columns. 分类 and 关注 are not reskins of the title list.

## Navigation

The bar is the only place new product areas are added. Do not invent pages or disabled “coming soon” items.

| Piece | Use |
|---|---|
| Brand | `WatchSieve`, left, links to the title list |
| Menu | `标题` → `/` · `分类` → `/topics` · `关注` → `/watch` |
| Current item | `aria-current="page"`, ink on canvas, not color alone |
| Title action | Right of the bar: crawl `刷新` |
| Classification action | None in this version |
| Watch action | Right of the bar: `筛选`, runs the local_config_center chat model |

Add a later menu by appending `{ id, label, href }` in `web/src/nav.ts` and implementing that route. Chinese labels; keep them short.

## 分类

The left rail is the topic catalog, not a second copy of the top menu and not the title-page filters. Hash selects the primary topic (`/topics#model-eval`); default with no hash is 未分类. Counts sit in the rail. Groups are small labels inside the rail (`AI 用量`, `开发`, `生活与社区`, `其他`).

Right pane filters and columns are owned by this page. Do not reuse the title list’s 类型 or 原文, and do not add 日期 in this version.

| Field | Use |
|---|---|
| 关键词 | Match title text inside the current topic |
| 来源 | One watched site |
| 标题 | Primary cell, wraps, opens the original post |
| 来源 | Site name |
| 主分类 | Primary topic label |
| 时间 | First-seen time, `zh-CN` |

Empty: 这一类还没有标题, or 还没有未分类的标题. Switching topics does not refetch the title list. Opening the page does not call the model. A stored LLM topic wins when present; until `watchSieveJudge` has judged a title, the rail uses the keyword fallback so it is not empty.

## 关注

Independent from 分类. No left rail. Filters and columns are owned by this page. Matches are persisted; opening the page does not call the model. `筛选` and the scheduled `watchSieveJudge` job both call the local_config_center gateway (`POST /v1/invoke`, `kind=chat`). Model slug is `WATCH_SIEVE_CHAT_MODEL` (currently `aurora/gpt-5-6-mini`); if unset, the first `kind=chat` model from `GET /v1/models`. It is not a vendor SDK, not Antigravity CLI, and is not inside the crawl refresh lock.

| Field | Use |
|---|---|
| 兴趣 | Comma-separated interest keywords, saved on this page. Topic phrases such as 国际新闻大事件 / 国内新闻大事件 also consider news-event titles, not only the exact phrase |
| 关键词 | Match already-kept title text |
| 来源 | One watched site |
| 标题 | Primary cell, wraps, opens the original post |
| 来源 | Site name |
| 兴趣 | Which interest the model assigned |
| 原因 | Short model reason |
| 时间 | First-seen time, `zh-CN` |

Empty: 还没有关注的标题, or 请先填写兴趣关键词. Error: one recoverable line; show the gateway `error.safeMessage` or HTTP status, never pretend the call succeeded.

## Query fields

Title list only. Four fields. Crawl internals stay out of the form.

| Field | Use |
|---|---|
| 关键词 | Match title text |
| 来源 | One watched site |
| 类型 | `forum` 论坛 / `news` 资讯 / `blog` 博客 / `other` 其他 |
| 日期 | First-seen calendar day in UTC+8 |

## List fields

Title list only.

| Field | Use |
|---|---|
| 标题 | Primary cell, wraps, opens the original post |
| 来源 | Site name |
| 类型 | Site category label |
| 时间 | Fetch time, `zh-CN` |
| 原文 | Explicit text action, not an icon |

Do not show engine, status code, selector, or raw URL as columns.

## Principles

1. The table is the product. Filters stay on one row.
2. Query on submit, not on every keystroke.
3. Failed crawls are one line above the table, not a status column.
4. Chinese titles wrap; they are not truncated to ellipsis.
5. The top menu grows for product pages; classification topics live in the left rail, not as extra top items.
6. Vendor API keys and vendor Base URLs stay in local_config_center. This app only stores the gateway base URL, gateway auth, and an optional model slug.
7. 分类 and 关注 own their filters and columns; they must not inherit the title list’s query state.

## Layout

The app bar is full width and sticky. Title and 关注 content max width 1120px. The 分类 page is a left rail plus a right pane, using the same colors and type as the rest of the app.

| Mode | Width | Behavior |
|---|---:|---|
| Narrow | 375px | Brand and action on the first row; top menu wraps; 分类 rail sits above the pane and scrolls sideways; filters stack; table becomes stacked cards |
| Tablet | 768px | Brand, menu, and action on one row if they fit; 分类 rail and pane stack if needed; filters wrap; table stays tabular if it fits |
| Desktop | 1440px | Title and 关注: sticky bar + filter row + table. 分类: sticky bar + 220px left rail + right pane |

## States

| State | Behavior |
|---|---|
| Default | Current menu item marked; table ready |
| Hover | Primary buttons darken to body; menu items stay readable |
| Focus | 2px ink outline, 3px offset, on links, inputs, and buttons |
| Disabled | Query waits while a search is in flight; pager uses not-allowed. 刷新 does not wait on crawl |
| Loading | Title list is independent of crawl: no 抓取中, no crawl skeletons, keep the last loaded table |
| Empty | 没有符合条件的标题, or 还没有标题，点刷新. 分类: 这一类还没有标题, or 还没有未分类的标题. 关注: 还没有关注的标题, or 请先填写兴趣关键词 |
| Error | One recoverable line above the table or catalog |
| Reduced motion | No skeleton motion |

## Source

| Role | Source | Borrow | Adapt | Avoid |
|---|---|---|---|---|
| Primary | Notion | Warm quiet chrome, content first, text navigation | Horizontal top bar instead of a workspace sidebar | Notion logo, editor chrome, proprietary type |
| Secondary | Airtable | One object per row | Four filters only, no colorful views | Rainbow tags, spreadsheet gadgets |

### Direction for this version

The top menu is Notion workspace chrome turned into a horizontal bar. 分类 borrows only the left-rail plus right-pane arrangement from a typical admin console; it does not take another brand’s colors, type, or icons. 关注 stays a full-width list like the title page.

## Out of scope

Site editor, scheduler, engine debug, auth, and an in-app config page. Model keys live in local_config_center. 分类 and 关注 use the gateway chat model in a separate `watchSieveJudge` job (and 关注 still has manual `筛选`); they do not run inside the crawl refresh lock.
