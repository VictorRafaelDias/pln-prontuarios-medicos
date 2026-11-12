import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Command } from "cmdk";
import { ClipboardList, FlaskConical, Home, Settings, User, UserPlus, Users } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogTitle, Kbd } from "@/components/ui";
import { api } from "@/lib/api";

const PAGES = [
  { to: "/", label: "Início", icon: Home }, { to: "/consulta/nova", label: "Nova consulta", icon: UserPlus },
  { to: "/atualizar", label: "Atualizar prontuário", icon: ClipboardList }, { to: "/pacientes", label: "Pacientes", icon: Users },
  { to: "/laboratorio", label: "Laboratório PLN", icon: FlaskConical }, { to: "/configuracoes", label: "Configurações", icon: Settings },
];

export function GlobalSearch({ open, onOpenChange }: { open: boolean; onOpenChange: (b: boolean) => void }) {
  const nav = useNavigate();
  const [patients, setPatients] = useState<any[]>([]);
  useEffect(() => { if (open) api.get("/patients").then(setPatients).catch(() => {}); }, [open]);
  const go = (to: string) => { onOpenChange(false); nav(to); };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="top-[20%] max-w-xl translate-y-0 gap-0 p-0">
        <DialogTitle className="sr-only">Busca global</DialogTitle>
        <DialogDescription className="sr-only">Busque pacientes, queixas, padrões de MTC, pontos ou navegue entre telas.</DialogDescription>
        <Command className="overflow-hidden rounded-lg" filter={(value, search) => (value.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").includes(search.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")) ? 1 : 0)}>
          <Command.Input autoFocus placeholder="Buscar paciente, queixa, padrão MTC, ponto (VB20)…" className="w-full border-b bg-transparent px-4 py-3 text-sm outline-none" />
          <Command.List className="max-h-80 overflow-auto p-2">
            <Command.Empty className="p-6 text-center text-sm text-muted-foreground">Nada encontrado.</Command.Empty>
            <Command.Group heading="Pacientes" className="text-xs text-muted-foreground [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1">
              {patients.map((p) => (
                <Command.Item key={p.id} value={`${p.name} ${p.search_text}`} onSelect={() => go(`/pacientes/${p.id}`)} className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 text-sm text-foreground aria-selected:bg-secondary">
                  <User className="size-4 text-primary" /><span className="font-medium">{p.name}</span><span className="truncate text-xs text-muted-foreground">{p.main_complaint}</span>
                </Command.Item>))}
            </Command.Group>
            <Command.Group heading="Ir para" className="text-xs text-muted-foreground [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1">
              {PAGES.map((p) => (
                <Command.Item key={p.to} value={`ir ${p.label}`} onSelect={() => go(p.to)} className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 text-sm text-foreground aria-selected:bg-secondary">
                  <p.icon className="size-4 text-accent" />{p.label}
                </Command.Item>))}
            </Command.Group>
          </Command.List>
          <div className="flex justify-between border-t px-3 py-2 text-[11px] text-muted-foreground"><span>↑↓ navegar · Enter abrir</span><span><Kbd>Esc</Kbd> fechar</span></div>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
