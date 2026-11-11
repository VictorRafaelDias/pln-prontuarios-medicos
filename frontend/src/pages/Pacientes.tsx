import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Search } from "lucide-react";
import { api } from "@/lib/api";
import { age, fmtDate, fold } from "@/lib/utils";
import { Badge, Card, CardContent, Empty, Input, Select, Skeleton } from "@/components/ui";

export default function Pacientes() {
  const [list, setList] = useState<any[] | null>(null);
  const [q, setQ] = useState("");
  const [period, setPeriod] = useState("all");
  const [smoker, setSmoker] = useState("all");
  const [complaint, setComplaint] = useState("");
  const [sp] = useSearchParams();
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { api.get("/patients").then(setList); }, []);
  useEffect(() => { if (sp.get("focus")) ref.current?.focus(); }, [sp, list]);
  const shown = useMemo(() => {
    if (!list) return [];
    const terms = fold(q).split(/\s+/).filter(Boolean);
    const days = period === "all" ? null : Number(period);
    return list.filter((p) =>
      terms.every((t) => p.search_text.includes(t)) &&
      (!complaint || fold(p.main_complaint).includes(fold(complaint))) &&
      (smoker === "all" || (smoker === "sim" ? ["atual", "ex"].includes(p.smoking) : p.smoking === smoker)) &&
      (!days || (p.last_session_at && Date.now() - +new Date(p.last_session_at) < days * 86400000)));
  }, [list, q, period, smoker, complaint]);
  return (
    <div className="animate-fade-in space-y-5">
      <h1 className="text-3xl font-semibold">Pacientes</h1>
      <div className="grid gap-3 md:grid-cols-4">
        <div className="relative md:col-span-2"><Search className="absolute left-3 top-3 size-4 text-muted-foreground" /><Input ref={ref} className="pl-9" placeholder="Buscar: nome, telefone, queixa, padrão MTC, pontos (ex.: VB20)…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <Select value={period} onChange={(e) => setPeriod(e.target.value)}><option value="all">Qualquer período</option><option value="30">Últimos 30 dias</option><option value="90">Últimos 90 dias</option><option value="365">Último ano</option></Select>
        <Select value={smoker} onChange={(e) => setSmoker(e.target.value)}><option value="all">Tabagismo: todos</option><option value="atual">Tabagista atual</option><option value="ex">Ex-tabagista</option><option value="nunca">Nunca fumou</option></Select>
        <Input className="md:col-span-2" placeholder="Filtrar por queixa (ex.: joelho)" value={complaint} onChange={(e) => setComplaint(e.target.value)} />
      </div>
      {!list ? <Skeleton className="h-64" /> : shown.length === 0 ? <Empty title="Nenhum paciente encontrado">Ajuste a busca ou os filtros.</Empty> : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {shown.map((p) => (
            <Link key={p.id} to={`/pacientes/${p.id}`}><Card className="h-full transition-all hover:-translate-y-0.5 hover:border-primary"><CardContent className="space-y-2 p-5">
              <div className="flex items-start justify-between"><div className="font-serif text-lg font-semibold">{p.name}</div><span className="text-xs text-muted-foreground">{age(p.birth_date)}</span></div>
              <p className="text-sm text-muted-foreground">{p.main_complaint || "Sem queixa registrada"}</p>
              <div className="flex flex-wrap gap-1">{p.alerts.map((a: string) => <Badge key={a} variant="accent">{a}</Badge>)}{p.mtc_patterns.slice(0, 2).map((m: string) => <Badge key={m} variant="default">{m}</Badge>)}</div>
              <div className="flex justify-between text-xs text-muted-foreground"><span>{p.session_count} sessões · EVA {p.last_eva ?? "—"}</span><span>{fmtDate(p.last_session_at)}</span></div>
            </CardContent></Card></Link>))}
        </div>)}
    </div>
  );
}
