// Base de la API para acciones (refresh/status). En prod va detrás de CloudFront
// en /api (mismo origen). Se puede override con window.__BIRRAS_API__.
const API_BASE = (typeof window !== "undefined" && window.__BIRRAS_API__) || "/api";

// La matriz es un archivo estático servido por el CDN (lecturas gratis).
export const MATRIX_URL = "/published/matrix_latest.json";
export const CSV_URL = "/published/matrix_latest.csv";
export const JSON_URL = "/published/matrix_latest.json";

export async function fetchMatrix() {
  const r = await fetch(MATRIX_URL, { cache: "no-store" });
  if (!r.ok) throw new Error(`No pude cargar la matriz (${r.status})`);
  return r.json();
}

export async function triggerRefresh() {
  const r = await fetch(`${API_BASE}/refresh`, { method: "POST" });
  if (!r.ok) throw new Error(`refresh falló (${r.status})`);
  return r.json();
}

export async function fetchStatus() {
  const r = await fetch(`${API_BASE}/status`);
  if (!r.ok) throw new Error(`status falló (${r.status})`);
  return r.json();
}
