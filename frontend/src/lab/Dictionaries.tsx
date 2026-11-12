import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, RefreshCw, Save, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { fold } from "@/lib/utils";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Skeleton, Textarea } from "@/components/ui";
import { NormalizationEditor, StopwordsEditor, TriggersEditor } from "@/lab/ConfigEditors";

interface Entry { canonical: string; variants: string[]; attrs?: Record<string, any> }
interface Res { name: string; kind: string; label: string | null; entries: number | null; description: string }

export default function Dictionaries({ onSaved }: { onSaved: () => void }) {
  const [list, setList] = useState<Res[]>([]);
  const [sel, setSel] = useState("");
  const [data, setData] = useState<any>(null);
  const [raw, setRaw] = useState("");
  const [rawMode, setRawMode] = useState(false);
  const [q, setQ] = useState("");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.get("/lab/resources").then((l: Res[]) => { setList(l); setSel(l[0]?.name ?? ""); }); }, []);
  useEffect(() => {
    if (!sel) return;
    setData(null); setDirty(false);
    api.get(`/lab/resources/${sel}`).then((d) => { setData(d); setRaw(JSON.stringify(d, null, 2)); });
  }, [sel]);

  const isDict = data && Array.isArray(data.entries);
  const STRUCTURED: Record<string, any> = { negation_triggers: TriggersEditor, stopwords_custom: StopwordsEditor, normalization: NormalizationEditor };
  const Structured = STRUCTURED[sel];
  const setWhole = (d: any) => { setData(d); setRaw(JSON.stringify(d, null, 2)); setDirty(true); };
  const cur = list.find((r) => r.name === sel);

  const setEntry = (i: number, patch: Partial<Entry>) => {
    const entries = data.entries.map((e: Entry, j: number) => (j === i ? { ...e, ...patch } : e));
    const d = { ...data, entries };
    setData(d); setRaw(JSON.stringify(d, null, 2)); setDirty(true);
  };
  const addEntry = () => { const d = { ...data, entries: [{ canonical: "", variants: [], attrs: {} }, ...data.entries] }; setData(d); setRaw(JSON.stringify(d, null, 2)); setDirty(true); };
  const delEntry = (i: number) => { const d = { ...data, entries: data.entries.filter((_: any, j: number) => j !== i) }; setData(d); setRaw(JSON.stringify(d, null, 2)); setDirty(true); };

  const save = async () => {
    let payload = data;
    if (rawMode) {
      try { payload = JSON.parse(raw); } catch (e: any) { toast.error("JSON inválido: " + e.message); return; }
    }
    setBusy(true);
    try {
      const r = await api.put(`/lab/resources/${sel}`, payload);
      toast.success(`Salvo. EntityRuler reconstruído (${r.ruler_patterns} padrões). Reprocessando a análise…`);
      setData(payload); setRaw(JSON.stringify(payload, null, 2)); setDirty(false);
      api.get("/lab/resources").then(setList);
      onSaved();
    } catch (e: any) { toast.error(e.message); } finally { setBusy(false); }
  };

  const shown = isDict ? data.entries.map((e: Entry, i: number) => ({ e, i })).filter(({ e }: any) => !q || fold(e.canonical + " " + e.variants.join(" ")).includes(fold(q))) : [];

  return (
    <div className="grid gap-4 lg:grid-cols-[16rem_1fr]">
      <Card className="h-fit"><CardHeader><CardTitle className="text-base">Recursos editáveis</CardTitle></CardHeader><CardContent className="space-y-1">
        {list.map((r) => (
          <button key={r.name} onClick={() => setSel(r.name)} className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-secondary ${sel === r.name ? "bg-primary/15 font-medium text-primary" : ""}`}>
            <span className="font-mono text-xs">{r.name}</span>{r.entries != null ? <Badge variant="muted">{r.entries}</Badge> : <Badge variant="outline">config</Badge>}
          </button>))}
      </CardContent></Card>
      <div className="space-y-3">
        {!data ? <Skeleton className="h-64" /> : (
          <>
            <Card><CardContent className="space-y-2 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div><span className="font-mono text-sm font-semibold">{sel}.json</span> {cur?.label && <Badge variant="default">{cur.label}</Badge>}</div>
                <div className="flex gap-2">
                  {(isDict || Structured) && <Button size="sm" variant="ghost" onClick={() => setRawMode(!rawMode)}>{rawMode ? "Editor estruturado" : "Editar JSON"}</Button>}
                  <Button size="sm" onClick={save} disabled={busy || (!dirty && !rawMode)}><Save /> Salvar e reprocessar</Button>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">{data.description ?? data._doc ?? cur?.description}</p>
              <p className="text-xs text-muted-foreground"><RefreshCw className="mr-1 inline size-3" />Ao salvar, o EntityRuler é reconstruído na hora e a análise atual é refeita.</p>
            </CardContent></Card>
            {Structured && !rawMode ? <Structured data={data} onChange={setWhole} /> : isDict && !rawMode ? (
              <Card><CardContent className="space-y-3 p-4">
                <div className="flex gap-2"><Input placeholder="Filtrar entradas…" value={q} onChange={(e) => setQ(e.target.value)} /><Button variant="outline" onClick={addEntry}><Plus /> Nova entrada</Button></div>
                <div className="max-h-[32rem] space-y-2 overflow-auto pr-1">
                  {shown.map(({ e, i }: any) => (
                    <div key={i} className="grid gap-2 rounded-md border p-2 md:grid-cols-[12rem_1fr_auto]">
                      <Input value={e.canonical} placeholder="termo canônico" onChange={(ev) => setEntry(i, { canonical: ev.target.value })} className="h-9 font-medium" />
                      <Input value={e.variants.join(", ")} placeholder="variantes separadas por vírgula" onChange={(ev) => setEntry(i, { variants: ev.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} className="h-9" />
                      <Button size="icon" variant="ghost" onClick={() => delEntry(i)} aria-label="remover"><Trash2 className="size-4 text-destructive" /></Button>
                      {e.attrs && Object.keys(e.attrs).length > 0 && <div className="flex flex-wrap gap-1 md:col-span-3">{Object.entries(e.attrs).map(([k, v]) => <Badge key={k} variant="muted" className="font-mono">{k}: {JSON.stringify(v)}</Badge>)}</div>}
                    </div>))}
                  {shown.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">Nenhuma entrada.</p>}
                </div>
              </CardContent></Card>
            ) : (
              <Card><CardContent className="p-4"><Textarea className="min-h-[28rem] font-mono text-xs" spellCheck={false} value={raw} onChange={(e) => { setRaw(e.target.value); setDirty(true); }} /></CardContent></Card>
            )}
          </>)}
      </div>
    </div>
  );
}
