import React, { useEffect, useMemo, useState } from "react";
import { fetchMatrix, triggerRefresh, fetchStatus, CSV_URL, JSON_URL } from "./api.js";

const money = (n) =>
  n == null ? "" : "$" + Number(n).toLocaleString("es-AR", { maximumFractionDigits: 2 });

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
  const [error, setError] = useState(null);
  const [refresh, setRefresh] = useState({ state: "idle", msg: "" });

  const [q, setQ] = useState("");
  const [brand, setBrand] = useState("");
  const [size, setSize] = useState("");
  const [onlyComparable, setOnlyComparable] = useState(false);
  const [onlyDeal, setOnlyDeal] = useState(false);
  const [per100, setPer100] = useState(false);
  const [sort, setSort] = useState("default");

  const load = () =>
    fetchMatrix().then(setData).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

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

  const platforms = data?.platforms || [];

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
        <span>{rows.length} en la vista</span>
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

      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th className="sticky">Cerveza</th>
              {platforms.map((p) => (
                <th key={p} className="pcol">{p}</th>
              ))}
              <th>Mejor</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <Row key={row.canonical_id} row={row} platforms={platforms} per100={per100} />
            ))}
          </tbody>
        </table>
      </div>
      <footer>
        Precios de referencia para {data.reference_address}. Solo comparación; verificá en cada tienda antes de comprar.
      </footer>
    </div>
  );
}

function Row({ row, platforms, per100 }) {
  return (
    <tr>
      <td className="sticky namecell">
        <div className="name">
          {row.display_name}
          {row.review_needed && <span className="badge review" title="Match tentativo, en revisión">?</span>}
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
          <td key={p} className={`cell ${best ? "best" : ""} ${!c.disponible ? "oos" : ""}`}>
            {!c.disponible ? (
              <span className="oostag">sin stock</span>
            ) : (
              <>
                <div className="price">
                  {best && <span className="dot">●</span>}
                  {per100 ? money(c.precio_por_100ml) : money(c.precio_actual)}
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
