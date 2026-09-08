---
version: 0.2
name: WatchSieve Title Admin
description: A quiet admin table for titles from many watched sites.
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
typography:
  display:
    fontFamily: "ui-sans-serif, PingFang SC, Noto Sans SC, system-ui, sans-serif"
    fontSize: 22px
    fontWeight: 600
    lineHeight: 28px
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
---

# WatchSieve UI

One admin page: filter bar, title table, pagination. Sites are rows of metadata, not extra columns.

## Query fields

Only four. Crawl internals stay out of the form.

| Field | Use |
|---|---|
| 关键词 | Match title text |
| 来源 | One watched site |
| 类型 | `forum` 论坛 / `news` 资讯 / `blog` 博客 / `other` 其他 |
| 日期 | Fetch calendar day in UTC+8 |

## List fields

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

## Layout

Max width 1120px. Desktop: real table. 375px: stacked rows (title, then 来源 · 类型 · 时间 · 原文). Refresh stays in the header.

| Mode | Width | Behavior |
|---|---:|---|
| Narrow | 375px | Filters wrap; table becomes stacked cards |
| Tablet | 768px | Filters wrap; table stays tabular if it fits |
| Desktop | 1440px | Filter row + table + pager |

## Source

| Role | Source | Borrow | Adapt | Avoid |
|---|---|---|---|---|
| Primary | Notion | Warm quiet chrome, content first | Admin table instead of a title wall | Notion logo and editor chrome |
| Secondary | Airtable | One object per row | Four filters only, no colorful views | Rainbow tags, spreadsheet gadgets |

## Out of scope

Site editor, scheduler, LLM sieve, engine debug, settings, auth.
