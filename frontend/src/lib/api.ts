export type Speaker = "profissional" | "paciente";
export interface Utt { speaker: Speaker; text: string; ts: number }
export type Source = "rules" | "llm" | "both" | "manual" | "calc";
export interface Alt { value: any; confidence: number; evidence?: string; source?: string }
export interface FieldState {
  value: any; source: Source; confidence: number; evidence?: string; confirmed?: boolean; conflict?: boolean;
  alternatives?: Alt[]; rule?: string; note?: string; uncertain?: boolean; status?: string;
}
export type Form = Record<string, FieldState>;
export interface FieldDef {
  id: string; section: string; label: string; type: string; options?: string[]; option_labels?: Record<string, string>;
  required?: boolean; hint?: string; unit?: string; alert?: string;
}
export interface Schema {
  sections: { id: string; title: string; modes: string[] }[]; fields: FieldDef[]; regions: Record<string, string>;
}
export interface Status {
  llm_enabled: boolean; model: string | null; effort: string; badge: string; prices?: { in: number; out: number };
  spacy: { model: string; version: string; pipeline: string[]; ruler_patterns: number };
  settings: { clinic_name: string; professional_name: string; speech_lang: string; clinic_address: string; clinic_phone: string; professional_voice: "auto" | "masculina" | "feminina" };
}

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, { method, headers: body !== undefined ? { "Content-Type": "application/json" } : undefined, body: body !== undefined ? JSON.stringify(body) : undefined });
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* ignore */ }
    throw new Error(msg);
  }
  const ct = r.headers.get("content-type") || "";
  return (ct.includes("json") ? r.json() : r.text()) as Promise<T>;
}

export const api = {
  get: <T = any>(u: string) => req<T>("GET", "/api" + u),
  post: <T = any>(u: string, b?: unknown) => req<T>("POST", "/api" + u, b ?? {}),
  put: <T = any>(u: string, b?: unknown) => req<T>("PUT", "/api" + u, b ?? {}),
  del: <T = any>(u: string) => req<T>("DELETE", "/api" + u),
};

export const sourceLabel: Record<string, string> = { rules: "Regras", llm: "LLM", both: "Ambos", manual: "Manual", calc: "Cálculo" };
