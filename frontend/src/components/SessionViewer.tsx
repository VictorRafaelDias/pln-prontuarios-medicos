import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileDown, FlaskConical } from "lucide-react";
import { api, sourceLabel } from "@/lib/api";
import { cn, fmtClock, fmtDate, isEmpty } from "@/lib/utils";
import { useApp } from "@/App";
import { Badge, Button, Dialog, DialogContent, DialogDescription, DialogTitle, Skeleton, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui";

const show = (v: any) => (v === true ? "Sim" : v === false ? "Não" : Array.isArray(v) ? v.join(", ") : String(v));

/** Visualizador somente leitura de uma sessão salva: campos (com origem), transcrição e resumo do pipeline. */
export function SessionViewer({ sid, onClose }: { sid: number | null; onClose: () => void }) {
  const { schema } = useApp();
  const nav = useNavigate();
  const [s, setS] = useState<any>(null);
  useEffect(() => { setS(null); if (sid) api.get(`/sessions/${sid}`).then(setS); }, [sid]);
  const sections = schema?.sections.filter((x) => s && x.modes.includes(s.kind)) ?? [];
  const pipe = s?.pipeline?.stages as any[] | undefined;
  return (
    <Dialog open={!!sid} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogTitle>{s ? `${s.kind === "soap" ? "Sessão SOAP" : "Anamnese"} — ${fmtDate(s.saved_at, true)}` : "Sessão"}</DialogTitle>
        <DialogDescription>{s?.summary}</DialogDescription>
        {!s ? <Skeleton className="h-64" /> : (
          <Tabs defaultValue="campos">
            <TabsList><TabsTrigger value="campos">Campos</TabsTrigger><TabsTrigger value="transcricao">Transcrição ({s.transcript.length})</TabsTrigger><TabsTrigger value="pipeline">Pipeline</TabsTrigger></TabsList>
            <TabsContent value="campos" className="max-h-[55vh] space-y-4 overflow-auto pr-1">
              {sections.map((sec) => {
                const fs = schema!.fields.filter((f) => f.section === sec.id && !isEmpty(s.form[f.id]?.value));
                if (!fs.length) return null;
                return (
                  <div key={sec.id}><h4 className="mb-1 font-serif text-sm font-semibold text-primary">{sec.title}</h4>
                    <dl className="divide-y rounded-md border text-sm">{fs.map((f) => { const st = s.form[f.id]; return (
                      <div key={f.id} className="flex flex-wrap items-start gap-2 px-3 py-1.5"><dt className="w-44 shrink-0 text-muted-foreground">{f.label}</dt><dd className="min-w-0 flex-1">{f.type === "bodymap" ? st.value.map((r: string) => schema!.regions[r] ?? r).join(", ") : show(st.value)}</dd>
                        <Badge variant={st.source === "manual" ? "outline" : "default"}>{sourceLabel[st.source] ?? st.source}{st.confirmed === false ? " · sugestão" : ""}</Badge></div>); })}</dl></div>);
              })}
            </TabsContent>
            <TabsContent value="transcricao" className="max-h-[55vh] space-y-2 overflow-auto pr-1">
              {s.transcript.length === 0 ? <p className="text-sm text-muted-foreground">Sem transcrição.</p> : s.transcript.map((u: any, i: number) => (
                <div key={i} className={cn("flex", u.speaker === "profissional" ? "" : "justify-end")}><div className={cn("max-w-[85%] rounded-2xl px-3 py-2 text-sm", u.speaker === "profissional" ? "bg-secondary" : "bg-primary/15")}>
                  <div className="mb-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">{u.speaker} · {fmtClock(u.ts)}</div>{u.text}</div></div>))}
            </TabsContent>
            <TabsContent value="pipeline" className="space-y-3">
              {!pipe ? <p className="text-sm text-muted-foreground">Resultado do pipeline não disponível para esta sessão.</p> : (
                <>
                  <p className="text-sm text-muted-foreground">Resultado do pipeline salvo junto da sessão: {s.pipeline.entities?.length ?? 0} entidades, tempo total {s.pipeline.timing?.total_ms} ms.</p>
                  <div className="flex flex-wrap gap-1.5">{pipe.map((st) => <Badge key={st.id} variant="muted" className="font-mono">{st.index}. {st.short ?? st.id} · {st.ms} ms</Badge>)}</div>
                  <Button size="sm" variant="outline" onClick={() => nav(`/laboratorio?session=${s.id}`)}><FlaskConical /> Abrir no Laboratório PLN</Button>
                </>)}
            </TabsContent>
          </Tabs>)}
        {s && <div className="flex justify-end"><Button size="sm" variant="outline" onClick={() => window.open(`/api/sessions/${s.id}/pdf`, "_blank")}><FileDown /> PDF</Button></div>}
      </DialogContent>
    </Dialog>
  );
}
