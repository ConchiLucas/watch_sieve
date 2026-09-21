export type NavItem = {
  id: string;
  label: string;
  href: string;
};

export const NAV_ITEMS: NavItem[] = [
  { id: "titles", label: "标题", href: "/" },
  { id: "topics", label: "分类", href: "/topics" },
  { id: "watch", label: "关注", href: "/watch" },
];

export const DEFAULT_NAV = "titles";
export const DEFAULT_TOPIC = "uncategorized";

export function currentNavId(pathname: string): string {
  const path = pathname || "/";
  const match = NAV_ITEMS.find((item) => {
    if (item.href === "/") {
      return path === "/" || path === "";
    }
    return path === item.href || path.startsWith(`${item.href}/`);
  });
  return match?.id ?? DEFAULT_NAV;
}

export function currentTopicId(hash: string, known: Iterable<string> = []): string {
  const id = hash.replace(/^#/, "");
  const allowed = new Set(known);
  if (!id) {
    return DEFAULT_TOPIC;
  }
  if (!allowed.size || allowed.has(id)) {
    return id;
  }
  return DEFAULT_TOPIC;
}

export function topicHref(topicId: string, search = ""): string {
  return `/topics${search}${topicId ? `#${topicId}` : ""}`;
}
