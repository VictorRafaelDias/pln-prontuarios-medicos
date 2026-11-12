import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle, Check, FileDown, FlaskConical, Mic, Pause, Play, Save, Send, Trash2, Wand2, ArrowLeft, Pencil, Volume2, VolumeX } from "lucide-react";
import { api, Form, FieldState, Utt, Speaker } from "@/lib/api";
import { speechSupported, useSpeech } from "@/lib/speech";
import { assignVoices, estimateMs, speak, stopSpeaking, ttsSupported, useVoices, usePrefs, voiceGender } from "@/lib/tts";
import { cn, fmtClock, fmtDate, isEmpty } from "@/lib/utils";
import { useApp } from "@/App";
import { FormView } from "@/components/FormView";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Dialog, DialogContent, DialogDescription, DialogTitle, Input, Label, Popover, PopoverContent, PopoverTrigger, Progress, Select, Skeleton, Switch, Textarea } from "@/components/ui";

/* ------------------------------------------------------------------ Passo 1: dados básicos + LGPD */
function Step1() {
  const nav = useNavigate();
  const [d, setD] = useState({ name: "", birth_date: "", phone: "", email: "", profession: "", sex: "", consent_lgpd: false });
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: any) => setD((x) => ({ ...x, [k]: v }));
  const go = async () => {
    setBusy(true);
    try {
      const s = await api.post("/sessions", { kind: "anamnese", patient_data: d });
      localStorage.setItem("qi:lastDraft", String(s.id));
      nav(`/consulta/${s.id}`);
    } catch (e: any) { toast.error(e.message); setBusy(false); }
  };
  return (
    <div className="mx-auto max-w-2xl animate-fade-in space-y-6">
      <div><h1 className="text-3xl font-semibold">Nova consulta</h1><p className="text-muted-foreground">Passo 1 de 2 — dados básicos do paciente</p></div>
      <Card><CardContent className="grid gap-4 p-6 sm:grid-cols-2">
        <div className="space-y-1.5 sm:col-span-2"><Label>Nome completo *</Label><Input value={d.name} onChange={(e) => set("name", e.target.value)} autoFocus /></div>
        <div className="space-y-1.5"><Label>Nascimento</Label><Input type="date" value={d.birth_date} onChange={(e) => set("birth_date", e.target.value)} /></div>
        <div className="space-y-1.5"><Label>Telefone</Label><Input value={d.phone} onChange={(e) => set("phone", e.target.value)} placeholder="(11) 90000-0000" /></div>
        <div className="space-y-1.5"><Label>E-mail</Label><Input type="email" value={d.email} onChange={(e) => set("email", e.target.value)} /></div>
        <div className="space-y-1.5"><Label>Profissão</Label><Input value={d.profession} onChange={(e) => set("profession", e.target.value)} /></div>
        <div className="space-y-1.5"><Label>Sexo <span className="font-normal text-muted-foreground">(escolhe a voz do paciente na simulação)</span></Label>
          <Select className="w-full" value={d.sex} onChange={(e) => set("sex", e.target.value)}><option value="">Não informado</option><option value="F">Feminino</option><option value="M">Masculino</option><option value="O">Outro / prefere não informar</option></Select></div>
        <label className="flex cursor-pointer items-start gap-3 rounded-md border bg-secondary/50 p-3 text-sm sm:col-span-2">
          <input type="checkbox" className="mt-1 size-4 accent-[hsl(var(--primary))]" checked={d.consent_lgpd} onChange={(e) => set("consent_lgpd", e.target.checked)} />
          <span><b>Consentimento LGPD (obrigatório).</b> O paciente autoriza o tratamento de seus dados de saúde e a gravação/transcrição da consulta para fins de documentação clínica. A transcrição é processada localmente; o reconhecimento de voz do Chrome envia o áudio aos servidores do Google.</span>
        </label>
      </CardContent></Card>
      <div className="flex justify-end"><Button size="lg" disabled={!d.consent_lgpd || !d.name.trim() || busy} onClick={go}>Iniciar consulta →</Button></div>
    </div>
  );
}

/* ------------------------------------------------------------------ Passo 2/3 */
export default function Consulta() {
  const { id } = useParams();
  if (!id) return <Step1 />;
  return <Editor sid={Number(id)} key={id} />;
}

function Editor({ sid }: { sid: number }) {
  const nav = useNavigate();
  const { schema, status, points } = useApp();
  const [sess, setSess] = useState<any>(null);
  const [utts, setUtts] = useState<Utt[]>([]);
  const [form, setForm] = useState<Form>({});
  const [flash, setFlash] = useState<Record<string, number>>({});
  const [speaker, setSpeaker] = useState<Speaker>("paciente");
  const [interim, setInterim] = useState<{ speaker: Speaker; text: string } | null>(null);
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [view, setView] = useState<"edit" | "review">("edit");
  const [processing, setProcessing] = useState(false);
  const [demos, setDemos] = useState<any[]>([]);
  const [demoId, setDemoId] = useState("");
  const [simulating, setSimulating] = useState(false);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [paste, setPaste] = useState("");
  const [discardOpen, setDiscardOpen] = useState(false);
  const [pdata, setPdata] = useState<any>({});
  const [dataOpen, setDataOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const voices = useVoices();
  const [prefs, setPrefs] = usePrefs();
  const [voiceOn, setVoiceOn] = useState(() => localStorage.getItem("qi:voiceOn") !== "0");
  const toggleVoice = (on: boolean) => { setVoiceOn(on); localStorage.setItem("qi:voiceOn", on ? "1" : "0"); if (!on) stopSpeaking(); };
  const profSetting = status?.settings.professional_voice ?? "auto";
  // automática: o profissional recebe a voz OPOSTA à do paciente (assim as duas vozes são sempre distintas)
  const profGender = profSetting === "feminina" ? "f" : profSetting === "masculina" ? "m" : pdata.sex === "M" ? "f" : "m";
  const assigned = useMemo(() => assignVoices(voices, pdata.sex, profGender, prefs), [voices, pdata.sex, profGender, prefs]);

  const formRef = useRef(form); formRef.current = form;
  const uttsRef = useRef(utts); uttsRef.current = utts;
  const llmRef = useRef<any>(null);
  const reqRef = useRef(0);
  const dirty = useRef(false);
  const speakerRef = useRef(speaker); speakerRef.current = speaker;
  const elapsedRef = useRef(0); elapsedRef.current = elapsed;
  const simAbort = useRef(false);
  const mode: string = sess?.kind ?? "anamnese";

  // --- carga inicial
  useEffect(() => {
    api.get(`/sessions/${sid}`).then((s) => {
      setSess(s); setUtts(s.transcript ?? []); setForm(s.form ?? {}); setPdata(s.patient_data ?? {}); setElapsed(s.duration_s ?? 0);
      localStorage.setItem("qi:lastDraft", String(sid));
    }).catch((e) => { toast.error(e.message); nav("/"); });
    api.get("/demo/transcripts").then(setDemos).catch(() => {});
  }, [sid, nav]);
  useEffect(() => { const d = demos.filter((x) => x.mode === mode); if (d.length && !d.find((x) => x.id === demoId)) setDemoId(d[0].id); }, [demos, mode, demoId]);

  // --- pipeline de PLN (debounce) ---------------------------------------------------------
  const runNlp = useCallback(async (useLlm: boolean) => {
    const list = uttsRef.current;
    if (!list.length || !sess) return;
    const my = ++reqRef.current;
    setProcessing(true);
    try {
      const confirmed: Record<string, any> = {};
      Object.entries(formRef.current).forEach(([k, f]) => { if (f.confirmed) confirmed[k] = f.value; });
      const res = await api.post("/nlp/process", { utterances: list, mode, confirmed, llm_fields: llmRef.current, use_llm: useLlm, previous_session: sess.previous ? { eva: sess.previous.eva, summary: sess.previous.summary } : null });
      if (my !== reqRef.current) return;
      if (res.llm_fields) llmRef.current = res.llm_fields;
      if (res.llm?.error) toast.warning(`LLM indisponível (${res.llm.error}). Continuando só com o PLN clássico.`, { id: "llm-err" });
      const stamp = Date.now();
      const changed: Record<string, number> = {};
      setForm((prev) => {
        const next: Form = {};
        for (const [k, f] of Object.entries(prev)) if (f.confirmed) next[k] = f;
        for (const [k, f] of Object.entries<any>(res.fields)) {
          if (next[k]) continue;
          next[k] = { ...f, confirmed: false };
          if (JSON.stringify(prev[k]?.value) !== JSON.stringify(f.value)) changed[k] = stamp;
        }
        return next;
      });
      if (Object.keys(changed).length) setFlash((x) => ({ ...x, ...changed }));
      dirty.current = true;
    } catch (e: any) { toast.error("Falha no processamento: " + e.message); }
    finally { if (my === reqRef.current) setProcessing(false); }
  }, [mode, sess]);

  useEffect(() => {
    if (!sess || !utts.length) return;
    dirty.current = true;
    const t = setTimeout(() => runNlp(false), 600);
    let t2: any;
    if (status?.llm_enabled) t2 = setTimeout(() => runNlp(true), 5000);
    return () => { clearTimeout(t); clearTimeout(t2); };
  }, [utts, sess, runNlp, status?.llm_enabled]);

  // --- autosave do rascunho a cada 10 s ---------------------------------------------------
  const flush = useCallback(async () => {
    await api.put(`/sessions/${sid}/draft`, { form: formRef.current, transcript: uttsRef.current, patient_data: pdata, duration_s: Math.round(elapsedRef.current) });
    dirty.current = false;
  }, [sid, pdata]);
  useEffect(() => {
    if (!sess) return;
    const t = setInterval(() => { if (dirty.current) flush().catch(() => {}); }, 10000);
    return () => clearInterval(t);
  }, [sess, flush]);

  // --- cronômetro --------------------------------------------------------------------------
  useEffect(() => { if (!recording && !simulating) return; const t = setInterval(() => setElapsed((e) => e + 1), 1000); return () => clearInterval(t); }, [recording, simulating]);

  // --- fala --------------------------------------------------------------------------------
  const addUtt = useCallback((text: string, sp?: Speaker) => {
    if (!text.trim()) return;
    setUtts((u) => [...u, { speaker: sp ?? speakerRef.current, text: text.trim(), ts: elapsedRef.current }]);
  }, []);
  const speech = useSpeech({
    lang: status?.settings.speech_lang || "pt-BR",
    onFinal: (t) => { addUtt(t); },
    onInterim: (t) => setInterim(t ? { speaker: speakerRef.current, text: t } : null),
    onError: (m) => { toast.error(m); setRecording(false); },
  });
  const toggleRec = useCallback(() => {
    if (recording) { speech.stop(); setRecording(false); return; }
    if (!speechSupported) { toast.warning("Este navegador não suporta reconhecimento de voz. Use o Chrome, ou digite/cole a transcrição."); setPasteOpen(true); return; }
    if (speech.start()) setRecording(true);
  }, [recording, speech]);

  const simulate = async () => {
    const demo = demos.find((d) => d.id === demoId);
    if (!demo) return;
    if (simulating) { simAbort.current = true; stopSpeaking(); return; }
    simAbort.current = false;
    setSimulating(true);
    for (const u of demo.utterances as { speaker: Speaker; text: string }[]) {
      if (simAbort.current) break;
      const words = u.text.split(" ");
      if (voiceOn && ttsSupported && voices.length) {
        // fala com a voz do papel (paciente × profissional) e "digita" as palavras em sincronia
        const who = u.speaker === "profissional" ? assigned.professional : assigned.patient;
        const step = estimateMs(u.text, prefs.rate) / words.length;
        let shown = 0;
        setInterim({ speaker: u.speaker, text: words[0] });
        const timer = setInterval(() => { shown = Math.min(words.length, shown + 1); setInterim({ speaker: u.speaker, text: words.slice(0, Math.max(1, shown)).join(" ") }); }, step);
        await speak(u.text, who, prefs.rate);
        clearInterval(timer);
      } else {
        for (let i = 1; i <= words.length; i++) {
          if (simAbort.current) break;
          setInterim({ speaker: u.speaker, text: words.slice(0, i).join(" ") });
          await new Promise((r) => setTimeout(r, 70));
        }
      }
      setInterim(null);
      if (simAbort.current) break;
      addUtt(u.text, u.speaker);
      await new Promise((r) => setTimeout(r, 650));
    }
    setSimulating(false);
    setInterim(null);
  };

  // --- atalhos: Espaço = gravar/pausar (fora de campos), Ctrl+S = salvar rascunho/ir à revisão ---------
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      const inField = ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) || el.isContentEditable;
      if (e.code === "Space" && !inField && view === "edit") { e.preventDefault(); toggleRec(); }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); if (view === "review") save(); else flush().then(() => toast.success("Rascunho salvo")).catch((err) => toast.error(err.message)); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  });

  // --- edição de campos -----------------------------------------------------------------------
  const onSet = (fid: string, v: any) => setForm((f) => { dirty.current = true; return isEmpty(v) && v !== false && v !== 0 ? Object.fromEntries(Object.entries(f).filter(([k]) => k !== fid)) : { ...f, [fid]: { value: v, source: "manual", confidence: 1, confirmed: true } as FieldState }; });
  const onConfirm = (fid: string) => setForm((f) => ({ ...f, [fid]: { ...f[fid], confirmed: true } }));
  const onClear = (fid: string) => setForm((f) => { dirty.current = true; return Object.fromEntries(Object.entries(f).filter(([k]) => k !== fid)); });
  const confirmAll = () => setForm((f) => Object.fromEntries(Object.entries(f).map(([k, v]) => [k, { ...v, confirmed: true }])));

  // --- derivados ----------------------------------------------------------------------------------
  const fields = useMemo(() => (schema?.fields ?? []).filter((f) => schema!.sections.find((s) => s.id === f.section)?.modes.includes(mode) && f.type !== "computed"), [schema, mode]);
  const filled = fields.filter((f) => !isEmpty(form[f.id]?.value));
  const progress = fields.length ? Math.round((filled.length / fields.length) * 100) : 0;
  const alerts = (schema?.fields ?? []).filter((f) => f.id.startsWith("contra.") && form[f.id]?.value === true).map((f) => f.alert!);
  const unconfirmed = Object.entries(form).filter(([k, f]) => !f.confirmed && f.source !== "calc" && !isEmpty(f.value));
  const missingRequired = fields.filter((f) => f.required && isEmpty(form[f.id]?.value));

  const save = async () => {
    if (!pdata.name?.trim()) { toast.error("Informe o nome do paciente."); setDataOpen(true); return; }
    if (!pdata.consent_lgpd && !sess?.patient_id) { toast.error("Consentimento LGPD é obrigatório."); setDataOpen(true); return; }
    setSaving(true);
    try {
      const r = await api.post(`/sessions/${sid}/save`, { form, transcript: utts, patient_data: pdata, duration_s: Math.round(elapsed) });
      localStorage.removeItem("qi:lastDraft");
      toast.success("Sessão salva no prontuário");
      nav(`/pacientes/${r.patient_id}`);
    } catch (e: any) { toast.error(e.message); setSaving(false); }
  };
  const exportPdf = async () => { await flush(); window.open(`/api/sessions/${sid}/pdf`, "_blank"); };
  const discard = async () => { await api.del(`/sessions/${sid}`); localStorage.removeItem("qi:lastDraft"); toast.success("Rascunho descartado"); nav("/"); };

  if (!sess || !schema) return <div className="space-y-4"><Skeleton className="h-10 w-72" /><Skeleton className="h-[60vh]" /></div>;
  const patientAlerts: string[] = sess.patient_alerts ?? [];

  /* ------------------------------------------------------------------ Revisão */
  if (view === "review") {
    return (
      <div className="mx-auto max-w-4xl animate-fade-in space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><h1 className="text-3xl font-semibold">Revisar e finalizar</h1><p className="text-muted-foreground">{pdata.name || "Paciente sem nome"} · {mode === "soap" ? "Sessão SOAP" : "Anamnese"}</p></div>
          <Button variant="ghost" onClick={() => setView("edit")}><ArrowLeft /> Voltar e editar</Button>
        </div>
        {alerts.length > 0 && <div className="flex items-center gap-3 rounded-lg border-2 border-accent bg-accent/10 p-3 font-medium text-accent"><AlertTriangle /> CONTRAINDICAÇÕES: {alerts.join(" · ")}</div>}
        {missingRequired.length > 0 && <Card className="border-destructive/60"><CardHeader><CardTitle className="text-destructive">Campos obrigatórios vazios</CardTitle></CardHeader><CardContent className="flex flex-wrap gap-2">{missingRequired.map((f) => <Badge key={f.id} variant="destructive">{f.label}</Badge>)}</CardContent></Card>}
        <Card className={unconfirmed.length ? "border-amber-500/60" : ""}>
          <CardHeader className="flex-row items-center justify-between"><CardTitle>{unconfirmed.length ? `${unconfirmed.length} campos automáticos ainda não confirmados` : "Todos os campos confirmados"}</CardTitle>{unconfirmed.length > 0 && <Button size="sm" onClick={confirmAll}><Check /> Confirmar todos</Button>}</CardHeader>
          <CardContent className="space-y-1">
            {unconfirmed.map(([k, f]) => { const def = schema.fields.find((x) => x.id === k); return (
              <div key={k} className="flex items-center justify-between gap-3 rounded-md bg-amber-500/10 px-3 py-1.5 text-sm"><span><b>{def?.label}</b>: {Array.isArray(f.value) ? f.value.join(", ") : String(f.value)}</span><Badge variant="warn">sugestão · {Math.round(f.confidence * 100)}%</Badge></div>); })}
          </CardContent>
        </Card>
        {(!pdata.name?.trim() || (!pdata.consent_lgpd && !sess.patient_id)) && (
          <Card className="border-destructive/60"><CardContent className="space-y-3 p-5">
            <p className="text-sm font-medium text-destructive">Para salvar é necessário nome e consentimento LGPD.</p>
            <Input placeholder="Nome do paciente" value={pdata.name ?? ""} onChange={(e) => setPdata({ ...pdata, name: e.target.value })} />
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!pdata.consent_lgpd} onChange={(e) => setPdata({ ...pdata, consent_lgpd: e.target.checked })} /> Paciente consentiu (LGPD) o tratamento de dados de saúde e da transcrição</label>
          </CardContent></Card>
        )}
        <div className="flex flex-wrap justify-between gap-3">
          <Button variant="outline" className="text-destructive" onClick={() => setDiscardOpen(true)}><Trash2 /> Descartar</Button>
          <div className="flex gap-2"><Button variant="outline" onClick={exportPdf}><FileDown /> Exportar PDF</Button><Button size="lg" onClick={save} disabled={saving}><Save /> Salvar no prontuário</Button></div>
        </div>
        <DiscardDialog open={discardOpen} onOpenChange={setDiscardOpen} onConfirm={discard} />
      </div>
    );
  }

  /* ------------------------------------------------------------------ Passo 2: tela dividida */
  const live = recording || simulating;
  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{pdata.name || "Consulta"} <Badge variant="outline">{mode === "soap" ? "Sessão SOAP" : "Anamnese"}</Badge></h1>
          <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground"><span>{filled.length} de {fields.length} campos</span><Progress value={progress} className="w-40" /><span>{progress}%</span>{processing && <span className="animate-pulse">analisando…</span>}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" size="sm" onClick={() => setDataOpen(true)}><Pencil /> Dados do paciente</Button>
          <Button variant="outline" size="sm" onClick={() => { flush(); nav("/laboratorio?draft=" + sid); }}><FlaskConical /> Ver no Laboratório PLN</Button>
          <Button onClick={() => { flush(); setView("review"); }}><Send /> Revisar e finalizar</Button>
        </div>
      </div>
      {(alerts.length > 0 || patientAlerts.length > 0) && <div className="flex items-center gap-3 rounded-lg border-2 border-accent bg-accent/10 p-3 font-medium text-accent"><AlertTriangle /> ALERTA — Contraindicações: {[...new Set([...alerts, ...patientAlerts])].join(" · ")}</div>}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* ----- esquerda: transcrição ao vivo */}
        <Card className="flex h-fit flex-col lg:sticky lg:top-4 lg:max-h-[calc(100vh-7rem)]">
          <CardHeader className="gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button variant={recording ? "destructive" : "default"} onClick={toggleRec} disabled={simulating}>{recording ? <><Pause /> Pausar</> : <><Mic /> Gravar</>}</Button>
              <span className={cn("size-3 rounded-full", live ? "rec-dot bg-destructive" : "bg-muted-foreground/40")} aria-label={live ? "gravando" : "parado"} />
              <span className="font-mono text-lg tabular-nums">{fmtClock(elapsed)}</span>
              <div className="ml-auto flex items-center gap-1 rounded-full border bg-muted p-0.5 text-xs">
                <span className="px-2 text-muted-foreground">Falando:</span>
                {(["profissional", "paciente"] as Speaker[]).map((s) => <button key={s} onClick={() => setSpeaker(s)} className={cn("rounded-full px-3 py-1 capitalize", speaker === s && "bg-primary text-primary-foreground")}>{s}</button>)}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Select value={demoId} onChange={(e) => setDemoId(e.target.value)} className="h-8 max-w-[15rem] text-xs" disabled={simulating}>{demos.filter((d) => d.mode === mode).map((d) => <option key={d.id} value={d.id}>{d.id} — {d.title}</option>)}</Select>
              <Button size="sm" variant="accent" onClick={simulate}>{simulating ? <><Pause /> Parar</> : <><Wand2 /> Simular consulta</>}</Button>
              {ttsSupported && (
                <Popover>
                  <PopoverTrigger asChild><Button size="sm" variant={voiceOn ? "outline" : "ghost"} title="Vozes da simulação" aria-label="Vozes da simulação">{voiceOn ? <Volume2 /> : <VolumeX />} Voz</Button></PopoverTrigger>
                  <PopoverContent className="w-80 space-y-3" align="start">
                    <label className="flex items-center justify-between text-sm font-medium">Falar a simulação em voz alta<Switch checked={voiceOn} onCheckedChange={toggleVoice} /></label>
                    {voices.length === 0 ? <p className="text-xs text-muted-foreground">Nenhuma voz em português encontrada neste navegador/sistema. A simulação continua só com texto.</p> : (
                      <>
                        {([["patient", `Paciente (${pdata.sex === "F" ? "feminino" : pdata.sex === "M" ? "masculino" : "não informado"})`, assigned.patient], ["professional", `Profissional (${profGender === "f" ? "feminina" : "masculina"}${profSetting === "auto" ? ", automática" : ""})`, assigned.professional]] as const).map(([k, label, a]) => (
                          <div key={k} className="space-y-1"><div className="flex items-center justify-between"><Label className="text-xs">{label}</Label>
                            <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px]" onClick={() => { stopSpeaking(); speak(k === "patient" ? "Bom dia, doutora. Estou com dor lombar há três meses." : "Bom dia. Conte-me o que está sentindo.", a, prefs.rate); }}>Testar</Button></div>
                            <Select className="h-8 w-full text-xs" value={a.voice?.voiceURI ?? ""} onChange={(e) => setPrefs({ [k]: e.target.value })}>
                              {voices.map((v) => <option key={v.voiceURI} value={v.voiceURI}>{v.name} ({voiceGender(v) === "f" ? "fem." : voiceGender(v) === "m" ? "masc." : "?"})</option>)}</Select></div>))}
                        <div className="space-y-1"><Label className="text-xs">Velocidade: {prefs.rate.toFixed(1)}×</Label>
                          <input type="range" min={0.7} max={1.4} step={0.1} value={prefs.rate} onChange={(e) => setPrefs({ rate: Number(e.target.value) })} className="w-full accent-[hsl(var(--primary))]" /></div>
                        <p className="text-[11px] text-muted-foreground">A voz do paciente segue o sexo cadastrado; a do profissional vem de Configurações. Usa as vozes instaladas no seu sistema (nada é enviado pela internet).</p>
                      </>)}
                  </PopoverContent>
                </Popover>)}
              <Button size="sm" variant="ghost" onClick={() => setPasteOpen(!pasteOpen)}>Digitar / colar</Button>
              {!speechSupported && <Badge variant="warn">Sem reconhecimento de voz neste navegador</Badge>}
            </div>
            {pasteOpen && (
              <div className="space-y-2 rounded-md border bg-secondary/40 p-3">
                <Textarea rows={4} value={paste} onChange={(e) => setPaste(e.target.value)} placeholder={'Uma fala por linha. Prefixos opcionais: "Profissional:" / "Paciente:". Sem prefixo usa o falante selecionado.'} />
                <Button size="sm" onClick={() => {
                  paste.split("\n").filter((l) => l.trim()).forEach((l) => { const m = l.match(/^\s*(profissional|prof|paciente|p|a)\s*:\s*(.*)$/i); addUtt(m ? m[2] : l, m ? (/^(profissional|prof|p)$/i.test(m[1]) && !/^paciente$/i.test(m[1]) ? "profissional" : "paciente") : undefined); });
                  setPaste(""); setPasteOpen(false);
                }}>Adicionar à transcrição</Button>
              </div>
            )}
          </CardHeader>
          <CardContent className="min-h-[18rem] flex-1 space-y-2 overflow-y-auto" aria-live="polite">
            {utts.length === 0 && !interim && <p className="py-10 text-center text-sm text-muted-foreground">Clique em <b>Gravar</b> (Chrome) ou use <b>Simular consulta</b> para ver o formulário se preencher sozinho.<br /><span className="text-xs">Atalho: Espaço grava/pausa.</span></p>}
            {utts.map((u, i) => (
              <div key={i} className={cn("group flex gap-2 animate-fade-in", u.speaker === "profissional" ? "" : "flex-row-reverse")}>
                <div className={cn("max-w-[85%] rounded-2xl px-3 py-2 text-sm", u.speaker === "profissional" ? "rounded-tl-sm bg-secondary" : "rounded-tr-sm bg-primary/15")}>
                  <div className="mb-0.5 flex items-center gap-2 text-[10px] uppercase tracking-wide text-muted-foreground"><span>{u.speaker}</span><span className="font-mono">{fmtClock(u.ts)}</span>
                    <button className="opacity-0 transition-opacity group-hover:opacity-100" title="trocar falante" onClick={() => setUtts((l) => l.map((x, j) => j === i ? { ...x, speaker: x.speaker === "paciente" ? "profissional" : "paciente" } : x))}>⇄</button>
                    <button className="opacity-0 transition-opacity group-hover:opacity-100" title="remover" onClick={() => setUtts((l) => l.filter((_, j) => j !== i))}>✕</button></div>
                  <span contentEditable suppressContentEditableWarning onBlur={(e) => { const t = e.currentTarget.textContent ?? ""; if (t !== u.text) setUtts((l) => l.map((x, j) => j === i ? { ...x, text: t } : x)); }}>{u.text}</span>
                </div>
              </div>
            ))}
            {interim && <div className={cn("flex", interim.speaker === "profissional" ? "" : "justify-end")}><div className="max-w-[85%] rounded-2xl bg-muted px-3 py-2 text-sm italic text-muted-foreground">{interim.text}…</div></div>}
          </CardContent>
        </Card>

        {/* ----- direita: formulário */}
        <div className="space-y-3">
          {sess.previous && (
            <Card className="border-primary/40 bg-primary/5"><CardContent className="p-4 text-sm">
              <div className="mb-1 font-serif font-semibold">Última sessão — {fmtDate(sess.previous.date)} ({sess.previous.kind === "soap" ? "SOAP" : "Anamnese"})</div>
              <p className="text-muted-foreground">{sess.previous.summary || "—"}</p>
              {sess.previous.eva != null && <Badge className="mt-2" variant="accent">EVA anterior: {sess.previous.eva}</Badge>}
            </CardContent></Card>
          )}
          <FormView schema={schema} mode={mode} form={form} flash={flash} catalog={points} onSet={onSet} onConfirm={onConfirm} onClear={onClear} />
        </div>
      </div>

      <Dialog open={dataOpen} onOpenChange={setDataOpen}>
        <DialogContent>
          <DialogTitle>Dados do paciente</DialogTitle><DialogDescription>Necessários para salvar. O consentimento LGPD é obrigatório.</DialogDescription>
          <div className="grid gap-3">
            {[["name", "Nome"], ["birth_date", "Nascimento"], ["phone", "Telefone"], ["email", "E-mail"], ["profession", "Profissão"]].map(([k, l]) => (
              <div key={k} className="space-y-1"><Label>{l}</Label><Input type={k === "birth_date" ? "date" : "text"} value={pdata[k] ?? ""} disabled={!!sess.patient_id} onChange={(e) => setPdata({ ...pdata, [k]: e.target.value })} /></div>))}
            <div className="space-y-1"><Label>Sexo (voz do paciente na simulação)</Label><Select className="w-full" value={pdata.sex ?? ""} disabled={!!sess.patient_id} onChange={(e) => setPdata({ ...pdata, sex: e.target.value })}><option value="">Não informado</option><option value="F">Feminino</option><option value="M">Masculino</option><option value="O">Outro / prefere não informar</option></Select></div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!pdata.consent_lgpd} disabled={!!sess.patient_id} onChange={(e) => setPdata({ ...pdata, consent_lgpd: e.target.checked })} /> Consentimento LGPD</label>
          </div>
          <Button onClick={() => { setDataOpen(false); dirty.current = true; }}>Concluir</Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function DiscardDialog({ open, onOpenChange, onConfirm }: { open: boolean; onOpenChange: (b: boolean) => void; onConfirm: () => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent><DialogTitle>Descartar este rascunho?</DialogTitle><DialogDescription>A transcrição e o preenchimento desta consulta serão apagados. Esta ação não pode ser desfeita.</DialogDescription>
        <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => onOpenChange(false)}>Cancelar</Button><Button variant="destructive" onClick={onConfirm}>Descartar</Button></div>
      </DialogContent>
    </Dialog>
  );
}
