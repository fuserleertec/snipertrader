import type { NewsItem } from '../types';
import { ago } from '../lib/format';

interface NewsPanelProps {
  symbol: string;
  items: NewsItem[];
  sentiment: string | null;
  loading: boolean;
}

export function NewsPanel({ symbol, items, sentiment, loading }: NewsPanelProps) {
  const tone = sentiment === 'BULLISH' ? 'up' : sentiment === 'BEARISH' ? 'down' : '';
  return (
    <section className="panel news-panel">
      <div className="panel-h">
        <span>Headlines · {symbol}</span>
        {sentiment ? <span className={`stack ${tone}`}>{sentiment}</span> : <span className="panel-meta">News</span>}
      </div>
      <div className="news-list">
        {loading && !items.length ? <p className="empty">Loading headlines…</p> : null}
        {!loading && !items.length ? <p className="empty">No headlines for {symbol}.</p> : null}
        {items.map((item) => {
          const body = (
            <>
              <span className="news-title">{item.title}</span>
              <span className="news-meta">
                {item.source}
                {item.publishedAt ? ` · ${ago(item.publishedAt)}` : ''}
                {item.summary ? ` · ${item.summary}` : ''}
              </span>
            </>
          );
          return item.url ? (
            <a key={item.id} className="news-item" href={item.url} target="_blank" rel="noreferrer">
              {body}
            </a>
          ) : (
            <div key={item.id} className="news-item">
              {body}
            </div>
          );
        })}
      </div>
    </section>
  );
}
