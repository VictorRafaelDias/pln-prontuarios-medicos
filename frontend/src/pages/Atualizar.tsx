import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Play, Search } from "lucide-react";
import { api } from "@/lib/api";
import { age, fmtDate } from "@/lib/utils";
import { Badge, Button, Card, CardContent, Empty, Input } from "@/components/ui";
import { SessionViewer } from "@/components/SessionViewer";

export default function Atualizar() {
  const [q, setQ] = useState("");
  const [list, setList] = useState<any[]>([]);
  const [sel, setSel] = useState<any>(null);
  const nav = useNavigate();
  const [viewSid, setViewSid] = useState<number | null>(null);
  useEffect(() => { const t = setTimeout(() => api.get(`/patients?q=${encodeURIComponent(q)}`).then(setList), 150); return () => clearTimeout(t); }, [q]);
  const open = (id: number) => api.get(`/patients/${id}`).then(setSel);
  const start = async () => {
    try { const s = await api.post("/sessions", { kind: "soap", patient_id: sel.id }); nav(`/consulta/${s.id}`); } catch (e: any) { toast.error(e.message); }
  };
  const last = sel?.sessions?.[sel.sessions.length - 1];
  return (
    <div className="animate-fade-in space-y-6">
      <div><h1 className="text-3xl font-semibold">Atualizar prontuário</h1><p className="text-muted-foreground">Busque o paciente e inicie uma nova sessão de evolução (SOAP).</p></div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-3">
          <div className="relative"><Search className="absolute left-3 top-3 size-4 text-muted-foreground" /><Input className="pl-9" autoFocus placeholder="Nome, telefone, queixa…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          {list.length === 0 ? <Empty title="Nenhum paciente encontrado" /> : list.map((p) => (
            <button key={p.id} onClick={() => open(p.id)} className={`w-full rounded-lg border bg-card p-4 text-left shadow-soft transition-colors hover:border-primary ${sel?.id === p.id ? "border-primary ring-1 ring-primary" : ""}`}>
              <div className="font-medium">{p.name} <span className="text-xs text-muted-foreground">{age(p.birth_date)}</span></div>
              <div className="text-sm text-muted-foreground">{p.main_complaint || "—"} · {p.session_count} sessões</div>
              {p.alerts.length > 0 && <div className="mt-1 flex flex-wrap gap-1">{p.alerts.map((a: string) => <Badge key={a} variant="accent">{a}</Badge>)}</div>}
            </button>))}
        </div>
        <div>
          {!sel ? <Empty title="Selecione um paciente">O resumo da última sessão aparece aqui.</Empty> : (
            <Card><CardContent className="space-y-4 p-6">
              <div><h2 className="text-2xl font-semibold">{sel.name}</h2><p className="text-sm text-muted-foreground">{sel.phone} · {sel.profession}</p></div>
              {sel.alerts.length > 0 && <div className="rounded-md border border-accent bg-accent/10 p-2 text-sm font-medium text-accent">Contraindicações: {sel.alerts.join(", ")}</div>}
              {last ? <div className="rounded-md bg-secondary p-3 text-sm"><div className="mb-1 font-medium">Última sessão — {fmtDate(last.saved_at)} ({last.kind === "soap" ? "SOAP" : "Anamnese"})</div>{last.summary}{last.eva != null && <Badge className="ml-2" variant="accent">EVA {last.eva}</Badge>}</div> : <p className="text-sm text-muted-foreground">Sem sessões anteriores.</p>}
              <Button size="lg" className="w-full" onClick={start}><Play /> Iniciar nova sessão SOAP</Button>
              {sel.sessions.length > 0 && (
                <div><h3 className="mb-2 font-serif text-base font-semibold">Histórico ({sel.sessions.length} sessões)</h3>
                  <ul className="relative space-y-2 border-l-2 border-primary/30 pl-4">
                    {[...sel.sessions].reverse().map((x: any) => (
                      <li key={x.id} className="relative"><span className="absolute -left-[22px] top-2 size-3 rounded-full border-2 border-primary bg-background" />
                        <button onClick={() => setViewSid(x.id)} className="w-full rounded-md border bg-card p-2 text-left text-sm hover:border-primary">
                          <div className="flex items-center justify-between"><span className="font-medium">{fmtDate(x.saved_at)} <Badge variant="outline">{x.kind === "soap" ? "SOAP" : "Anamnese"}</Badge></span>{x.eva != null && <Badge variant="accent">EVA {x.eva}</Badge>}</div>
                          <div className="line-clamp-2 text-xs text-muted-foreground">{x.summary}</div></button></li>))}
                  </ul></div>)}
            </CardContent></Card>
          )}
        </div>
      </div>
      <SessionViewer sid={viewSid} onClose={() => setViewSid(null)} />
    </div>
  );
}
