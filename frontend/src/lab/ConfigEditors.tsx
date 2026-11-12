import { Plus, Trash2 } from "lucide-react";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Label, Textarea } from "@/components/ui";

type Json = Record<string, any>;
interface EditorProps { data: Json; onChange: (d: Json) => void }

/* ------------------------------------------------------------------ Gatilhos de negação / incerteza / estado passado */
const CATS: { key: string; title: string; help: string; fields: ("window" | "factor")[] }[] = [
  { key: "pre", title: "Negação — escopo à direita", help: "“não tenho DIABETES”: a janela conta tokens à direita do gatilho.", fields: ["window"] },
  { key: "post", title: "Negação posposta — escopo à esquerda", help: "“DIABETES ausente”: a janela conta tokens à esquerda.", fields: ["window"] },
  { key: "pseudo", title: "Pseudo-negação (parece gatilho, mas NÃO nega)", help: "“não só”, “sem dúvida”.", fields: [] },
  { key: "termination", title: "Terminadores de escopo", help: "“mas”, “porém”: encerram o alcance de uma negação.", fields: [] },
  { key: "uncertainty", title: "Incerteza — reduz a confiança", help: "factor multiplica a confiança (0,6 = −40%).", fields: ["window", "factor"] },
  { key: "former", title: "Estado passado — escopo à direita", help: "“parei de FUMAR”, “já tive”: marca ex-hábito/ex-condição.", fields: ["window"] },
  { key: "former_post", title: "Estado passado posposto — escopo à esquerda", help: "“TROMBOSE que eu tive”.", fields: ["window"] },
];

export function TriggersEditor({ data, onChange }: EditorProps) {
  const set = (key: string, rows: Json[]) => onChange({ ...data, [key]: rows });
  return (
    <div className="space-y-3">
      <Card><CardContent className="flex flex-wrap items-center gap-3 p-4">
        <Label>Janela padrão (tokens)</Label>
        <Input type="number" min={1} max={20} className="w-24" value={data.window ?? 6} onChange={(e) => onChange({ ...data, window: Number(e.target.value) })} />
        <span className="text-xs text-muted-foreground">Usada quando o gatilho não define a própria janela.</span>
      </CardContent></Card>
      {CATS.map((c) => {
        const rows: Json[] = data[c.key] ?? [];
        return (
          <Card key={c.key}><CardHeader className="flex-row items-start justify-between pb-2">
            <div><CardTitle className="text-base">{c.title} <Badge variant="muted">{rows.length}</Badge></CardTitle><p className="text-xs text-muted-foreground">{c.help}</p></div>
            <Button size="sm" variant="outline" onClick={() => set(c.key, [{ text: "", ...(c.fields.includes("window") ? { window: data.window ?? 6 } : {}), ...(c.fields.includes("factor") ? { factor: 0.8 } : {}) }, ...rows])}><Plus /> Gatilho</Button>
          </CardHeader>
            <CardContent className="space-y-1.5">
              {rows.map((r, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Input className="h-9 flex-1" value={r.text} placeholder="gatilho (ex.: não, nega, sem)" onChange={(e) => set(c.key, rows.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))} />
                  {c.fields.includes("window") && <Input type="number" min={1} max={20} title="janela" className="h-9 w-20" value={r.window ?? ""} onChange={(e) => set(c.key, rows.map((x, j) => (j === i ? { ...x, window: Number(e.target.value) } : x)))} />}
                  {c.fields.includes("factor") && <Input type="number" step={0.05} min={0} max={1} title="fator de confiança" className="h-9 w-20" value={r.factor ?? ""} onChange={(e) => set(c.key, rows.map((x, j) => (j === i ? { ...x, factor: Number(e.target.value) } : x)))} />}
                  <Button size="icon" variant="ghost" onClick={() => set(c.key, rows.filter((_, j) => j !== i))} aria-label="remover"><Trash2 className="size-4 text-destructive" /></Button>
                </div>))}
              {rows.length === 0 && <p className="text-xs text-muted-foreground">Nenhum gatilho.</p>}
            </CardContent></Card>);
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ Stopwords: palavras preservadas por categoria */
const CAT_HELP: Record<string, string> = {
  negacao: "inverte o sentido (não, nunca, nem, sem)", intensidade: "modula a gravidade/quantidade (muito, pouco, mais)",
  tempo: "separa hábito atual de ex-hábito (já, desde, há)", incerteza: "reduz a confiança (talvez, acho)", contraste: "delimita escopo (mas, se)",
};
const csv = (a: string[]) => (a ?? []).join(", ");
const parse = (t: string) => t.split(",").map((x) => x.trim()).filter(Boolean);

export function StopwordsEditor({ data, onChange }: EditorProps) {
  const preserve: Record<string, string[]> = data.preserve ?? {};
  return (
    <div className="space-y-3">
      <Card><CardHeader className="pb-2"><CardTitle className="text-base">Palavras PRESERVADAS (não viram stopword)</CardTitle>
        <p className="text-xs text-muted-foreground">A lista do NLTK removeria estas palavras, mas elas mudam o significado clínico. Separe por vírgula.</p></CardHeader>
        <CardContent className="space-y-3">
          {Object.entries(preserve).map(([cat, words]) => (
            <div key={cat} className="space-y-1"><Label className="capitalize">{cat} <span className="font-normal text-muted-foreground">— {CAT_HELP[cat] ?? ""}</span></Label>
              <Textarea rows={2} value={csv(words)} onChange={(e) => onChange({ ...data, preserve: { ...preserve, [cat]: parse(e.target.value) } })} /></div>))}
        </CardContent></Card>
      <Card><CardHeader className="pb-2"><CardTitle className="text-base">Stopwords extras (oralidade)</CardTitle></CardHeader>
        <CardContent><Textarea rows={3} value={csv(data.extra)} onChange={(e) => onChange({ ...data, extra: parse(e.target.value) })} /></CardContent></Card>
    </div>
  );
}

/* ------------------------------------------------------------------ Normalização: abreviações e marcadores de oralidade */
function KeyValue({ title, help, value, onChange }: { title: string; help?: string; value: Record<string, string>; onChange: (v: Record<string, string>) => void }) {
  const rows = Object.entries(value ?? {});
  const rename = (i: number, k: string, v: string) => onChange(Object.fromEntries(rows.map(([a, b], j) => (j === i ? [k, v] : [a, b]))));
  return (
    <Card><CardHeader className="flex-row items-start justify-between pb-2"><div><CardTitle className="text-base">{title} <Badge variant="muted">{rows.length}</Badge></CardTitle>{help && <p className="text-xs text-muted-foreground">{help}</p>}</div>
      <Button size="sm" variant="outline" onClick={() => onChange({ "": "", ...value })}><Plus /> Adicionar</Button></CardHeader>
      <CardContent className="grid gap-1.5 sm:grid-cols-2">
        {rows.map(([k, v], i) => (
          <div key={i} className="flex items-center gap-1.5">
            <Input className="h-9 w-28 font-mono" value={k} placeholder="abrev." onChange={(e) => rename(i, e.target.value, v)} />→
            <Input className="h-9 flex-1" value={v} placeholder="expansão" onChange={(e) => rename(i, k, e.target.value)} />
            <Button size="icon" variant="ghost" onClick={() => onChange(Object.fromEntries(rows.filter((_, j) => j !== i)))} aria-label="remover"><Trash2 className="size-4 text-destructive" /></Button>
          </div>))}
      </CardContent></Card>
  );
}

export function NormalizationEditor({ data, onChange }: EditorProps) {
  const list = (key: string, label: string, help: string) => (
    <div key={key} className="space-y-1"><Label>{label}</Label><p className="text-xs text-muted-foreground">{help}</p>
      <Textarea rows={2} value={csv(data[key])} onChange={(e) => onChange({ ...data, [key]: parse(e.target.value) })} /></div>
  );
  return (
    <div className="space-y-3">
      <KeyValue title="Abreviações (qualquer caixa)" help="“vc” → “você”, “pq” → “porque”." value={data.abbreviations} onChange={(v) => onChange({ ...data, abbreviations: v })} />
      <KeyValue title="Siglas clínicas (maiúsculas exatas)" help="“HAS” → “hipertensão arterial sistêmica”." value={data.case_sensitive_abbreviations} onChange={(v) => onChange({ ...data, case_sensitive_abbreviations: v })} />
      <Card><CardHeader className="pb-2"><CardTitle className="text-base">Marcadores de oralidade removidos</CardTitle></CardHeader><CardContent className="space-y-3">
        {list("ellipsis_hesitations", "Hesitações com reticências", "“é...”, “ahn...”")}
        {list("interjections", "Interjeições soltas", "“hum”, “ahn”")}
        {list("leading_markers", "Marcadores no início da fala", "“então,”, “bom,”, “olha”")}
        {list("stutter_words", "Palavras funcionais repetidas (gagueira)", "“eu eu sinto” → “eu sinto”")}
        <div className="space-y-1"><Label>Muletas (expressões regulares, uma por linha)</Label>
          <Textarea rows={4} className="font-mono text-xs" value={(data.filler_regex ?? []).join("\n")} onChange={(e) => onChange({ ...data, filler_regex: e.target.value.split("\n").filter((l: string) => l.trim()) })} /></div>
      </CardContent></Card>
    </div>
  );
}
