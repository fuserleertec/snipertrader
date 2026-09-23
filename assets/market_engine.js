/* ════════════════════════════════════════════════════════════════════════════
   SNIPERTRADER MARKET ENGINE — shared, single source of truth
   Loaded by market_terminal.html (Daily Market Picks) and
   sniper_market_forecaster.html (Market Forecaster).

   Everything here is computed from REAL price history. No simulation,
   no fabricated order flow. Deterministic given (bars, universe context).

   Pure analysis:
     structure()  → trend / MSS / FVG / order block / sweep / S/R / VWAP
     ensemble()   → 7 independent signals folded into one consensus
     cone()       → EMPIRICAL probability cone from actual forward returns
     tradeLevels()→ entry / stop / target from consensus + structure
     analyzeSymbol() → the full per-symbol read

   Data (key-less / server-key):
     crypto → Binance public klines (CORS-open)
     equity → /api/stocks/klines (Alpaca, server-side key)
     futures → no key-less feed (snapshot only, labeled SNAP)
   ════════════════════════════════════════════════════════════════════════════ */
'use strict';

/* ── universe ── */
const CRYPTO = ['BTCUSDT','ETHUSDT','SOLUSDT','LINKUSDT','AVAXUSDT','DOGEUSDT','XRPUSDT','ADAUSDT','DOTUSDT','BNBUSDT','LTCUSDT','ATOMUSDT','TRXUSDT','NEARUSDT','APTUSDT','ARBUSDT','SHIBUSDT','FILUSDT'];
const EQUITY = ['AAPL','AMD','AMZN','AVGO','CRWD','META','MSFT','NVDA','PLTR','TSLA','GOOGL','NFLX','ADBE','ORCL','CRM','QCOM','INTC','TSM','MU','COIN','NOW','SNOW','UBER','ABNB','PYPL','SHOP','XYZ','DDOG','PANW','NET'];
const FUTURES = ['CL','GC','ES','NQ','HG','SI','NG','ZN','ZB','ZF','PL','KC'];
const ALL_SYMBOLS = [...EQUITY, ...CRYPTO, ...FUTURES];
const MOM_WINDOW = 120, MOM_SKIP = 20, MIN_OBS = 30;   // cross-sectional momentum lookback (daily ≈ 6mo) + 1-month skip; MIN_OBS = min conditional observations

/* ── universe helpers ── */
const CLS = {};
EQUITY.forEach(s => CLS[s] = 'equity');
CRYPTO.forEach(s => CLS[s] = 'crypto');
FUTURES.forEach(s => CLS[s] = 'futures');

function dispSym(sym){ return CLS[sym] === 'futures' ? sym + '1!' : sym; }
function tvSymbol(sym){
  if(CLS[sym] === 'futures') return {CL:'NYMEX:CL1!',GC:'COMEX:GC1!',ES:'CME_MINI:ES1!',NQ:'CME_MINI:NQ1!',HG:'COMEX:HG1!',SI:'COMEX:SI1!',NG:'NYMEX:NG1!',ZN:'CBOT:ZN1!',ZB:'CBOT:ZB1!',ZF:'CBOT:ZF1!',PL:'NYMEX:PL1!',KC:'NYBOT:KC1!'}[sym] || sym;
  if(CLS[sym] === 'crypto') return 'BINANCE:' + sym;
  return sym; // equities resolve by bare ticker on TradingView
}

const fmt = (n, dec = 2) => (n == null ? '—' : Number(n).toFixed(dec));
const fmtPx = (n) => (n == null ? '—' : Number(n).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}));

/* ── indicators ── */
function sma(v, n){ if(v.length < n) return null; let s = 0; for(let i = v.length - n; i < v.length; i++) s += v[i]; return s / n; }
function emaSeries(v, n){ const k = 2/(n+1); let prev = null; const o = []; for(const x of v){ prev = prev == null ? x : x*k + prev*(1-k); o.push(prev); } return o; }
function atrSeries(bars, n = 14){
  const trs = []; for(let i = 1; i < bars.length; i++){ const h = bars[i].h, l = bars[i].l, pc = bars[i-1].c; trs.push(Math.max(h-l, Math.abs(h-pc), Math.abs(l-pc))); }
  if(trs.length < n) return null;
  let a = trs.slice(0, n).reduce((x,y)=>x+y,0)/n; const o = new Array(n).fill(null); o.push(a);
  for(let i = n; i < trs.length; i++){ a = (a*(n-1)+trs[i])/n; o.push(a); }
  return o;
}
function rsiSeries(bars, n = 14){
  const g = [], l = []; for(let i = 1; i < bars.length; i++){ const ch = bars[i].c - bars[i-1].c; g.push(Math.max(ch,0)); l.push(Math.max(-ch,0)); }
  if(g.length < n) return null;
  let ag = g.slice(0,n).reduce((x,y)=>x+y,0)/n, al = l.slice(0,n).reduce((x,y)=>x+y,0)/n;
  const o = new Array(n).fill(null); o.push(al === 0 ? 100 : 100 - 100/(1+ag/al));
  for(let i = n; i < g.length; i++){ ag = (ag*(n-1)+g[i])/n; al = (al*(n-1)+l[i])/n; o.push(al === 0 ? 100 : 100 - 100/(1+ag/al)); }
  return o;
}
function rollingVwap(bars, n = 20){ if(bars.length < n) return null; let pv = 0, vv = 0; for(let i = bars.length - n; i < bars.length; i++){ const b = bars[i], tp = (b.h+b.l+b.c)/3; pv += tp*b.v; vv += b.v; } return vv > 0 ? pv/vv : null; }
function obvSeries(bars){ const o = []; let run = 0; bars.forEach((b,i)=>{ if(i===0){o.push(run);return;} if(b.c>bars[i-1].c)run+=b.v; else if(b.c<bars[i-1].c)run-=b.v; o.push(run); }); return o; }
function swingPivots(bars, k = 3){ const p = []; for(let i = k; i < bars.length - k; i++){ let h = true, l = true; for(let j = i-k; j <= i+k; j++){ if(bars[j].h > bars[i].h) h = false; if(bars[j].l < bars[i].l) l = false; } if(h) p.push({i, kind:'H', price:bars[i].h}); if(l) p.push({i, kind:'L', price:bars[i].l}); } return p; }
function fwdReturns(bars, n = 5){ const o = []; for(let i = 0; i < bars.length - n; i++) o.push(bars[i+n].c/bars[i].c - 1); return o; }
function zlast(v){ if(!v || v.length < 8) return 0; let m = v.reduce((a,b)=>a+b,0)/v.length; let va = v.reduce((a,x)=>a+(x-m)*(x-m),0)/v.length; let sd = Math.sqrt(va); return sd > 1e-12 ? (v[v.length-1]-m)/sd : 0; }
function median(v){ const s = v.slice().sort((a,b)=>a-b); const n = s.length; if(!n) return 0; return n%2 ? s[Math.floor(n/2)] : (s[n/2-1]+s[n/2])/2; }

/* ── market structure ── */
function structure(bars){
  const c = bars[bars.length-1].c, piv = swingPivots(bars);
  const pH = piv.filter(p=>p.kind==='H'), pL = piv.filter(p=>p.kind==='L');
  const vwap = rollingVwap(bars);
  let trend = 'range';
  if(pH.length>=2 && pL.length>=2){ const hh = pH[pH.length-1].price>pH[pH.length-2].price, ll = pL[pL.length-1].price>pL[pL.length-2].price; if(hh&&ll)trend='up'; else if(!hh&&!ll)trend='down'; }
  let mss = null;
  if(pH.length && c>pH[pH.length-1].price)mss='bullish'; else if(pL.length && c<pL[pL.length-1].price)mss='bearish';
  let fvg = null;
  for(let i = bars.length-2; i>1; i--){ const b0 = bars[i-2], b2 = bars[i];
    if(b0.h < b2.l){ const sz = (b2.l-b0.h)/b0.h; if(sz>0.003){ fvg = {dir:'bull', zone:[b0.h,b2.l], bar:i, gap_pct:+(sz*100).toFixed(2)}; break; } }
    if(b0.l > b2.h){ const sz = (b0.l-b2.h)/b0.l; if(sz>0.003){ fvg = {dir:'bear', zone:[b2.h,b0.l], bar:i, gap_pct:+(sz*100).toFixed(2)}; break; } } }
  let ob = null;
  for(let i = bars.length-1; i>1; i--){ const b0 = bars[i], imp = (b0.c-b0.o)/b0.o;
    if(imp>0.012){ let j = i-1; while(j>0 && bars[j].c>bars[j].o) j--; if(bars[j].c<bars[j].o){ ob = {dir:'bull', zone:[bars[j].l,bars[j].h], bar:j}; break; } }
    if(imp<-0.012){ let j = i-1; while(j>0 && bars[j].c<bars[j].o) j--; if(bars[j].c>bars[j].o){ ob = {dir:'bear', zone:[bars[j].l,bars[j].h], bar:j}; break; } } }
  let sweep = null; const loK = Math.min(...bars.slice(-4,-1).map(b=>b.l)), hiK = Math.max(...bars.slice(-4,-1).map(b=>b.h)); const last = bars[bars.length-1];
  if(last.l<loK && last.c>loK) sweep = {dir:'bull', level:loK}; else if(last.h>hiK && last.c<hiK) sweep = {dir:'bear', level:hiK};
  const lows = pL.map(p=>p.price).sort((a,b)=>a-b), highs = pH.map(p=>p.price).sort((a,b)=>a-b);
  const below = lows.filter(x=>x<c), above = highs.filter(x=>x>c);
  const support = below.length ? Math.max(...below) : null;
  const resistance = above.length ? Math.min(...above) : null;
  return {close:c, vwap:vwap==null?null:+vwap.toFixed(4), vwap_pct:vwap==null?null:+((c/vwap-1)*100).toFixed(2),
    trend, mss, fvg, order_block:ob, sweep, support:support==null?null:+support.toFixed(4), resistance:resistance==null?null:+resistance.toFixed(4)};
}

/* ── ensemble: 7 signals → one consensus (0..1) ── */
function ensemble(bars, k, u){
  const closes = bars.map(b=>b.c), n = closes.length, c = closes[closes.length-1];
  const A = [];
  const push = (name, strength, why)=>{ const sig = strength>0.4?'bull':(strength<-0.4?'bear':'neutral');
    A.push({name, signal:sig, confidence:+Math.max(0,Math.min(1,Math.abs(strength))).toFixed(3), why}); };
  const ema12 = emaSeries(closes,12), ema26 = emaSeries(closes,26);
  const e12 = ema12[ema12.length-1], e26 = ema26[ema26.length-1];
  const sma50 = sma(closes,50), sma200 = sma(closes, n>=200?200:n);
  const atr = atrSeries(bars), atrNow = atr ? atr[atr.length-1] : null, atrVals = atr ? atr.filter(v=>v!=null) : [];
  const rsi = rsiSeries(bars), rsiNow = rsi ? rsi[rsi.length-1] : null;
  const obv = obvSeries(bars), obvSlope = obv.length>=10 ? (obv[obv.length-1]-obv[obv.length-10])/(obv[obv.length-10]||1) : 0;

  // 1) Trend — EMA12/26 + SMA50/200 stack
  let stack = 0; if(sma50 && sma200){ if(c>sma50 && sma50>sma200)stack=1; else if(c<sma50 && sma50<sma200)stack=-1; }
  const tDir = (e12>e26?1:-1) + stack;
  push('Trend', tDir, `EMA12/26 ${e12>e26?'above':'below'}${(sma50&&sma200)?`, SMA50 ${sma50>sma200?'>':'<'} SMA200`:''}`);

  // 2) Rel Momentum — cross-sectional relative strength vs universe. 120d lookback, skip 20d.
  if(n >= MOM_WINDOW+1){ const mom = closes[closes.length-1-MOM_SKIP]/closes[closes.length-1-MOM_WINDOW]-1;
    if(u && u.cs_mad != null){ const denom = 1.4826*u.cs_mad; const rel = denom>1e-12 ? (mom-u.cs_median)/denom : 0;
      push('Rel Momentum', rel, `${MOM_WINDOW}d momentum (skip ${MOM_SKIP}d) ${(mom*100)>=0?'+':''}${(mom*100).toFixed(1)}% vs universe z ${rel>=0?'+':''}${rel.toFixed(1)}`); }
    else { const moms = []; for(let i=MOM_WINDOW;i<n;i++) moms.push(closes[i-MOM_SKIP]/closes[i-MOM_WINDOW]-1); const z = zlast(moms);
      push('Rel Momentum', z, `${MOM_WINDOW}d momentum z ${z>=0?'+':''}${z.toFixed(1)}`); } }
  else push('Rel Momentum', 0, 'insufficient bars');

  // 3) Mean Rev — Bollinger z (contrarian)
  const bbz = n>=20 ? zlast(closes.slice(-20)) : 0;
  push('Mean Rev', -bbz, `BB z ${bbz>=0?'+':''}${bbz.toFixed(1)}${rsiNow!=null?`, RSI ${rsiNow.toFixed(0)}`:''}`);

  // 4) Vol Regime — ATR percentile (low-vol continuation tilt, high-vol caution)
  if(atrNow!=null && atrVals.length){ let pct = 0; for(const v of atrVals){ if(v<atrNow)pct++; else if(v===atrNow)pct+=0.5; } pct/=atrVals.length;
    push('Vol Regime', (0.5-pct)*2, `ATR ${(pct*100).toFixed(0)}th pct`); }
  else push('Vol Regime', 0, 'no ATR');

  // 5) Volume — OBV 10-bar slope, z-scored
  if(obv.length>=18){ const slopes = []; for(let i=10;i<obv.length;i++) slopes.push((obv[i]-obv[i-10])/(obv[i-10]||1));
    push('Volume', zlast(slopes), `OBV 10-bar slope ${obvSlope>=0?'+':''}${obvSlope.toFixed(3)}`); }
  else push('Volume', 0, 'insufficient bars');

  // 6) Key Level — ATR-distance to nearest support/resistance
  if(atrNow && atrNow>0 && (k.support != null || k.resistance != null)){ const dSup = k.support != null ? (c-k.support)/atrNow : Infinity, dRes = k.resistance != null ? (k.resistance-c)/atrNow : Infinity, near = Math.min(dSup, dRes);
    let kl = 0; if(near<=2) kl = (1-near/2)*(dSup<dRes?1:-1);
    push('Key Level', kl, `${near.toFixed(1)} ATR to S/R`); }
  else push('Key Level', 0, 'no level');

  // 7) Structure — MSS + sweep (break/run, NOT trend which is signal #1)
  let st = 0; if(k.mss==='bullish')st+=1; else if(k.mss==='bearish')st-=1;
  if(k.sweep && k.sweep.dir==='bull')st+=0.5; else if(k.sweep && k.sweep.dir==='bear')st-=0.5;
  push('Structure', st, `break=${k.mss} sweep=${k.sweep?k.sweep.dir:'—'}`);

  const bull = A.filter(a=>a.signal==='bull').reduce((s,a)=>s+a.confidence,0), bear = A.filter(a=>a.signal==='bear').reduce((s,a)=>s+a.confidence,0);
  const nBull = A.filter(a=>a.signal==='bull'&&a.confidence>0.05).length, nBear = A.filter(a=>a.signal==='bear'&&a.confidence>0.05).length, nNeu = A.length-nBull-nBear;
  const consensus = +((bull+0.5)/(bull+bear+1.0)).toFixed(3);
  return {agents:A, bull:+bull.toFixed(3), bear:+bear.toFixed(3), n_bull:nBull, n_bear:nBear, n_neu:nNeu, consensus, consensus_pct:+(consensus*100).toFixed(1)};
}

/* ── probability cone — CONDITIONAL on the signal bucket (from ACTUAL forward returns) ──
   Resolution: this symbol's own bucket → universe-wide bucket → unconditional base rate.
   Point-in-time; MIN_OBS = minimum observations before a bucket is trusted. */
function cone(bars, bucket, perSym, pooled){
  const c = bars[bars.length-1].c, atr = atrSeries(bars), atrNow = atr ? atr[atr.length-1] : null, fr = fwdReturns(bars,5);
  if(!fr.length || atrNow == null) return null;
  const muAll = fr.reduce((a,b)=>a+b,0)/fr.length, sdAll = Math.sqrt(fr.reduce((a,x)=>a+(x-muAll)**2,0)/fr.length);
  let stats = null, scope = 'unconditional';
  const pSym = perSym ? perSym[bucket] : null;
  const pPool = pooled ? pooled[bucket] : null;
  if(pSym && pSym.n >= MIN_OBS){ stats = pSym; scope = 'symbol'; }
  else if(pPool && pPool.n >= MIN_OBS){ stats = pPool; scope = 'universe'; }
  let bull, base, bear, n;
  if(stats == null){ const sd = sdAll; bull = fr.filter(x=>x>0.5*sd).length/fr.length; bear = fr.filter(x=>x<-0.5*sd).length/fr.length; base = 1-bull-bear; n = fr.length;
    bull = +(bull*100).toFixed(1); base = +(base*100).toFixed(1); bear = +(bear*100).toFixed(1); }
  else { bull = stats.bull; base = stats.base; bear = stats.bear; n = stats.n; }
  return {sigma_5d:+(sdAll*100).toFixed(2), bull, base, bear,
    up:+(c*(1+sdAll)).toFixed(4), down:+(c*(1-sdAll)).toFixed(4), atr:+atrNow.toFixed(4), atr_pct:+(atrNow/c*100).toFixed(2), horizon_bars:5,
    n, scope, bucket};
}

/* ── trade plan ── */
function tradeLevels(bars, k, cons){
  const c = bars[bars.length-1].c, atr = atrSeries(bars), atrNow = atr ? atr[atr.length-1] : null, entry = c; let stop = null, target = null, direction;
  if(cons >= 0.60){ direction = 'LONG';
    stop = (k.support && k.support<c) ? (atrNow ? Math.min(k.support, c-atrNow) : k.support) : (atrNow ? c-atrNow : null);
    target = (k.resistance && k.resistance>c) ? (atrNow ? Math.min(k.resistance, c+3*atrNow) : k.resistance) : (atrNow ? c+2*atrNow : null);
    if(atrNow && target && target < c+atrNow) target = c+atrNow; }
  else if(cons <= 0.40){ direction = 'SHORT';
    stop = (k.resistance && k.resistance>c) ? (atrNow ? Math.max(k.resistance, c+atrNow) : k.resistance) : (atrNow ? c+atrNow : null);
    target = (k.support && k.support<c) ? (atrNow ? Math.max(k.support, c-3*atrNow) : k.support) : (atrNow ? c-2*atrNow : null);
    if(atrNow && target && target > c-atrNow) target = c-atrNow; }
  else direction = 'HOLD';
  let rr = null;
  if((direction==='LONG'||direction==='SHORT') && stop && target){ const risk = Math.abs(entry-stop), reward = Math.abs(target-entry); rr = risk>0 ? +(reward/risk).toFixed(2) : null;
    if(direction==='LONG' && (stop>=entry || target<=entry)){ direction='HOLD'; rr=null; }
    else if(direction==='SHORT' && (stop<=entry || target>=entry)){ direction='HOLD'; rr=null; }
    else if(rr!=null && rr<1.0){ direction='HOLD'; rr=null; } }
  return {direction, entry, stop, target, rr};
}

function conviction(cone, trade){
  const d = trade.direction;
  if(d === 'HOLD' || cone == null) return 50;
  const pWin = d === 'LONG' ? cone.bull : cone.bear;
  const pLoss = d === 'LONG' ? cone.bear : cone.bull;
  return Math.round(50 + (pWin - pLoss) / 2);
}

/* ── real Monte Carlo (bootstrap + GBM, calibrated to realized returns) ──
   NOT the old MiroFish seeded random-walk: these paths are sampled from the
   symbol's ACTUAL historical daily log-returns (bootstrap, non-parametric) and
   a log-normal GBM fit to its realized drift/vol. Output is a percentile FAN —
   a statistical range, not a directional prediction. */
function mulberry32(a){ return function(){ a|=0; a=(a+0x6D2B79F5)|0; let t=Math.imul(a^a>>>15,1|a); t=(t+Math.imul(t^t>>>7,61|t))^t; return ((t^t>>>14)>>>0)/4294967296; }; }
function gauss(rng){ let u=0,v=0; while(u===0)u=rng(); while(v===0)v=rng(); return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v); }

function monteCarlo(bars, opts){
  opts = opts || {};
  const horizon = opts.horizon || 5;
  const nPaths = opts.nPaths || 2000;
  const seed = opts.seed != null ? opts.seed : 0x9E3779B1;
  if(!bars || bars.length < 40) return null;
  const closes = bars.map(b => b.c);
  const n = closes.length;
  const rets = [];
  for(let i=1;i<n;i++) rets.push(Math.log(closes[i]/closes[i-1]));
  const mu = rets.reduce((a,b)=>a+b,0)/rets.length;
  const va = rets.reduce((a,r)=>a+(r-mu)*(r-mu),0)/rets.length;
  const sigma = Math.sqrt(va);
  const last = closes[n-1];

  function pct(sorted, q){ if(!sorted.length) return 0; const idx=(sorted.length-1)*q; const lo=Math.floor(idx), hi=Math.ceil(idx); if(lo===hi) return sorted[lo]; return sorted[lo]*(hi-idx)+sorted[hi]*(idx-lo); }
  function qs(arr){ const s=Array.from(arr).sort((a,b)=>a-b); return [pct(s,0.05),pct(s,0.25),pct(s,0.5),pct(s,0.75),pct(s,0.95)]; }

  function simulate(stepFn){
    const cur = new Float64Array(nPaths); cur.fill(last);
    const fan = [];
    for(let t=0;t<horizon;t++){ for(let p=0;p<nPaths;p++) cur[p]=stepFn(cur[p]); fan.push(qs(cur)); }
    const term = Array.from(cur);
    let up=0, down=0; for(const x of term){ if(x>last) up++; else if(x<last) down++; }
    const tp = qs(term);
    return { fan, p5:+tp[0].toFixed(2), p25:+tp[1].toFixed(2), p50:+tp[2].toFixed(2), p75:+tp[3].toFixed(2), p95:+tp[4].toFixed(2),
      pUp:+(up/nPaths*100).toFixed(1), pDown:+(down/nPaths*100).toFixed(1), pFlat:+((nPaths-up-down)/nPaths*100).toFixed(1) };
  }

  const rng = mulberry32(seed);
  const boot = simulate(prev => prev * Math.exp(rets[Math.floor(rng()*rets.length)]));
  const gbm = simulate(prev => prev * Math.exp((mu - sigma*sigma/2) + sigma*gauss(rng)));

  return { horizon, nPaths, n, last:+last, mu_pct:+(mu*100).toFixed(3), sigma_pct:+(sigma*100).toFixed(2), bootstrap:boot, gbm:gbm,
    recent: closes.slice(-60).map(c => +c.toFixed(2)) };
}

/* GBM fan with EXPLICIT drift/vol — used for the news-conditioned forward path
   (inject a sentiment bias β into mu, a news-vol coefficient into sigma). */
function gbmFanCustom(last, mu, sigma, horizon, nPaths, seed){
  const H = horizon || 5, N = nPaths || 2000;
  const rng = mulberry32(seed == null ? 0x9E3779B1 : seed);
  const cur = new Float64Array(N); cur.fill(last);
  const fan = [];
  for(let t=0;t<H;t++){
    for(let p=0;p<N;p++) cur[p] = cur[p] * Math.exp((mu - sigma*sigma/2) + sigma*gauss(rng));
    const s = Array.from(cur).sort((a,b)=>a-b);
    const pct = q => { const i=(s.length-1)*q; const lo=Math.floor(i), hi=Math.ceil(i); return lo===hi ? s[lo] : s[lo]*(hi-i)+s[hi]*(i-lo); };
    fan.push({ p10:+pct(0.10).toFixed(2), p50:+pct(0.50).toFixed(2), p90:+pct(0.90).toFixed(2) });
  }
  return fan;
}

function analyzeSymbol(sym, bars, u, cond){
  if(!bars || bars.length < 60) return null;
  const k = structure(bars), mf = ensemble(bars, k, u);
  const bucket = mf.consensus >= 0.60 ? 'bull' : (mf.consensus <= 0.40 ? 'bear' : 'neutral');
  const perSym = cond && cond.per_symbol ? cond.per_symbol[sym] : null;
  const pooled = cond && cond.pooled ? cond.pooled : null;
  const cn = cone(bars, bucket, perSym, pooled), tl = tradeLevels(bars, k, mf.consensus);
  const prev = bars[bars.length-2] ? bars[bars.length-2].c : bars[bars.length-1].c, chg = (bars[bars.length-1].c/prev-1)*100;
  return {symbol:sym, yahoo:'', currency:'', last:bars[bars.length-1].c, chg_pct:+chg.toFixed(2),
    structure:k, ensemble:mf, cone:cn, trade:tl, conviction:conviction(cn, tl), n_bars:bars.length,
    mc: monteCarlo(bars)};
}

/* ── data fetchers ── */
async function fetchBinance(sym, limit = 1000){ const r = await fetch(`https://data-api.binance.vision/api/v3/klines?symbol=${sym}&interval=1d&limit=${limit}`);
  if(!r.ok){ let m = 'Binance HTTP '+r.status; try{const e = await r.json(); if(e && e.msg) m = 'Binance: '+e.msg;}catch(_){} throw new Error(m); }
  return (await r.json()).map(k=>({o:+k[1],h:+k[2],l:+k[3],c:+k[4],v:+k[5]})); }
async function fetchAlpaca(sym, limit = 512){ const r = await fetch(`/api/stocks/klines?symbol=${sym}&timeframe=1d&limit=${limit}`);
  if(!r.ok){ let m = 'Stocks API HTTP '+r.status; try{const e = await r.json(); if(e && e.error) m = e.error;}catch(_){} throw new Error(m); }
  return (await r.json()).map(b=>({o:+b.open,h:+b.high,l:+b.low,c:+b.close,v:+b.volume})); }
async function fetchFutures(sym, limit = 512){ const r = await fetch(`/api/stocks/klines?symbol=${sym}1!&timeframe=1d&limit=${limit}`);
  if(!r.ok){ let m = 'Futures API HTTP '+r.status; try{const e = await r.json(); if(e && e.error) m = e.error;}catch(_){} throw new Error(m); }
  return (await r.json()).map(b=>({o:+b.open,h:+b.high,l:+b.low,c:+b.close,v:+b.volume})); }

/* Fetch + analyze the whole universe, returning {results, sources, liveCount}.
   `cond` = the conditional-cone buckets (per_symbol + pooled), passed through to analyzeSymbol. */
async function fetchLive(cond){
  const out = [], sources = {}, barMap = {};
  await Promise.all([
    ...CRYPTO.map(async sym=>{ try{ barMap[sym] = await fetchBinance(sym); sources[sym] = 'binance'; }catch(e){ sources[sym] = 'error'; } }),
    ...EQUITY.map(async sym=>{ try{ barMap[sym] = await fetchAlpaca(sym); sources[sym] = 'alpaca'; }catch(e){ sources[sym] = 'error'; } }),
    ...FUTURES.map(async sym=>{ try{ barMap[sym] = await fetchFutures(sym); sources[sym] = 'alpaca-futures'; }catch(e){ sources[sym] = 'error'; } })
  ]);
  const rocs = [];
  for(const sym of ALL_SYMBOLS){ const bars = barMap[sym]; if(bars && bars.length >= MOM_WINDOW+1) rocs.push(bars[bars.length-1-MOM_SKIP].c/bars[bars.length-1-MOM_WINDOW].c-1); }
  const med = median(rocs), mad = median(rocs.map(r=>Math.abs(r-med)));
  const u = {cs_median:med, cs_mad:mad};
  for(const sym of ALL_SYMBOLS){ const bars = barMap[sym]; if(!bars) continue; const r = analyzeSymbol(sym, bars, u, cond); if(r) out.push(r); }
  out.sort((a,b)=>((a.trade.direction!=='HOLD'?0:1)-(b.trade.direction!=='HOLD'?0:1)) || (b.conviction-a.conviction));
  return {results:out, sources, liveCount:out.length};
}

/* ── shared render helpers (deterministic HTML strings) ── */
function coneBar(c){ if(!c) return '<span class="fl">—</span>';
  return `<div class="bar"><div class="b" style="width:${c.bull}%"></div><div class="r" style="width:${c.bear}%"></div></div>
   <div class="lbl"><span>B ${c.bull}%</span><span>${c.base}%</span><span>R ${c.bear}%</span></div>`; }

function coneScopeLabel(c){
  const b = c.bucket || '';
  if(c.scope === 'symbol') return 'this name when the signal said ' + b + ' · n=' + c.n;
  if(c.scope === 'universe') return 'whole book when the signal said ' + b + ' · n=' + c.n;
  return 'unconditional base rate (thin bucket) · n=' + c.n;
}

function sigClass(s){ return s==='bull'?'up':(s==='bear'?'dn':'fl'); }
function sigLabel(s){ return s==='bull'?'▲':(s==='bear'?'▼':'·'); }

function structureTags(k){
  const tags = [];
  tags.push(['trend '+(k.trend==='up'?'↗':k.trend==='down'?'↘':'→'), k.trend!=='range']);
  tags.push(['break '+(k.mss?k.mss:'—'), !!k.mss]);
  tags.push(['gap '+(k.fvg?k.fvg.dir[0]:'—'), !!k.fvg]);
  tags.push(['key '+(k.order_block?k.order_block.dir[0]:'—'), !!k.order_block]);
  tags.push(['sweep '+(k.sweep?k.sweep.dir[0]:'—'), !!k.sweep]);
  return tags.map(t=>`<span class="tag ${t[1]?'on':''}">${t[0]}</span>`).join('');
}

function agentRows(agents){
  return agents.map(a=>`<div class="agent"><span class="nm">${a.name}</span>
    <span class="sg ${sigClass(a.signal)}">${sigLabel(a.signal)} ${a.signal}</span>
    <span class="cf">${a.confidence.toFixed(2)}</span>
    <span class="wh">${a.why}</span></div>`).join('');
}

function earnInfo(cat){
  const dates = (cat && cat.earnings_8k_dates && cat.earnings_8k_dates.length) ? cat.earnings_8k_dates : ((cat && cat.earnings_dates) || []);
  if(!dates.length) return { last: null, next: null };
  const last = dates[0];
  const lastDaysAgo = Math.round((Date.now() - new Date(last + 'T00:00:00').getTime()) / 86400000);
  // estimate next earnings from the median quarterly gap (labeled an estimate)
  let next = null;
  if(dates.length >= 3){
    const gaps = [];
    for(let i = 0; i < dates.length - 1; i++){
      const g = (new Date(dates[i] + 'T00:00:00') - new Date(dates[i+1] + 'T00:00:00')) / 86400000;
      if(g > 60 && g < 130) gaps.push(g);   // quarterly cadence only
    }
    if(gaps.length >= 2){
      const avg = gaps.reduce((a,b) => a + b, 0) / gaps.length;
      const nextDate = new Date(new Date(last + 'T00:00:00').getTime() + avg * 86400000);
      const daysOut = Math.round((nextDate - Date.now()) / 86400000);
      next = daysOut <= 0 ? 'overdue' : '~' + daysOut + 'd';
    }
  }
  return { last: last + ' · ' + lastDaysAgo + 'd ago', next };
}

/* catalyst box: pass the catalyst record for the symbol (may be undefined).
   Context only — catalysts are deliberately NOT in the consensus signal. */
function catalystBox(cat){
  if(!cat || !cat.insider) return '';
  const ins = cat.insider;
  const ei = earnInfo(cat);
  const buys = ins.buys || 0;
  const sells = ins.sells || 0;
  const insLabel = buys > 0
    ? `<span class="v up">${buys} buy${buys>1?'s':''} — bullish</span>`
    : `<span class="v fl">none (${sells} sells, routine)</span>`;
  return `<div class="dbox">
    <h4>Catalyst — SEC EDGAR · context, not a signal</h4>
    <div class="lv"><span class="n">insider open-market buys (30d)</span>${insLabel}</div>
    <div class="lv"><span class="n">last earnings (8-K)</span><span class="v">${ei.last || '—'}</span></div>
    <div class="lv"><span class="n">next earnings (est.)</span><span class="v">${ei.next || '—'}</span></div>
  </div>`;
}
