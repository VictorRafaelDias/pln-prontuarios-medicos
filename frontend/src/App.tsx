import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { Home as HomeIcon, UserPlus, ClipboardList, Users, FlaskConical, Settings, Moon, Sun, Leaf, Sparkles } from "lucide-react";
import { api, Schema, Status } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Badge, TooltipProvider } from "@/components/ui";
import Home from "@/pages/Home";
import Consulta from "@/pages/Consulta";
import Atualizar from "@/pages/Atualizar";
import Pacientes from "@/pages/Pacientes";
import Prontuario from "@/pages/Prontuario";
import Lab from "@/pages/Lab";
import Config from "@/pages/Config";
import { GlobalSearch } from "@/components/GlobalSearch";

interface Ctx { schema: Schema | null; status: Status | null; reloadStatus: () => void; points: { code: string; nome: string; meridiano: string }[] }
const AppCtx = createContext<Ctx>({ schema: null, status: null, reloadStatus: () => {}, points: [] });
export const useApp = () => useContext(AppCtx);

const NAV = [
  { to: "/", icon: HomeIcon, label: "Início", end: true },
  { to: "/consulta/nova", icon: UserPlus, label: "Nova consulta" },
  { to: "/atualizar", icon: ClipboardList, label: "Atualizar prontuário" },
  { to: "/pacientes", icon: Users, label: "Pacientes" },
];

export default function App() {
  const [schema, setSchema] = useState<Schema | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [points, setPoints] = useState<Ctx["points"]>([]);
  const [dark, setDark] = useState(() => localStorage.getItem("qi:dark") === "1");
  const [offline, setOffline] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  const reloadStatus = useCallback(() => { api.get<Status>("/status").then((s) => { setStatus(s); setOffline(false); }).catch(() => setOffline(true)); }, []);
  useEffect(() => {
    reloadStatus();
    api.get<Schema>("/form-schema").then(setSchema).catch(() => setOffline(true));
    api.get("/points").then(setPoints).catch(() => {});
  }, [reloadStatus]);
  useEffect(() => { document.documentElement.classList.toggle("dark", dark); localStorage.setItem("qi:dark", dark ? "1" : "0"); }, [dark]);
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setSearchOpen((o) => !o); } };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  return (
    <AppCtx.Provider value={{ schema, status, reloadStatus, points }}>
      <TooltipProvider>
        <div className="flex min-h-screen">
          <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r bg-card/70 p-4 md:flex">
            <div className="mb-6 flex items-center gap-2 px-2">
              <span className="grid size-9 place-items-center rounded-full bg-primary text-primary-foreground"><Leaf className="size-5" /></span>
              <div><div className="font-serif text-lg font-semibold leading-none">Prontuário Qi</div><div className="text-[11px] text-muted-foreground">documentação clínica local</div></div>
            </div>
            <nav className="flex flex-1 flex-col gap-1">
              {NAV.map((n) => (
                <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cn("flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors hover:bg-secondary", isActive && "bg-primary/15 font-medium text-primary")}>
                  <n.icon className="size-4" />{n.label}
                </NavLink>
              ))}
            </nav>
            <div className="space-y-1 border-t pt-3">
              <NavLink to="/laboratorio" className={({ isActive }) => cn("flex items-center gap-3 rounded-md px-3 py-2 text-sm hover:bg-secondary", isActive && "bg-primary/15 font-medium text-primary")}><FlaskConical className="size-4" />Laboratório PLN</NavLink>
              <NavLink to="/configuracoes" className={({ isActive }) => cn("flex items-center gap-3 rounded-md px-3 py-2 text-sm hover:bg-secondary", isActive && "bg-primary/15 font-medium text-primary")}><Settings className="size-4" />Configurações</NavLink>
              <button onClick={() => setDark(!dark)} className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm hover:bg-secondary">{dark ? <Sun className="size-4" /> : <Moon className="size-4" />}{dark ? "Modo claro" : "Modo escuro"}</button>
            </div>
          </aside>
          <main className="min-w-0 flex-1">
            <header className="flex items-center justify-between gap-2 border-b bg-background/80 px-4 py-2 backdrop-blur md:px-8">
              <div className="flex gap-1 md:hidden">{NAV.map((n) => <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cn("rounded-md p-2", isActive && "bg-primary/15 text-primary")} title={n.label}><n.icon className="size-5" /></NavLink>)}
                <NavLink to="/laboratorio" className="rounded-md p-2"><FlaskConical className="size-5" /></NavLink></div>
              <div className="ml-auto flex items-center gap-2">
                <button onClick={() => setSearchOpen(true)} className="hidden items-center gap-2 rounded-md border bg-card px-3 py-1 text-xs text-muted-foreground hover:bg-secondary sm:flex">Buscar <kbd className="rounded border bg-muted px-1 font-mono text-[10px]">Ctrl K</kbd></button>
                {offline && <Badge variant="destructive">API offline</Badge>}
                {status && <Badge variant={status.llm_enabled ? "solid" : "muted"} title={status.llm_enabled ? `Modelo: ${status.model}` : "Defina ANTHROPIC_API_KEY no .env para ativar o LLM"}><Sparkles className="size-3" />{status.badge}</Badge>}
              </div>
            </header>
            <div className="mx-auto max-w-[1500px] p-4 md:p-8">
              <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/consulta/nova" element={<Consulta />} />
                <Route path="/consulta/:id" element={<Consulta />} />
                <Route path="/atualizar" element={<Atualizar />} />
                <Route path="/pacientes" element={<Pacientes />} />
                <Route path="/pacientes/:id" element={<Prontuario />} />
                <Route path="/laboratorio" element={<Lab />} />
                <Route path="/configuracoes" element={<Config />} />
              </Routes>
            </div>
          </main>
        </div>
        <GlobalSearch open={searchOpen} onOpenChange={setSearchOpen} />
        <Toaster position="bottom-right" richColors closeButton />
      </TooltipProvider>
    </AppCtx.Provider>
  );
}
