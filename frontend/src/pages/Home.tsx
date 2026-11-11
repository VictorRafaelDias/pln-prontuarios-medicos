import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertTriangle, ClipboardList, FileClock, UserPlus, Users } from "lucide-react";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/utils";
import { Badge, Card, CardContent, CardHeader, CardTitle, Empty, Skeleton } from "@/components/ui";

export default function Home() {
  const [d, setD] = useState<any>(null);
  const nav = useNavigate();
  useEffect(() => { api.get("/dashboard").then(setD); }, []);
  return (
    <div className="animate-fade-in space-y-8">
      <div><h1 className="text-4xl font-semibold">Bom dia 🌿</h1><p className="text-muted-foreground">O que vamos documentar hoje?</p></div>
      <div className="grid gap-4 md:grid-cols-2">
        <Link to="/consulta/nova" className="group rounded-xl border bg-primary p-8 text-primary-foreground shadow-soft transition-transform hover:-translate-y-0.5">
          <UserPlus className="mb-4 size-9" /><h2 className="text-2xl font-semibold">Novo paciente</h2><p className="mt-1 text-sm opacity-85">Anamnese completa com transcrição ao vivo e preenchimento automático.</p>
        </Link>
        <Link to="/atualizar" className="group rounded-xl border bg-accent p-8 text-accent-foreground shadow-soft transition-transform hover:-translate-y-0.5">
          <ClipboardList className="mb-4 size-9" /><h2 className="text-2xl font-semibold">Atualizar prontuário</h2><p className="mt-1 text-sm opacity-85">Nova sessão de evolução (SOAP) de um paciente já cadastrado.</p>
        </Link>
      </div>
      {!d ? <Skeleton className="h-48" /> : (
        <>
          {d.alerts.length > 0 && (
            <Card className="border-accent/50 bg-accent/5"><CardHeader><CardTitle className="flex items-center gap-2 text-accent"><AlertTriangle className="size-5" />Pacientes com contraindicações</CardTitle></CardHeader>
              <CardContent className="flex flex-wrap gap-2">{d.alerts.map((a: any) => <Link key={a.id} to={`/pacientes/${a.id}`}><Badge variant="accent" className="py-1 text-xs">{a.name}: {a.alerts.join(", ")}</Badge></Link>)}</CardContent></Card>
          )}
          <div className="grid gap-4 lg:grid-cols-3">
            <Card><CardHeader><CardTitle className="flex items-center gap-2"><Users className="size-5 text-primary" />Pacientes</CardTitle></CardHeader>
              <CardContent><div className="font-serif text-5xl font-semibold">{d.n_patients}</div><p className="text-sm text-muted-foreground">{d.n_sessions} sessões registradas</p></CardContent></Card>
            <Card><CardHeader><CardTitle>Atendimentos de hoje</CardTitle></CardHeader><CardContent className="space-y-2">
              {d.today.length === 0 ? <p className="text-sm text-muted-foreground">Nenhum atendimento salvo hoje.</p> : d.today.map((s: any) => <Link key={s.id} to={`/pacientes/${s.patient_id}`} className="block rounded-md bg-secondary p-2 text-sm">{s.patient} · {s.kind === "soap" ? "SOAP" : "Anamnese"}</Link>)}
            </CardContent></Card>
            <Card><CardHeader><CardTitle className="flex items-center gap-2"><FileClock className="size-5 text-accent" />Rascunhos</CardTitle></CardHeader><CardContent className="space-y-2">
              {d.drafts.length === 0 ? <p className="text-sm text-muted-foreground">Sem rascunhos pendentes.</p> : d.drafts.map((s: any) => <button key={s.id} onClick={() => nav(`/consulta/${s.id}`)} className="block w-full rounded-md bg-secondary p-2 text-left text-sm">{s.patient_data?.name || "Sem nome"} · {fmtDate(s.updated_at, true)}</button>)}
            </CardContent></Card>
          </div>
          <Card><CardHeader><CardTitle>Últimos prontuários</CardTitle></CardHeader><CardContent>
            {d.recent.length === 0 ? <Empty title="Nenhum prontuário ainda" /> : (
              <ul className="divide-y">{d.recent.map((s: any) => (
                <li key={s.id}><Link to={`/pacientes/${s.patient_id}`} className="flex items-center justify-between gap-4 py-3 hover:bg-secondary/50">
                  <div><div className="font-medium">{s.patient}</div><div className="text-sm text-muted-foreground">{s.summary}</div></div>
                  <div className="text-right text-xs text-muted-foreground"><Badge variant="outline">{s.kind === "soap" ? "SOAP" : "Anamnese"}</Badge><div>{fmtDate(s.date)}</div></div>
                </Link></li>))}</ul>)}
          </CardContent></Card>
        </>
      )}
    </div>
  );
}
