import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip as RTip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import { AlertTriangle, FileDown, FileText, FlaskConical, Pencil, Play } from "lucide-react";
import { api } from "@/lib/api";
import { age, fmtDate, isEmpty } from "@/lib/utils";
import { useApp } from "@/App";
import { FormView } from "@/components/FormView";
import { SessionViewer } from "@/components/SessionViewer";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Empty, Skeleton, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui";

export default function Prontuario() {
  const { id } = useParams();
  const { schema, points } = useApp();
  const nav = useNavigate();
  const [p, setP] = useState<any>(null);
  const [audit, setAudit] = useState<any[]>([]);
  const [edit, setEdit] = useState(false);
  const [viewSid, setViewSid] = useState<number | null>(null);
  const [form, setForm] = useState<any>({});
  const load = () => api.get(`/patients/${id}`).then((x) => { setP(x); setForm(x.anamnese ?? {}); }).catch((e) => toast.error(e.message));
  useEffect(() => { load(); api.get(`/patients/${id}/audit`).then(setAudit); }, [id]);
  if (!p || !schema) return <Skeleton className="h-96" />;

  const evaData = p.sessions.filter((s: any) => s.eva != null).map((s: any) => ({ data: fmtDate(s.saved_at), EVA: s.eva }));
  const saveAnamnese = async () => {
    const vals: Record<string, any> = {};
    Object.entries<any>(form).forEach(([k, f]) => { if (JSON.stringify(f.value) !== JSON.stringify(p.anamnese?.[k]?.value)) vals[k] = f.value; });
    try { await api.put(`/patients/${id}`, { anamnese: vals }); toast.success("Anamnese atualizada (alterações registradas no histórico)"); setEdit(false); load(); api.get(`/patients/${id}/audit`).then(setAudit); } catch (e: any) { toast.error(e.message); }
  };
  return (
    <div className="animate-fade-in space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h1 className="text-3xl font-semibold">{p.name}</h1><p className="text-muted-foreground">{age(p.birth_date)} · {p.phone} · {p.profession} · {p.email}</p></div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => window.open(`/api/patients/${id}/pdf`, "_blank")}><FileDown /> PDF do prontuário</Button>
          <Button onClick={async () => { const s = await api.post("/sessions", { kind: "soap", patient_id: p.id }); nav(`/consulta/${s.id}`); }}><Play /> Nova sessão SOAP</Button>
        </div>
      </div>
      {p.alerts.length > 0 && <div className="flex items-center gap-3 rounded-lg border-2 border-accent bg-accent/10 p-3 font-medium text-accent"><AlertTriangle /> CONTRAINDICAÇÕES: {p.alerts.join(" · ")}</div>}
      <Tabs defaultValue="anamnese">
        <TabsList className="flex-wrap h-auto"><TabsTrigger value="anamnese">Anamnese</TabsTrigger><TabsTrigger value="sessoes">Sessões ({p.sessions.length})</TabsTrigger><TabsTrigger value="eva">Evolução da dor</TabsTrigger><TabsTrigger value="docs">Documentos</TabsTrigger><TabsTrigger value="hist">Histórico de alterações</TabsTrigger></TabsList>

        <TabsContent value="anamnese">
          <div className="mb-3 flex justify-end gap-2">{edit ? <><Button variant="outline" onClick={() => { setEdit(false); setForm(p.anamnese ?? {}); }}>Cancelar</Button><Button onClick={saveAnamnese}>Salvar alterações</Button></> : <Button variant="outline" onClick={() => setEdit(true)}><Pencil /> Editar anamnese</Button>}</div>
          {isEmpty(p.anamnese) ? <Empty title="Sem anamnese registrada" /> : (
            <div className={edit ? "" : "pointer-events-none opacity-95"}>
              <FormView schema={schema} mode="anamnese" form={form} flash={{}} catalog={points}
                onSet={(k, v) => setForm((f: any) => ({ ...f, [k]: { value: v, source: "manual", confidence: 1, confirmed: true } }))}
                onConfirm={() => {}} onClear={(k) => setForm((f: any) => { const { [k]: _, ...r } = f; return r; })} />
            </div>)}
        </TabsContent>

        <TabsContent value="sessoes">
          <div className="relative space-y-4 border-l-2 border-primary/30 pl-6">
            {[...p.sessions].reverse().map((s: any) => (
              <div key={s.id} className="relative"><span className="absolute -left-[33px] top-2 size-4 rounded-full border-2 border-primary bg-background" />
                <Card><CardHeader className="flex-row items-center justify-between pb-2"><CardTitle className="text-base">{fmtDate(s.saved_at, true)} <Badge variant="outline">{s.kind === "soap" ? "SOAP" : "Anamnese"}</Badge></CardTitle>{s.eva != null && <Badge variant="accent">EVA {s.eva}</Badge>}</CardHeader>
                  <CardContent className="space-y-1 text-sm">
                    <p>{s.summary}</p>
                    {s.form["soap.p_pontos"]?.value && <div className="flex flex-wrap gap-1">{s.form["soap.p_pontos"].value.map((c: string) => <Badge key={c} variant="solid" className="font-mono">{c}</Badge>)}</div>}
                    <div className="flex gap-2 pt-2"><Button size="sm" onClick={() => setViewSid(s.id)}>Ver sessão</Button><Button size="sm" variant="outline" onClick={() => window.open(`/api/sessions/${s.id}/pdf`, "_blank")}><FileDown /> PDF</Button><Button size="sm" variant="ghost" onClick={() => nav(`/laboratorio?session=${s.id}`)}><FlaskConical /> Laboratório</Button></div>
                  </CardContent></Card></div>))}
          </div>
        </TabsContent>

        <TabsContent value="eva">
          <Card><CardHeader><CardTitle>Evolução da dor (EVA 0–10)</CardTitle></CardHeader><CardContent>
            {evaData.length < 2 ? <Empty title="Dados insuficientes">São necessárias ao menos 2 sessões com EVA.</Empty> : (
              <div className="h-72"><ResponsiveContainer><LineChart data={evaData} margin={{ left: -10, right: 16, top: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" /><XAxis dataKey="data" stroke="hsl(var(--muted-foreground))" fontSize={12} /><YAxis domain={[0, 10]} stroke="hsl(var(--muted-foreground))" fontSize={12} />
                <RTip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                <Line type="monotone" dataKey="EVA" stroke="hsl(var(--accent))" strokeWidth={3} dot={{ r: 5, fill: "hsl(var(--accent))" }} /></LineChart></ResponsiveContainer></div>)}
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="docs">
          <Card><CardContent className="divide-y p-2">
            <DocRow name="Prontuário completo" sub="Todas as sessões" href={`/api/patients/${id}/pdf`} />
            {p.sessions.map((s: any) => <div key={s.id}><DocRow name={`Sessão ${fmtDate(s.saved_at)} (${s.kind === "soap" ? "SOAP" : "Anamnese"})`} sub="PDF clínico" href={`/api/sessions/${s.id}/pdf`} /><DocRow name={`Transcrição ${fmtDate(s.saved_at)}`} sub="TXT" href={`/api/sessions/${s.id}/transcript.txt`} /></div>)}
            <div className="flex items-center gap-3 p-3 text-sm"><FileText className="size-4 text-primary" />Termo de consentimento LGPD — registrado em {fmtDate(p.consent_at, true)}</div>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="hist">
          <Card><CardContent className="space-y-1 p-4 text-sm">{audit.length === 0 ? <p className="text-muted-foreground">Sem alterações.</p> : audit.map((a) => <div key={a.id} className="flex gap-3 border-b py-1.5 last:border-0"><span className="w-36 shrink-0 font-mono text-xs text-muted-foreground">{fmtDate(a.at, true)}</span><span className="font-medium">{a.action}</span><span className="text-muted-foreground">{a.field} {a.old != null && `${JSON.stringify(a.old)} →`} {a.new != null && JSON.stringify(a.new)}</span></div>)}</CardContent></Card>
        </TabsContent>
      </Tabs>
      <SessionViewer sid={viewSid} onClose={() => setViewSid(null)} />
    </div>
  );
}

function DocRow({ name, sub, href }: { name: string; sub: string; href: string }) {
  return <a href={href} target="_blank" rel="noreferrer" className="flex items-center gap-3 rounded-md p-3 text-sm hover:bg-secondary"><FileDown className="size-4 text-primary" /><span className="font-medium">{name}</span><span className="text-muted-foreground">{sub}</span></a>;
}
