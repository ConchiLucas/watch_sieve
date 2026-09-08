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
