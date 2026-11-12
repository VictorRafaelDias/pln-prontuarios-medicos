import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip as RTip, XAxis, YAxis } from "recharts";
import { ChevronLeft, ChevronRight, Download, FlaskConical, Play, Sparkles } from "lucide-react";
import { api, sourceLabel } from "@/lib/api";
import { cn, download } from "@/lib/utils";
import { useApp } from "@/App";
import Dictionaries from "@/lab/Dictionaries";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Empty, Select, Skeleton, Tabs, TabsContent, TabsList, TabsTrigger, Textarea, Tip } from "@/components/ui";

const SAMPLE = "Profissional: Qual é a sua queixa principal?\nPaciente: É... tipo, uma dor no joelho direito, né, há uns três meses. Dor nota oito, piora de manhã.\nProfissional: Você fuma?\nPaciente: Não fumo mais, parei de fumar há dois anos. Fumava dez cigarros por dia.\nProfissional: Língua pálida, pulso fino. Vou usar E36, BP6 e VB34.";

const fmtVal = (v: any) => (v === true ? "Sim" : v === false ? "Não" : Array.isArray(v) ? v.join(", ") : String(v));
const entStyle = (label: string) => ({ background: `hsl(var(--e-${label}, 0 0% 85%))` });

export default function Lab() {
  const { schema, status } = useApp();
  const [sp] = useSearchParams();
  const [source, setSource] = useState<"draft" | "session" | "text">("text");
  const [sessions, setSessions] = useState<any[]>([]);
  const [sessionId, setSessionId] = useState("");
  const [draftId, setDraftId] = useState<string | null>(sp.get("draft") || localStorage.getItem("qi:lastDraft"));
  const [text, setText] = useState(SAMPLE);
  const [mode, setMode] = useState("anamnese");
  const [a, setA] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(0);
  const [stepMode, setStepMode] = useState(false);

  useEffect(() => { api.get("/sessions-list").then(setSessions); }, []);
  useEffect(() => { if (sp.get("draft")) setSource("draft"); if (sp.get("session")) { setSource("session"); setSessionId(sp.get("session")!); } }, [sp]);

  const analyze = async (useLlm = false) => {
    setBusy(true);
    try {
      let body: any = { mode, use_llm: useLlm, count_llm_tokens: true };
      if (source === "text") body.text = text;
      else if (source === "session") body.session_id = Number(sessionId);
      else { const s = await api.get(`/sessions/${draftId}`); body.utterances = s.transcript; body.mode = s.kind; if (!s.transcript?.length) throw new Error("O rascunho ainda não tem transcrição."); }
      const r = await api.post("/lab/analyze", body);
      setA(r); setStep(0);
    } catch (e: any) { toast.error(e.message); } finally { setBusy(false); }
  };
  useEffect(() => { if (!a && (sp.get("draft") || sp.get("session"))) { const t = setTimeout(() => analyze(), 300); return () => clearTimeout(t); } }, [sessionId, draftId]); // eslint-disable-line

  return (
    <div className="-m-4 min-h-screen space-y-4 bg-[hsl(var(--lab-bg))] p-4 md:-m-8 md:p-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="flex items-center gap-2 text-3xl font-semibold"><FlaskConical className="text-primary" /> Laboratório PLN</h1><p className="text-sm text-muted-foreground">Inspecione cada etapa do pipeline — separado do uso clínico.</p></div>
      </div>
      <Card><CardContent className="grid gap-3 p-4 lg:grid-cols-[auto_1fr_auto]">
        <div className="flex gap-1 rounded-lg bg-muted p-1 text-sm">{([["draft", "Consulta atual"], ["session", "Sessão salva"], ["text", "Testar frase"]] as const).map(([k, l]) => <button key={k} onClick={() => setSource(k)} className={cn("rounded-md px-3 py-1.5", source === k && "bg-card shadow-sm")}>{l}</button>)}</div>
        <div>
          {source === "text" && <Textarea className="font-mono text-xs" rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder='Uma fala por linha; prefixe com "Profissional:" ou "Paciente:"' />}
          {source === "session" && <Select className="w-full" value={sessionId} onChange={(e) => setSessionId(e.target.value)}><option value="">Escolha uma sessão…</option>{sessions.map((s) => <option key={s.id} value={s.id}>#{s.id} · {s.patient} · {s.date} · {s.kind}</option>)}</Select>}
          {source === "draft" && <p className="py-2 text-sm text-muted-foreground">{draftId ? `Rascunho em andamento nº ${draftId}.` : "Nenhuma consulta em andamento. Inicie uma em “Nova consulta”."}</p>}
        </div>
        <div className="flex flex-col gap-2">
          <Button onClick={() => analyze(false)} disabled={busy || (source === "session" && !sessionId) || (source === "draft" && !draftId)}><Play /> {busy ? "Analisando…" : "Analisar"}</Button>
          <Button variant="outline" size="sm" disabled={busy || !status?.llm_enabled} onClick={() => analyze(true)} title={status?.llm_enabled ? "" : "Sem chave da Anthropic"}><Sparkles /> Analisar com LLM</Button>
        </div>
      </CardContent></Card>

      {!a ? (busy ? <Skeleton className="h-96" /> : <Empty title="Escolha uma fonte de texto e clique em Analisar" icon={<FlaskConical className="size-8" />} />) : (
        <Tabs defaultValue="pipeline">
          <TabsList className="h-auto flex-wrap">
            {[["pipeline", "Pipeline"], ["anotado", "Texto anotado"], ["tabelas", "Tabelas"], ["stats", "Estatísticas"], ["compara", "Regras × LLM"], ["avalia", "Avaliação"], ["llm", "Inspeção do LLM"], ["dic", "Dicionários"], ["export", "Exportar"]].map(([v, l]) => <TabsTrigger key={v} value={v}>{l}</TabsTrigger>)}
          </TabsList>
          <TabsContent value="pipeline"><Pipeline a={a} step={step} setStep={setStep} stepMode={stepMode} setStepMode={setStepMode} /></TabsContent>
          <TabsContent value="anotado"><Annotated a={a} /></TabsContent>
          <TabsContent value="tabelas"><Tables a={a} /></TabsContent>
          <TabsContent value="stats"><Stats a={a} /></TabsContent>
          <TabsContent value="compara"><Compare a={a} /></TabsContent>
          <TabsContent value="avalia"><Evaluation /></TabsContent>
          <TabsContent value="llm"><LlmInspect a={a} /></TabsContent>
          <TabsContent value="dic"><Dictionaries onSaved={() => analyze(false)} /></TabsContent>
          <TabsContent value="export"><Export a={a} /></TabsContent>
        </Tabs>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------------------------- Pipeline */
function Pipeline({ a, step, setStep, stepMode, setStepMode }: any) {
  const stages: any[] = a.stages;
  const st = stages[step];
  const [raw, setRaw] = useState(false);
  const visible = stepMode ? step : stages.length - 1;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant={stepMode ? "default" : "outline"} onClick={() => { setStepMode(!stepMode); setStep(0); }}>{stepMode ? "Modo passo a passo: ligado" : "Modo passo a passo"}</Button>
        <Button size="icon" variant="outline" disabled={step === 0} onClick={() => setStep(step - 1)} aria-label="voltar"><ChevronLeft /></Button>
        <Button size="icon" variant="outline" disabled={step === stages.length - 1} onClick={() => setStep(step + 1)} aria-label="avançar"><ChevronRight /></Button>
        <span className="text-sm text-muted-foreground">Etapa {step + 1} de {stages.length} · tempo total {a.timing.total_ms} ms</span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {stages.map((s, i) => (
          <div key={s.id} className="flex items-center gap-1.5">
            <button onClick={() => setStep(i)} style={{ animationDelay: `${i * 90}ms` }} disabled={stepMode && i > step + 0 && false}
              className={cn("step-in rounded-lg border px-3 py-2 text-left transition-all", i === step ? "border-primary bg-primary text-primary-foreground shadow-soft" : "bg-card hover:border-primary", stepMode && i > visible && "opacity-30")}>
              <div className="text-[10px] opacity-70">{s.index}</div><div className="text-xs font-medium">{s.short}</div><div className="font-mono text-[10px] opacity-70">{s.ms} ms</div>
            </button>
            {i < stages.length - 1 && <span className="text-muted-foreground">→</span>}
          </div>))}
      </div>
      <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
        <Card className="h-fit"><CardHeader><CardTitle>{st.index}. {st.name}</CardTitle><Badge variant="muted" className="w-fit font-mono">{st.ms} ms</Badge></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div><b className="text-primary">O que faz</b><p>{st.explain.what}</p></div>
            <div><b className="text-primary">Por quê</b><p>{st.explain.why}</p></div>
            <div><b className="text-primary">Como</b><p>{st.explain.how}</p></div>
          </CardContent></Card>
        <div className="space-y-3">
          <Card><CardHeader className="flex-row items-center justify-between pb-2"><CardTitle className="text-base">Saída</CardTitle><Button size="sm" variant="ghost" onClick={() => setRaw(!raw)}>{raw ? "Visão didática" : "JSON bruto (entrada/saída)"}</Button></CardHeader>
            <CardContent>{raw ? (
              <div className="grid gap-3 md:grid-cols-2">{[["Entrada", st.input], ["Saída", st.output]].map(([l, v]: any) => <div key={l}><div className="mb-1 text-xs font-semibold">{l}</div><pre className="max-h-96 overflow-auto rounded-md bg-muted p-2 font-mono text-[11px]">{JSON.stringify(v, (k, x) => (k === "svg" ? "…" : x), 1)}</pre></div>)}</div>
            ) : <StageView st={st} a={a} />}</CardContent></Card>
        </div>
      </div>
    </div>
  );
}

function StageView({ st, a }: { st: any; a: any }) {
  const o = st.output;
  switch (st.id) {
    case "asr": return <ul className="space-y-1 text-sm">{o.utterances.map((u: any) => <li key={u.idx}><span className="font-mono text-xs text-muted-foreground">[{u.ts}s]</span> <Badge variant={u.speaker === "profissional" ? "outline" : "default"}>{u.speaker}</Badge> {u.text}</li>)}</ul>;
    case "normalize": return (
      <div className="space-y-3">
        <div className="flex flex-wrap gap-1.5">{Object.entries(o.applied).map(([k, v]) => <Badge key={k} variant="default">{k}: {v as number}</Badge>)}</div>
        {o.utterances.map((u: any) => (
          <div key={u.idx} className="rounded-md border p-2 text-sm"><Badge variant="muted">{u.speaker}</Badge>
            <p className="mt-1 leading-7">{u.ops.map((op: any, i: number) => op.op === "equal" ? <span key={i}>{op.a} </span> : <span key={i}>{op.a && <del className="rounded bg-destructive/15 px-0.5 text-destructive">{op.a}</del>} {op.b && <ins className="rounded bg-primary/20 px-0.5 no-underline">{op.b}</ins>} </span>)}</p></div>))}
      </div>);
    case "sentences": return <ol className="list-decimal space-y-1 pl-5 text-sm">{o.sentences.map((s: any) => <li key={s.idx}><Badge variant="muted">{s.speaker}</Badge> {s.text} <span className="font-mono text-[10px] text-muted-foreground">[{s.start}–{s.end}]</span></li>)}</ol>;
    case "tokens": return (
      <div className="space-y-3">
        <div className="grid gap-2 sm:grid-cols-3 text-sm">
          <Stat l="Tokens spaCy (palavras)" v={o.n_tokens} /><Stat l={o.llm_tokens.available ? "Tokens do LLM (real)" : "Tokens do LLM (estimado)"} v={o.llm_tokens.tokens ?? o.llm_tokens.estimated ?? "—"} /><Stat l="Razão LLM / palavras" v={o.llm_tokens.ratio ?? "—"} />
        </div>
        <p className="text-xs text-muted-foreground">{o.llm_tokens.note}</p>
        <div className="flex max-h-72 flex-wrap gap-1 overflow-auto">{o.tokens.map((t: any) => <Tip key={t.i} content={`índice ${t.i} · caracteres ${t.start}–${t.end}`}><span className="rounded border bg-card px-1.5 py-0.5 font-mono text-xs"><sub className="mr-0.5 text-[8px] text-muted-foreground">{t.i}</sub>{t.text}</span></Tip>)}</div>
      </div>);
    case "stopwords": return (
      <div className="space-y-3 text-sm">
        <p className="text-xs text-muted-foreground">Fonte: {o.source}. Removidas: {o.n_removed} · Mantidas: {o.n_kept}</p>
        <div className="rounded-md border-2 border-primary/40 bg-primary/5 p-3"><b>Palavras que o NLTK removeria, mas foram PRESERVADAS:</b>
          <ul className="mt-2 space-y-1">{o.preserved_hits.length === 0 ? <li className="text-muted-foreground">nenhuma neste texto</li> : o.preserved_hits.map((h: any) => <li key={h.i}><Badge variant="solid">{h.text}</Badge> <span className="text-xs">{h.reason}</span></li>)}</ul></div>
        <div><b>Removidas:</b> <span className="text-muted-foreground line-through">{o.removed.map((t: any) => t.text).join(" ")}</span></div>
        <div><b>Mantidas:</b> {o.kept.map((t: any) => t.text).join(" ")}</div>
      </div>);
    case "lemma_stem": return <TokenTable rows={o.rows} cols={["text", "lemma", "stem", "pos"]} head={["Token", "Lema (spaCy)", `Stem (${o.stemmer})`, "POS"]} />;
    case "pos_dep": return (
      <div className="space-y-4">{o.sentences_svg.slice(0, 8).map((g: any) => <div key={g.sent} className="overflow-x-auto rounded-md border bg-card p-2"><div className="mb-1 text-xs text-muted-foreground">{g.text}</div>{g.svg ? <div className="svg-dep" dangerouslySetInnerHTML={{ __html: g.svg }} /> : <p className="text-xs">{g.note || "sem desenho"}</p>}</div>)}</div>);
    case "ner": return <EntityTable ents={a.entities.filter((e: any) => e.clinical || e.source === "spacy")} />;
    case "negation": return (
      <div className="space-y-3 text-sm">
        <div className="flex gap-2"><Badge variant="destructive">negadas {o.summary.negated}</Badge><Badge variant="muted">passado {o.summary.former}</Badge><Badge variant="accent">incertas {o.summary.uncertain}</Badge><Badge>afirmadas {o.summary.affirmed}</Badge></div>
        <table className="w-full text-xs"><thead><tr className="text-left text-muted-foreground"><th>Gatilho</th><th>Tipo</th><th>Escopo (tokens)</th></tr></thead><tbody>{o.triggers.map((t: any, i: number) => <tr key={i} className="border-t"><td className="font-mono">{t.text}</td><td>{t.type}</td><td>{t.scope[0]}–{t.scope[1]}</td></tr>)}</tbody></table>
        <div className="flex flex-wrap gap-1.5">{o.entities.filter((e: any) => e.status !== "afirmado" || e.uncertain).map((e: any) => <Badge key={e.id} variant={e.negated ? "destructive" : e.former ? "muted" : "accent"}>{e.text}: {e.status}{e.uncertain ? " (incerto)" : ""} · {Math.round(e.conf * 100)}%</Badge>)}</div>
      </div>);
    case "mapping": return (
      <div className="space-y-2 text-sm"><p className="text-xs text-muted-foreground">{o.n_candidates} candidatos → {o.n_fields} campos. Similaridade TF-IDF: {o.similarity.scored?.length ?? 0} sentenças avaliadas.</p>
        <table className="w-full text-xs"><thead><tr className="text-left text-muted-foreground"><th>Campo</th><th>Valor</th><th>Conf.</th><th>Regra</th><th>Trecho</th></tr></thead><tbody>{o.candidates.map((c: any, i: number) => <tr key={i} className="border-t align-top"><td className="font-mono">{c.field}</td><td>{fmtVal(c.value)}</td><td>{Math.round(c.conf * 100)}%</td><td className="text-muted-foreground">{c.rule}</td><td className="italic">{c.evidence}</td></tr>)}</tbody></table></div>);
    case "llm": return o.skipped ? <p className="text-sm">⏭ <b>Etapa pulada:</b> {o.reason}</p> : (
      <div className="space-y-1 text-sm">{o.error && <p className="text-destructive">Erro: {o.error}</p>}<p>Modelo <code>{o.model}</code> · {o.n_fields} campos · {o.latency_ms} ms · custo estimado US$ {o.cost_usd}</p>{o.usage && <p className="font-mono text-xs">tokens: {o.usage.input_tokens} entrada / {o.usage.output_tokens} saída</p>}<p className="text-xs text-muted-foreground">Veja prompt e resposta bruta na aba “Inspeção do LLM”.</p></div>);
    case "merge": return (
      <div className="space-y-3 text-sm">
        <div className="flex gap-2">{Object.entries(o.by_source).map(([k, v]) => <Badge key={k} variant="default">{sourceLabel[k] ?? k}: {v as number}</Badge>)}</div>
        <details className="rounded-md border p-2"><summary className="cursor-pointer font-medium">Regras de prioridade da fusão</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-xs">{o.priority_rules.map((r: string) => <li key={r}>{r}</li>)}</ul></details>
        <FieldsTable fields={o.fields} schema={null} />
      </div>);
  }
  return null;
}

const Stat = ({ l, v }: { l: string; v: any }) => <div className="rounded-md border bg-card p-3"><div className="text-xs text-muted-foreground">{l}</div><div className="font-serif text-2xl font-semibold">{v}</div></div>;

function TokenTable({ rows, cols, head }: { rows: any[]; cols: string[]; head: string[] }) {
  return <div className="max-h-96 overflow-auto"><table className="w-full text-xs"><thead className="sticky top-0 bg-card text-left text-muted-foreground"><tr>{head.map((h) => <th key={h} className="p-1">{h}</th>)}</tr></thead><tbody>{rows.filter((r) => r.pos !== "PUNCT").map((r) => <tr key={r.i} className="border-t">{cols.map((c) => <td key={c} className="p-1 font-mono">{r[c]}</td>)}</tr>)}</tbody></table></div>;
}

function EntityTable({ ents }: { ents: any[] }) {
  return <div className="max-h-96 overflow-auto"><table className="w-full text-xs"><thead className="sticky top-0 bg-card text-left text-muted-foreground"><tr><th className="p-1">Trecho</th><th>Categoria</th><th>Estado</th><th>Regra</th><th>Conf.</th></tr></thead><tbody>{ents.map((e) => <tr key={e.id} className="border-t"><td className="p-1"><span className="ent" style={entStyle(e.label)}>{e.text}</span></td><td>{e.title}</td><td>{e.status ?? ""}{e.uncertain ? " · incerto" : ""}</td><td className="font-mono text-[10px] text-muted-foreground">{e.rule}</td><td>{Math.round(e.conf * 100)}%</td></tr>)}</tbody></table></div>;
}

function FieldsTable({ fields }: { fields: Record<string, any>; schema: any }) {
  const { schema } = useApp();
  return <table className="w-full text-xs"><thead className="text-left text-muted-foreground"><tr><th className="p-1">Campo</th><th>Valor</th><th>Origem</th><th>Conf.</th></tr></thead><tbody>{Object.entries(fields).map(([k, f]: any) => <tr key={k} className="border-t align-top"><td className="p-1">{schema?.fields.find((x) => x.id === k)?.label ?? k}</td><td>{fmtVal(f.value)}{f.conflict && <Badge variant="accent" className="ml-1">divergência</Badge>}</td><td><Badge variant={f.source === "both" ? "solid" : "default"}>{sourceLabel[f.source]}</Badge></td><td>{Math.round(f.confidence * 100)}%</td></tr>)}</tbody></table>;
}

/* ------------------------------------------------------------------------------------- Texto anotado */
function Annotated({ a }: { a: any }) {
  const ents = a.entities.filter((e: any) => e.clinical);
  const labels = [...new Set(ents.map((e: any) => e.label))] as string[];
  return (
    <Card><CardContent className="space-y-4 p-5">
      <div className="flex flex-wrap gap-1.5">{labels.map((l) => <span key={l} className="ent text-xs" style={entStyle(l)}>{l}</span>)}<span className="ent-neg text-xs">negado</span><span className="ent-unc text-xs">incerto</span><span className="ent-fmr text-xs">passado</span></div>
      {a.sentences.reduce((acc: any[], s: any) => { const g = acc[acc.length - 1]; if (g && g.utt === s.utt) g.items.push(s); else acc.push({ utt: s.utt, speaker: s.speaker, items: [s] }); return acc; }, []).map((g: any) => (
        <div key={g.utt} className="flex gap-3"><Badge variant={g.speaker === "profissional" ? "outline" : "default"} className="h-fit w-24 justify-center">{g.speaker}</Badge>
          <p className="flex-1 leading-8">{g.items.map((s: any) => {
            const out: any[] = []; let pos = s.start;
            ents.filter((e: any) => e.start >= s.start && e.end <= s.end).forEach((e: any) => {
              if (e.start < pos) return;
              out.push(a.text.slice(pos, e.start));
              out.push(
                <Tip key={e.id} content={<div className="space-y-0.5"><div><b>{e.title}</b> · lema “{e.lemma}”</div><div>Estado: {e.status}{e.uncertain ? " (incerto)" : ""} · confiança {Math.round(e.conf * 100)}%</div><div className="font-mono text-[10px]">{e.rule}</div>{e.triggers?.map((t: any, i: number) => <div key={i} className="text-accent">gatilho: {t.text}</div>)}</div>}>
                  <span className={cn("ent", e.negated && "ent-neg", e.uncertain && "ent-unc", e.former && "ent-fmr")} style={entStyle(e.label)}>{a.text.slice(e.start, e.end)}</span>
                </Tip>);
              pos = e.end;
            });
            out.push(a.text.slice(pos, s.end) + " ");
            return <span key={s.idx}>{out}</span>;
          })}</p></div>))}
    </CardContent></Card>
  );
}

/* ------------------------------------------------------------------------------------- Tabelas */
function Tables({ a }: { a: any }) {
  const st = Object.fromEntries(a.stages.map((s: any) => [s.id, s.output]));
  const stop = new Set(st.stopwords.removed.map((t: any) => t.i));
  const dep = Object.fromEntries(st.pos_dep.rows.map((r: any) => [r.i, r]));
  const rows = st.lemma_stem.rows.map((r: any) => ({ ...r, dep: dep[r.i]?.dep, head: dep[r.i]?.head_text, stop: stop.has(r.i) ? "sim" : "não" }));
  return <Card><CardContent className="p-4"><div className="max-h-[32rem] overflow-auto"><table className="w-full text-xs"><thead className="sticky top-0 bg-card text-left text-muted-foreground"><tr>{["#", "Token", "Lema", "Stem", "POS", "Dependência", "Núcleo", "Stopword"].map((h) => <th key={h} className="p-1.5">{h}</th>)}</tr></thead>
    <tbody>{rows.filter((r: any) => r.pos !== "PUNCT").map((r: any) => <tr key={r.i} className={cn("border-t font-mono", r.stop === "sim" && "text-muted-foreground")}><td className="p-1">{r.i}</td><td>{r.text}</td><td>{r.lemma}</td><td>{r.stem}</td><td>{r.pos}</td><td>{r.dep}</td><td>{r.head}</td><td>{r.stop}</td></tr>)}</tbody></table></div></CardContent></Card>;
}

/* ------------------------------------------------------------------------------------- Estatísticas */
function Stats({ a }: { a: any }) {
  const [tf, setTf] = useState<any>(null);
  useEffect(() => { api.get("/lab/tfidf").then(setTf).catch(() => {}); }, []);
  const s = a.stats;
  const max = s.term_freq[0]?.count || 1;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card><CardHeader><CardTitle className="text-base">Nuvem de termos (lemas)</CardTitle></CardHeader><CardContent className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        {s.term_freq.map((t: any, i: number) => <span key={t.term} className="font-serif" style={{ fontSize: `${0.8 + (t.count / max) * 1.6}rem`, color: i % 3 === 0 ? "hsl(var(--primary))" : i % 3 === 1 ? "hsl(var(--accent))" : "hsl(var(--foreground))", opacity: 0.55 + 0.45 * (t.count / max) }}>{t.term}</span>)}</CardContent></Card>
      <Card><CardHeader><CardTitle className="text-base">Frequência de termos</CardTitle></CardHeader><CardContent className="h-64"><ResponsiveContainer><BarChart data={s.term_freq.slice(0, 12)} layout="vertical" margin={{ left: 30 }}><CartesianGrid horizontal={false} stroke="hsl(var(--border))" /><XAxis type="number" allowDecimals={false} fontSize={11} stroke="hsl(var(--muted-foreground))" /><YAxis type="category" dataKey="term" width={80} fontSize={11} stroke="hsl(var(--muted-foreground))" /><RTip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} /><Bar dataKey="count" fill="hsl(var(--primary))" radius={4} /></BarChart></ResponsiveContainer></CardContent></Card>
      <Card><CardHeader><CardTitle className="text-base">Entidades por categoria</CardTitle></CardHeader><CardContent className="h-64"><ResponsiveContainer><BarChart data={s.entities_by_label} margin={{ bottom: 40 }}><CartesianGrid vertical={false} stroke="hsl(var(--border))" /><XAxis dataKey="label" angle={-35} textAnchor="end" fontSize={10} interval={0} stroke="hsl(var(--muted-foreground))" /><YAxis allowDecimals={false} fontSize={11} stroke="hsl(var(--muted-foreground))" /><RTip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} /><Bar dataKey="count" fill="hsl(var(--accent))" radius={4} /></BarChart></ResponsiveContainer></CardContent></Card>
      <Card><CardHeader><CardTitle className="text-base">N-gramas mais comuns</CardTitle></CardHeader><CardContent className="grid grid-cols-2 gap-3 text-xs"><div><b>Bigramas</b>{s.bigrams.map((t: any) => <div key={t.term} className="flex justify-between border-b py-0.5"><span>{t.term}</span><span className="font-mono">{t.count}</span></div>)}</div><div><b>Trigramas</b>{s.trigrams.map((t: any) => <div key={t.term} className="flex justify-between border-b py-0.5"><span>{t.term}</span><span className="font-mono">{t.count}</span></div>)}</div></CardContent></Card>
      <Card className="lg:col-span-2"><CardHeader><CardTitle className="text-base">TF-IDF por sessão (termos mais característicos de cada paciente)</CardTitle></CardHeader><CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {!tf ? <Skeleton className="h-24" /> : tf.documents.length === 0 ? <p className="text-sm text-muted-foreground">{tf.note}</p> : tf.documents.slice(0, 9).map((d: any, i: number) => (
          <div key={i} className="rounded-md border p-2 text-xs"><div className="mb-1 font-medium">{d.patient} <span className="text-muted-foreground">{d.kind} {d.date}</span></div><div className="flex flex-wrap gap-1">{d.top.slice(0, 8).map((t: any) => <Badge key={t.term} variant="default" title={`TF-IDF ${t.score}`}>{t.term} {t.score}</Badge>)}</div></div>))}
      </CardContent></Card>
    </div>
  );
}

/* ------------------------------------------------------------------------------------- Regras × LLM */
function Compare({ a }: { a: any }) {
  const { schema } = useApp();
  const llm = a.llm_fields as Record<string, any> | null;
  const rules = a.rule_fields as Record<string, any>;
  const ids = [...new Set([...Object.keys(rules), ...Object.keys(llm ?? {})])];
  const ls = a.stages.find((s: any) => s.id === "llm").output;
  const rulesMs = a.stages.filter((s: any) => s.id !== "llm").reduce((x: number, s: any) => x + s.ms, 0);
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2"><Stat l="Regras: tempo / custo" v={`${rulesMs.toFixed(0)} ms / US$ 0`} /><Stat l="LLM: tempo / custo estimado" v={llm ? `${ls.latency_ms} ms / US$ ${ls.cost_usd}` : "—"} /></div>
      {!llm && <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">Sem extração do LLM nesta análise. {ls.reason ?? ""} Com chave configurada, use “Analisar com LLM”.</p>}
      <Card><CardContent className="overflow-auto p-3"><table className="w-full text-xs"><thead className="text-left text-muted-foreground"><tr><th className="p-1">Campo</th><th>Regras</th><th>LLM</th><th>Situação</th></tr></thead><tbody>
        {ids.map((k) => { const r = rules[k], l = llm?.[k]; const same = r && l && JSON.stringify(r.value) === JSON.stringify(l.value); const sit = !llm ? "só regras" : same ? "concordam" : r && l ? "divergem" : r ? "só regras" : "só LLM";
          return <tr key={k} className="border-t align-top"><td className="p-1">{schema?.fields.find((f) => f.id === k)?.label ?? k}</td><td>{r ? fmtVal(r.value) : "—"}</td><td>{l ? fmtVal(l.value) : "—"}</td><td><Badge variant={sit === "concordam" ? "solid" : sit === "divergem" ? "accent" : "muted"}>{sit}</Badge></td></tr>; })}
      </tbody></table></CardContent></Card>
    </div>
  );
}

/* ------------------------------------------------------------------------------------- Avaliação */
function Evaluation() {
  const [ev, setEv] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [minConf, setMinConf] = useState(0);
  const [which, setWhich] = useState("rules");
  const run = async () => { setBusy(true); try { setEv(await api.post("/lab/evaluate", { min_conf: minConf })); } catch (e: any) { toast.error(e.message); } finally { setBusy(false); } };
  const ap = ev?.approaches?.[which];
  return (
    <div className="space-y-4">
      <Card><CardContent className="flex flex-wrap items-center gap-3 p-4">
        <Button onClick={run} disabled={busy}><Play /> {busy ? "Avaliando…" : "Rodar avaliação"}</Button>
        <label className="flex items-center gap-2 text-sm">Confiança mínima <Select value={minConf} onChange={(e) => setMinConf(Number(e.target.value))}>{[0, 0.5, 0.6, 0.7, 0.8].map((v) => <option key={v} value={v}>{v}</option>)}</Select></label>
        <span className="text-xs text-muted-foreground">10 transcrições fictícias anotadas à mão (gold standard). Gold e regras foram escritos pelo mesmo autor: leia o F1 como indicativo, não como medida de generalização.</span>
      </CardContent></Card>
      {ev && (
        <>
          <div className="grid gap-3 sm:grid-cols-3">{["rules", "llm", "hybrid"].map((k) => { const x = ev.approaches[k]; return (
            <button key={k} onClick={() => setWhich(k)} className={cn("rounded-lg border bg-card p-4 text-left shadow-soft", which === k && "border-primary ring-1 ring-primary")}>
              <div className="text-sm font-medium">{{ rules: "Regras", llm: "LLM", hybrid: "Híbrido" }[k]}</div>
              {x.available ? <><div className="font-serif text-3xl font-semibold">F1 {x.overall.f1}</div><div className="text-xs text-muted-foreground">P {x.overall.precision} · R {x.overall.recall} · macro-F1 {x.macro_f1}</div></> : <div className="text-sm text-muted-foreground">indisponível — {x.reason}</div>}
            </button>); })}</div>
          {ap?.available && (
            <div className="grid gap-4 xl:grid-cols-2">
              <Card><CardHeader><CardTitle className="text-base">Precisão, recall e F1 por campo</CardTitle></CardHeader><CardContent className="max-h-96 overflow-auto"><table className="w-full text-xs"><thead className="text-left text-muted-foreground"><tr><th className="p-1">Campo</th><th>TP</th><th>FP</th><th>FN</th><th>P</th><th>R</th><th>F1</th></tr></thead><tbody>{Object.entries<any>(ap.fields).map(([k, v]) => <tr key={k} className="border-t font-mono"><td className="p-1">{k}</td><td>{v.tp}</td><td>{v.fp}</td><td>{v.fn}</td><td>{v.precision}</td><td>{v.recall}</td><td className={v.f1 < 0.6 ? "text-destructive" : ""}>{v.f1}</td></tr>)}</tbody></table></CardContent></Card>
              <Card><CardHeader><CardTitle className="text-base">Matrizes de confusão (campos categóricos)</CardTitle></CardHeader><CardContent className="space-y-4">
                <div className="text-xs">Presença do campo — verdadeiro+: {ap.presence_matrix.tp} · falso+: {ap.presence_matrix.fp} · falso−: {ap.presence_matrix.fn} · verdadeiro−: {ap.presence_matrix.tn}</div>
                {ap.confusion.map((c: any) => (
                  <div key={c.field}><div className="mb-1 font-mono text-xs">{c.field} (linhas = gold, colunas = previsto)</div>
                    <table className="text-xs"><thead><tr><th></th>{c.labels.map((l: string) => <th key={l} className="px-2">{l}</th>)}</tr></thead><tbody>{c.matrix.map((row: number[], i: number) => <tr key={i}><th className="pr-2 text-right">{c.labels[i]}</th>{row.map((n, j) => <td key={j} className={cn("border px-2 text-center", i === j && n > 0 ? "bg-primary/25" : n > 0 ? "bg-destructive/20" : "")}>{n}</td>)}</tr>)}</tbody></table></div>))}
              </CardContent></Card>
              <Card className="xl:col-span-2"><CardHeader><CardTitle className="text-base">Erros ({ap.errors.length})</CardTitle></CardHeader><CardContent className="max-h-96 overflow-auto"><table className="w-full text-xs"><thead className="text-left text-muted-foreground"><tr><th className="p-1">Transcrição</th><th>Tipo</th><th>Campo</th><th>Gold</th><th>Previsto</th><th>Trecho</th></tr></thead><tbody>{ap.errors.map((e: any, i: number) => <tr key={i} className="border-t align-top"><td className="p-1">{e.transcript}</td><td><Badge variant={e.kind === "falso negativo" ? "muted" : "accent"}>{e.kind}</Badge></td><td className="font-mono">{e.field}</td><td>{e.gold != null ? fmtVal(e.gold) : "—"}</td><td>{e.pred != null ? fmtVal(e.pred) : "—"}</td><td className="italic text-muted-foreground">{e.evidence}</td></tr>)}</tbody></table></CardContent></Card>
            </div>)}
        </>)}
    </div>
  );
}

/* ------------------------------------------------------------------------------------- LLM / Exportar */
function LlmInspect({ a }: { a: any }) {
  const o = a.stages.find((s: any) => s.id === "llm").output;
  if (o.skipped) return <Empty title="Nenhuma chamada ao LLM nesta análise">{o.reason}<br />Configure <code>ANTHROPIC_API_KEY</code> no <code>.env</code> e use “Analisar com LLM”.</Empty>;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="lg:col-span-2"><CardContent className="flex flex-wrap gap-4 p-4 text-sm"><span>Modelo <code>{o.model}</code></span><span>{o.latency_ms} ms</span><span>tokens: {o.usage?.input_tokens} in / {o.usage?.output_tokens} out</span><span>custo estimado US$ {o.cost_usd}</span>{o.error && <span className="text-destructive">{o.error}</span>}</CardContent></Card>
      {[["Prompt do sistema", o.prompt?.system], ["Prompt do usuário (schema + transcrição)", o.prompt?.user], ["Resposta bruta (JSON)", o.raw_response], ["Schema de saída", o.prompt ? JSON.stringify(o.prompt.schema, null, 1) : ""]].map(([l, v]) => <Card key={l as string}><CardHeader><CardTitle className="text-base">{l}</CardTitle></CardHeader><CardContent><pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 font-mono text-[11px]">{v}</pre></CardContent></Card>)}
    </div>
  );
}

function Export({ a }: { a: any }) {
  const get = async (fmt: string, name: string, type: string) => {
    const r = await fetch(`/api/lab/export/${fmt}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(a) });
    if (!r.ok) return toast.error("Falha ao exportar");
    download(name, await r.blob(), type);
  };
  return <Card><CardContent className="flex flex-wrap gap-3 p-5">
    <Button variant="outline" onClick={() => get("json", "analise-pln.json", "application/json")}><Download /> JSON completo (todas as etapas)</Button>
    <Button variant="outline" onClick={() => get("html", "relatorio-pln.html", "text/html")}><Download /> Relatório HTML</Button>
    <Button variant="outline" onClick={() => get("pdf", "relatorio-pln.pdf", "application/pdf")}><Download /> Relatório PDF</Button>
  </CardContent></Card>;
}
