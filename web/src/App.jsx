import React, { useEffect, useMemo, useState } from "react";
import {
  fetchMatrix,
  fetchHistory,
  fetchHistoryDetail,
  triggerRefresh,
  fetchStatus,
  CSV_URL,
  JSON_URL,
} from "./api.js";

const money = (n) =>
  n == null ? "" : "$" + Number(n).toLocaleString("es-AR", { maximumFractionDigits: 2 });

// Paleta estable por ecommerce (para las líneas del gráfico de historial).
const PALETTE = ["#f5a623", "#2ecc71", "#4aa3ff", "#e056a0", "#9b59b6", "#1abc9c", "#ff6b6b", "#c8cf3a"];
const platColor = (p, all) => PALETTE[Math.max(0, all.indexOf(p)) % PALETTE.length];

function HistoryChart({ series, allPlatforms }) {
  const plats = Object.keys(series || {});
  if (!plats.length) return <div className="nohist">Todavía no hay historial suficiente para esta cerveza.</div>;

  // eje x = unión de timestamps ordenada; y = precio
  const tset = new Set();
  plats.forEach((p) => series[p].forEach(([t]) => tset.add(t)));
  const times = [...tset].sort();
  const tIndex = new Map(times.map((t, i) => [t, i]));
  const prices = plats.flatMap((p) => series[p].map(([, v]) => v));
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = max - min || 1;

  const W = 520, H = 240, PAD = 44;
  const x = (t) => (times.length < 2 ? W / 2 : PAD + (tIndex.get(t) / (times.length - 1)) * (W - PAD - 12));
  const y = (v) => H - 28 - ((v - min) / span) * (H - 28 - 14);

  return (
    <div>
      <svg className="histchart" viewBox={`0 0 ${W} ${H}`} width="100%">
        {/* ejes y labels de precio */}
        <line x1={PAD} y1={14} x2={PAD} y2={H - 28} stroke="var(--line)" />
        <line x1={PAD} y1={H - 28} x2={W - 12} y2={H - 28} stroke="var(--line)" />
        <text x={PAD - 6} y={18} textAnchor="end" className="axis">{money(max)}</text>
        <text x={PAD - 6} y={H - 28} textAnchor="end" className="axis">{money(min)}</text>
        {plats.map((p) => (
          <polyline
            key={p}
            fill="none"
            stroke={platColor(p, allPlatforms)}
            strokeWidth="2"
            points={series[p].map(([t, v]) => `${x(t).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}
          />
        ))}
        {plats.map((p) =>
          series[p].map(([t, v], i) => (
            <circle key={p + i} cx={x(t)} cy={y(v)} r="2.5" fill={platColor(p, allPlatforms)} />
          )),
        )}
      </svg>
      <div className="legend">
        {plats.map((p) => (
          <span key={p} className="lg">
            <span className="sw" style={{ background: platColor(p, allPlatforms) }} />
            {p} <b>{money(series[p][series[p].length - 1][1])}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

function DetailModal({ row, series, allPlatforms, onClose }) {
  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modalhead">
          <div>
            <h3>{row.display_name}</h3>
            <div className="meta">
              {[variantLabel(row.variant_slug), row.volume_ml && `${row.volume_ml}ml`, row.container]
                .filter(Boolean)
                .join(" · ")}
            </div>
          </div>
          <button className="btn ghost" onClick={onClose}>✕</button>
        </div>
        <div className="modalsub">Evolución del precio por ecommerce</div>
        {series === undefined ? (
          <div className="nohist">Cargando historial…</div>
        ) : (
          <HistoryChart series={series} allPlatforms={allPlatforms} />
        )}
      </div>
    </div>
  );
}

function useMediaQuery(query) {
  const [matches, setMatches] = useState(
    () => typeof window !== "undefined" && window.matchMedia(query).matches,
  );
  useEffect(() => {
    const m = window.matchMedia(query);
    const on = () => setMatches(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, [query]);
  return matches;
}

function Sparkline({ points }) {
  if (!points || points.length < 2) return null;
  const vals = points.map((p) => p[1]);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const w = 66;
  const h = 16;
  const span = max - min || 1;
  const step = w / (points.length - 1);
  const d = vals
    .map((v, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${(h - ((v - min) / span) * h).toFixed(1)}`)
    .join(" ");
  const up = vals[vals.length - 1] > vals[0];
  const down = vals[vals.length - 1] < vals[0];
  const color = down ? "var(--green)" : up ? "var(--red)" : "var(--muted)";
  return (
    <svg className="spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`} title="Evolución del más barato">
      <path d={d} fill="none" stroke={color} strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  );
}

function relativeTime(iso) {
  if (!iso) return "—";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "hace instantes";
  const m = Math.floor(diff / 60);
  if (m < 60) return `hace ${m}m`;
  const h = Math.floor(m / 60);
  return `hace ${h}h ${m % 60}m`;
}

const variantLabel = (s) => (!s || s === "unknown" ? "" : s.replace(/-/g, " "));

function minPrice(row) {
  const vals = Object.values(row.precios)
    .filter((c) => c.disponible && c.precio_actual)
    .map((c) => c.precio_actual);
  return vals.length ? Math.min(...vals) : Infinity;
}
function maxDiscount(row) {
  const vals = Object.values(row.precios).map((c) => c.descuento_pct || 0);
  return vals.length ? Math.max(...vals) : 0;
}
function minPer100(row) {
  const vals = Object.values(row.precios)
    .filter((c) => c.disponible && c.precio_por_100ml)
    .map((c) => c.precio_por_100ml);
  return vals.length ? Math.min(...vals) : Infinity;
}

export default function App() {
  const [data, setData] = useState(null);
  const [history, setHistory] = useState({});
  const [error, setError] = useState(null);
  const [refresh, setRefresh] = useState({ state: "idle", msg: "" });

  const [q, setQ] = useState("");
  const [brand, setBrand] = useState("");
  const [size, setSize] = useState("");
  const [hidden, setHidden] = useState(() => new Set());
  const [onlyComparable, setOnlyComparable] = useState(false);
  const [onlyDeal, setOnlyDeal] = useState(false);
  const [per100, setPer100] = useState(false);
  const [sort, setSort] = useState("default");
  const [visibleCount, setVisibleCount] = useState(150); // render incremental
  const [detail, setDetail] = useState(null); // fila seleccionada para el gráfico
  const [hdetail, setHdetail] = useState(null); // historial por-plataforma (lazy)

  const openDetail = (row) => {
    setDetail(row);
    if (hdetail === null) fetchHistoryDetail().then(setHdetail);
  };

  const load = () =>
    Promise.all([fetchMatrix(), fetchHistory()])
      .then(([m, h]) => {
        setData(m);
        setHistory(h || {});
      })
      .catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  const togglePlatform = (p) =>
    setHidden((prev) => {
      const next = new Set(prev);
      next.has(p) ? next.delete(p) : next.add(p);
      return next;
    });

  const brands = useMemo(
    () => [...new Set((data?.products || []).map((p) => p.brand_display))].sort(),
    [data],
  );
  const sizes = useMemo(
    () =>
      [...new Set((data?.products || []).map((p) => p.volume_ml).filter(Boolean))].sort(
        (a, b) => a - b,
      ),
    [data],
  );

  const rows = useMemo(() => {
    let r = data?.products ? [...data.products] : [];
    if (q) {
      const s = q.toLowerCase();
      r = r.filter((x) => x.display_name.toLowerCase().includes(s));
    }
    if (brand) r = r.filter((x) => x.brand_display === brand);
    if (size) r = r.filter((x) => String(x.volume_ml) === size);
    if (onlyComparable) r = r.filter((x) => x.n_platforms > 1);
    if (onlyDeal) r = r.filter((x) => maxDiscount(x) > 0);
    const cmp = {
      default: (a, b) => b.n_platforms - a.n_platforms || a.brand_display.localeCompare(b.brand_display),
      cheap: (a, b) => minPrice(a) - minPrice(b),
      discount: (a, b) => maxDiscount(b) - maxDiscount(a),
      per100: (a, b) => minPer100(a) - minPer100(b),
      brand: (a, b) => a.brand_display.localeCompare(b.brand_display),
    }[sort];
    return r.sort(cmp);
  }, [data, q, brand, size, onlyComparable, onlyDeal, sort]);

  // Render incremental: reseteo al cambiar los filtros, sumo al scrollear cerca del fondo.
  useEffect(() => setVisibleCount(150), [rows]);
  useEffect(() => {
    const onScroll = () => {
      if (window.innerHeight + window.scrollY > document.body.offsetHeight - 900) {
        setVisibleCount((v) => v + 200);
      }
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const platforms = data?.platforms || [];
  const visiblePlatforms = platforms.filter((p) => !hidden.has(p));
  const isMobile = useMediaQuery("(max-width: 719px)");

  async function onRefresh() {
    setRefresh({ state: "running", msg: "Iniciando actualización…" });
    try {
      await triggerRefresh();
      // poll
      for (let i = 0; i < 40; i++) {
        await new Promise((res) => setTimeout(res, 3000));
        const st = await fetchStatus();
        setRefresh({ state: "running", msg: `Actualizando… (${st.status})` });
        if (st.status && st.status !== "RUNNING") break;
      }
      await load();
      setRefresh({ state: "done", msg: "Precios actualizados" });
      setTimeout(() => setRefresh({ state: "idle", msg: "" }), 4000);
    } catch (e) {
      setRefresh({ state: "error", msg: e.message });
      setTimeout(() => setRefresh({ state: "idle", msg: "" }), 6000);
    }
  }

  if (error)
    return (
      <div className="app">
        <div className="error">⚠️ {error}</div>
      </div>
    );
  if (!data) return <div className="app loading">Cargando precios…</div>;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">🍺</span>
          <div>
            <h1>birras</h1>
            <div className="sub">
              {data.reference_address} · actualizado {relativeTime(data.generated_at)} ·{" "}
              {platforms.length} ecommerce{platforms.length !== 1 ? "s" : ""}
            </div>
          </div>
        </div>
        <div className="actions">
          <a className="btn ghost" href={CSV_URL} download>
            ⬇ CSV
          </a>
          <a className="btn ghost" href={JSON_URL} download>
            ⬇ JSON
          </a>
          <button className="btn primary" onClick={onRefresh} disabled={refresh.state === "running"}>
            {refresh.state === "running" ? "⏳ Actualizando…" : "🔄 Actualizar precios"}
          </button>
        </div>
      </header>

      {refresh.msg && <div className={`banner ${refresh.state}`}>{refresh.msg}</div>}

      <div className="stats">
        <span><b>{data.total_canonicos}</b> cervezas</span>
        <span><b>{data.comparables}</b> comparables</span>
        <span>
          {rows.length === data.total_canonicos ? "" : `${rows.length} filtradas · `}
          mostrando {Math.min(visibleCount, rows.length)} de {rows.length}
        </span>
      </div>

      <div className="filters">
        <input
          className="search"
          placeholder="🔍 buscar cerveza…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select value={brand} onChange={(e) => setBrand(e.target.value)}>
          <option value="">Todas las marcas</option>
          {brands.map((b) => (
            <option key={b} value={b}>{b}</option>
          ))}
        </select>
        <select value={size} onChange={(e) => setSize(e.target.value)}>
          <option value="">Todos los tamaños</option>
          {sizes.map((s) => (
            <option key={s} value={s}>{s} ml</option>
          ))}
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="default">Orden: comparables</option>
          <option value="cheap">Más barato</option>
          <option value="discount">Mayor descuento</option>
          <option value="per100">$/100ml</option>
          <option value="brand">Marca</option>
        </select>
        <label className="chk">
          <input type="checkbox" checked={onlyComparable} onChange={(e) => setOnlyComparable(e.target.checked)} />
          solo comparables
        </label>
        <label className="chk">
          <input type="checkbox" checked={onlyDeal} onChange={(e) => setOnlyDeal(e.target.checked)} />
          en oferta
        </label>
        <label className="chk">
          <input type="checkbox" checked={per100} onChange={(e) => setPer100(e.target.checked)} />
          $/100ml
        </label>
      </div>

      <div className="platforms">
        <span className="plabel">Ecommerces:</span>
        {platforms.map((p) => (
          <button
            key={p}
            className={`chip ${hidden.has(p) ? "off" : ""}`}
            onClick={() => togglePlatform(p)}
            title={hidden.has(p) ? "Mostrar columna" : "Ocultar columna"}
          >
            {p}
          </button>
        ))}
      </div>

      {isMobile ? (
        <div className="cards">
          {rows.slice(0, visibleCount).map((row) => (
            <Card
              key={row.canonical_id}
              row={row}
              platforms={visiblePlatforms}
              per100={per100}
              onOpen={openDetail}
            />
          ))}
        </div>
      ) : (
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th className="sticky">Cerveza</th>
                {visiblePlatforms.map((p) => (
                  <th key={p} className="pcol">{p}</th>
                ))}
                <th>Mejor</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, visibleCount).map((row) => (
                <Row
                  key={row.canonical_id}
                  row={row}
                  platforms={visiblePlatforms}
                  per100={per100}
                  history={history[row.canonical_key]}
                  onOpen={openDetail}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {detail && (
        <DetailModal
          row={detail}
          series={hdetail ? hdetail[detail.canonical_key] || {} : undefined}
          allPlatforms={platforms}
          onClose={() => setDetail(null)}
        />
      )}
      <footer>
        Precios de referencia para {data.reference_address}. Solo comparación; verificá en cada tienda antes de comprar.
      </footer>
    </div>
  );
}

function Card({ row, platforms, per100, onOpen }) {
  const entries = platforms.map((p) => ({ p, c: row.precios[p] })).filter((e) => e.c);
  entries.sort((a, b) => {
    const av = a.c.disponible ? (per100 ? a.c.precio_por_100ml : a.c.precio_actual) : Infinity;
    const bv = b.c.disponible ? (per100 ? b.c.precio_por_100ml : b.c.precio_actual) : Infinity;
    return av - bv;
  });
  return (
    <div className="card">
      <div className="cardhead clickable" onClick={() => onOpen(row)} title="Ver evolución de precios">
        <div className="name">
          {row.display_name} <span className="chartico">📈</span>
          {row.review_needed && <span className="badge review" title="Match tentativo">?</span>}
        </div>
        <div className="meta">
          {[variantLabel(row.variant_slug), row.volume_ml && `${row.volume_ml}ml`, row.container, row.pack_qty > 1 && `x${row.pack_qty}`]
            .filter(Boolean)
            .join(" · ")}
        </div>
      </div>
      <div className="cardprices">
        {entries.map(({ p, c }) => {
          const best = row.mejor === p && row.n_platforms > 1;
          return (
            <div key={p} className={`prow ${best ? "best" : ""} ${c.suspect ? "suspect" : ""}`}>
              <span className="pname">{p}</span>
              {c.disponible ? (
                <span className="pval">
                  {best && <span className="dot">●</span>}
                  {per100 ? `${money(c.precio_por_100ml)}/100ml` : money(c.precio_actual)}
                  {c.suspect && <span className="warn">⚠</span>}
                  {c.descuento_pct > 0 && <span className="pct"> -{Math.round(c.descuento_pct)}%</span>}
                </span>
              ) : (
                <span className="oostag">sin stock</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Row({ row, platforms, per100, history, onOpen }) {
  return (
    <tr>
      <td className="sticky namecell clickable" onClick={() => onOpen(row)} title="Ver evolución de precios">
        <div className="name">
          {row.display_name}
          {row.review_needed && <span className="badge review" title="Match tentativo, en revisión">?</span>}
          <Sparkline points={history} />
        </div>
        <div className="meta">
          {[variantLabel(row.variant_slug), row.volume_ml && `${row.volume_ml}ml`, row.container, row.pack_qty > 1 && `pack x${row.pack_qty}`]
            .filter(Boolean)
            .join(" · ")}
          {row.gtin && <span className="gtin"> · {row.gtin}</span>}
        </div>
      </td>
      {platforms.map((p) => {
        const c = row.precios[p];
        if (!c) return <td key={p} className="cell empty">—</td>;
        const best = row.mejor === p && row.n_platforms > 1;
        return (
          <td
            key={p}
            className={`cell ${best ? "best" : ""} ${!c.disponible ? "oos" : ""} ${c.suspect ? "suspect" : ""}`}
            title={c.suspect ? "Precio atípico (posible dato erróneo en la tienda)" : undefined}
          >
            {!c.disponible ? (
              <span className="oostag">sin stock</span>
            ) : (
              <>
                <div className="price">
                  {best && <span className="dot">●</span>}
                  {per100 ? money(c.precio_por_100ml) : money(c.precio_actual)}
                  {c.suspect && <span className="warn">⚠</span>}
                  {per100 && <span className="unit">/100ml</span>}
                </div>
                {c.descuento_pct > 0 && (
                  <div className="disc">
                    <span className="old">{money(c.precio_anterior)}</span>
                    <span className="pct">-{Math.round(c.descuento_pct)}%</span>
                  </div>
                )}
              </>
            )}
          </td>
        );
      })}
      <td className="bestcol">
        {row.mejor && row.n_platforms > 1 ? (
          <>
            <div className="bp">{row.mejor}</div>
            {row.ahorro_abs > 0 && <div className="save">−{money(row.ahorro_abs)}</div>}
          </>
        ) : (
          <span className="empty">—</span>
        )}
      </td>
    </tr>
  );
}
