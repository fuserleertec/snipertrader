import type { DeskQuote, Timeframe } from '../types';
import type { StudyLast, StackLabel } from '../lib/ta';
import { fmtPct, fmtPx, fmtVol, signClass } from '../lib/format';

interface TapePanelProps {
  quote: DeskQuote | null;
  last: StudyLast | null;
  stack: StackLabel;
  timeframe: Timeframe;
}

function Range({ low, high, mark }: { low: number; high: number; mark: number }) {
  const span = high - low;
  const pct = span > 0 ? Math.min(100, Math.max(0, ((mark - low) / span) * 100)) : 50;
  return (
    <div className="range">
      <span>{fmtPx(low)}</span>
      <div className="range-track">
        <div className="range-fill" style={{ width: `${pct}%` }} />
        <i style={{ left: `${pct}%` }} />
      </div>
      <span>{fmtPx(high)}</span>
    </div>
  );
}

export function TapePanel({ quote, last, stack, timeframe }: TapePanelProps) {
  const vwapLabel = timeframe === '1d' ? 'Window VWAP' : 'Session VWAP';
  const distance =
    last?.vwap != null && last.vwap !== 0 ? ((last.close - last.vwap) / last.vwap) * 100 : null;
  return (
    <section className="panel tape-panel">
      <div className="panel-h">
        <span>Tape</span>
        <span className={`stack ${stack === 'LONG STACK' ? 'up' : stack === 'SHORT STACK' ? 'down' : ''}`}>{stack}</span>
      </div>
      {!quote ? (
        <p className="empty">Waiting for a quote.</p>
      ) : (
        <div className="tape-body">
          <div className="tape-last">
            <div>
              <div className="tape-sym">{quote.symbol}</div>
              <div className="tape-name">{quote.name}</div>
            </div>
            <div className="tape-px">
              <b className={signClass(quote.change)}>{fmtPx(quote.last)}</b>
              <span className={signClass(quote.change)}>
                {fmtPx(quote.change)} · {fmtPct(quote.changePct)}
              </span>
            </div>
          </div>
          <div className="tape-block">
            <div className="k">Day range</div>
            <Range low={quote.dayLow} high={quote.dayHigh} mark={quote.last} />
          </div>
          {quote.week52Low != null && quote.week52High != null ? (
            <div className="tape-block">
              <div className="k">52 week</div>
              <Range low={quote.week52Low} high={quote.week52High} mark={quote.last} />
            </div>
          ) : null}
          <dl className="tape-grid">
            <div>
              <dt>Prev close</dt>
              <dd>{fmtPx(quote.prevClose)}</dd>
            </div>
            <div>
              <dt>Volume</dt>
              <dd>{fmtVol(quote.volume)}</dd>
            </div>
            <div>
              <dt>{vwapLabel}</dt>
              <dd>{fmtPx(last?.vwap)}</dd>
            </div>
            <div>
              <dt>Vs VWAP</dt>
              <dd className={signClass(distance)}>{fmtPct(distance)}</dd>
            </div>
            <div>
              <dt>EMA 9</dt>
              <dd>{fmtPx(last?.ema9)}</dd>
            </div>
            <div>
              <dt>EMA 21 / 50</dt>
              <dd>
                {fmtPx(last?.ema21)} · {fmtPx(last?.ema50)}
              </dd>
            </div>
          </dl>
        </div>
      )}
    </section>
  );
}
