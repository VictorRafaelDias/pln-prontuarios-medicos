import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Download, KeyRound, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { useApp } from "@/App";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Label, Select } from "@/components/ui";

export default function Config() {
  const { status, reloadStatus } = useApp();
  const [s, setS] = useState<any>({});
  const file = useRef<HTMLInputElement>(null);
  useEffect(() => { if (status) setS(status.settings); }, [status]);
  const save = async () => { await api.put("/settings", s); reloadStatus(); toast.success("Configurações salvas"); };
  const restore = async (f: File) => {
    try { const r = await api.post("/restore", JSON.parse(await f.text())); toast.success(`Backup restaurado (${r.patients} pacientes)`); reloadStatus(); } catch (e: any) { toast.error("Backup inválido: " + e.message); }
  };
  return (
    <div className="mx-auto max-w-3xl animate-fade-in space-y-5">
      <h1 className="text-3xl font-semibold">Configurações</h1>
      <Card><CardHeader><CardTitle className="flex items-center gap-2"><KeyRound className="size-5 text-primary" />LLM (Anthropic)</CardTitle></CardHeader><CardContent className="space-y-2 text-sm">
        <div className="flex items-center gap-2">Status: {status?.llm_enabled ? <Badge variant="solid">Chave configurada</Badge> : <Badge variant="muted">Sem chave — Somente PLN clássico</Badge>}</div>
        {status?.llm_enabled && <div>Modelo: <code className="rounded bg-muted px-1.5">{status.model}</code> · esforço: <code className="rounded bg-muted px-1.5">{status.effort}</code></div>}
        <p className="text-muted-foreground">A chave fica apenas no backend (arquivo <code>.env</code>, variáveis <code>ANTHROPIC_API_KEY</code> e <code>ANTHROPIC_MODEL</code>). Ela nunca é enviada ao navegador. Reinicie a API após editar o <code>.env</code>.</p>
        <p className="text-muted-foreground">spaCy: <code>{status?.spacy.model} {status?.spacy.version}</code> · {status?.spacy.ruler_patterns} padrões no EntityRuler</p>
      </CardContent></Card>
      <Card><CardHeader><CardTitle>Clínica e reconhecimento de voz</CardTitle></CardHeader><CardContent className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5"><Label>Nome da clínica</Label><Input value={s.clinic_name ?? ""} onChange={(e) => setS({ ...s, clinic_name: e.target.value })} /></div>
        <div className="space-y-1.5"><Label>Nome do profissional</Label><Input value={s.professional_name ?? ""} onChange={(e) => setS({ ...s, professional_name: e.target.value })} /></div>
        <div className="space-y-1.5"><Label>Endereço</Label><Input value={s.clinic_address ?? ""} onChange={(e) => setS({ ...s, clinic_address: e.target.value })} /></div>
        <div className="space-y-1.5"><Label>Telefone da clínica</Label><Input value={s.clinic_phone ?? ""} onChange={(e) => setS({ ...s, clinic_phone: e.target.value })} /></div>
        <div className="space-y-1.5"><Label>Idioma do reconhecimento</Label><Select className="w-full" value={s.speech_lang ?? "pt-BR"} onChange={(e) => setS({ ...s, speech_lang: e.target.value })}><option value="pt-BR">Português (Brasil)</option><option value="pt-PT">Português (Portugal)</option><option value="en-US">English (US)</option><option value="es-ES">Español</option></Select></div>
        <div className="flex items-end"><Button onClick={save}>Salvar</Button></div>
      </CardContent></Card>
      <Card><CardHeader><CardTitle>Backup e restauração</CardTitle></CardHeader><CardContent className="flex flex-wrap gap-3">
        <Button variant="outline" onClick={() => window.open("/api/backup")}><Download /> Baixar backup (JSON)</Button>
        <Button variant="outline" onClick={() => file.current?.click()}><Upload /> Restaurar de JSON</Button>
        <input ref={file} type="file" accept="application/json" hidden onChange={(e) => e.target.files?.[0] && restore(e.target.files[0])} />
        <p className="w-full text-xs text-muted-foreground">Restaurar substitui todos os dados atuais. Dados de saúde são sensíveis (LGPD): guarde o arquivo em local seguro.</p>
      </CardContent></Card>
    </div>
  );
}
