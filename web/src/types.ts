export interface NamedOption {
  id: string;
  name: string;
}

export interface FilterMeta {
  sites: NamedOption[];
  categories: NamedOption[];
}

export interface TopicRow {
  title: string;
  url: string;
  site_id: string;
  site_name: string;
  site_url: string;
  category: string;
  category_label: string;
  fetched_at: string | null;
}

export interface TopicPage {
  total: number;
  page: number;
  page_size: number;
  fetched_at: string | null;
  refreshing: boolean;
  failed_sites: string[];
  items: TopicRow[];
}

export interface QueryState {
  q: string;
  site_id: string;
  category: string;
  date: string;
  page: number;
}

export interface ClassQueryState {
  q: string;
  site_id: string;
  page: number;
}

export interface WatchQueryState {
  q: string;
  site_id: string;
  page: number;
}

export interface WatchRow {
  title: string;
  url: string;
  site_id: string;
  site_name: string;
  interest: string;
  reason: string;
  fetched_at: string | null;
}

export interface WatchPage {
  total: number;
  page: number;
  page_size: number;
  keywords: string;
  revision: number;
  model: string;
  running: boolean;
  items: WatchRow[];
}

export interface ClassificationTopic {
  id: string;
  label: string;
  count: number;
}

export interface ClassificationGroup {
  id: string;
  label: string;
  topics: ClassificationTopic[];
}

export interface ClassificationCatalog {
  uncategorized: ClassificationTopic;
  groups: ClassificationGroup[];
}

export interface ClassificationRow {
  title: string;
  url: string;
  site_id: string;
  site_name: string;
  topic_id: string;
  topic_label: string;
  fetched_at: string | null;
}

export interface ClassificationPage {
  topic_id: string;
  topic_label: string;
  total: number;
  page: number;
  page_size: number;
  items: ClassificationRow[];
}
