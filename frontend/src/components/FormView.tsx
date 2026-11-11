import { useMemo, useState } from "react";
import { AlertTriangle, Check, CircleHelp, X } from "lucide-react";
import { FieldDef, FieldState, Form, Schema, sourceLabel } from "@/lib/api";
import { cn, fold, isEmpty } from "@/lib/utils";
import { Badge, Button, EvaSlider, Input, Section, Textarea, Tip } from "@/components/ui";

const SRC_VARIANT: Record<string, any> = { rules: "default", llm: "accent", both: "solid", manual: "outline", calc: "muted" };

function Chips({ options, value, labels, onToggle }: { options: string[]; value: string[]; labels?: Record<string, string>; onToggle: (o: string) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button key={o} type="button" onClick={() => onToggle(o)} className={cn("rounded-full border px-3 py-1 text-xs transition-colors", value.includes(o) ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-secondary")}>
          {labels?.[o] ?? o}
        </button>
      ))}
    </div>
  );
}

function ListInput({ value, onChange, placeholder }: { value: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [t, setT] = useState("");
  const add = () => { const s = t.trim(); if (s && !value.includes(s)) onChange([...value, s]); setT(""); };
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {value.map((v) => <Badge key={v} variant="default" className="gap-1 py-1 text-xs">{v}<button onClick={() => onChange(value.filter((x) => x !== v))} aria-label="remover"><X className="size-3" /></button></Badge>)}
      </div>
      <Input value={t} placeholder={placeholder ?? "Adicionar e pressionar Enter"} onChange={(e) => setT(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} onBlur={add} />
    </div>
  );
}

function PointsInput({ value, onChange, catalog }: { value: string[]; onChange: (v: string[]) => void; catalog: { code: string; nome: string; meridiano: string }[] }) {
  const [q, setQ] = useState("");
  const hits = useMemo(() => {
    const f = fold(q);
    return f ? catalog.filter((p) => fold(p.code).startsWith(f) || fold(p.nome).includes(f) || fold(p.meridiano).includes(f)).slice(0, 8) : [];
  }, [q, catalog]);
  const add = (c: string) => { c = c.toUpperCase().replace(/\s|-/g, ""); if (c && !value.includes(c)) onChange([...value, c]); setQ(""); };
  const name = (c: string) => catalog.find((p) => p.code === c);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {value.map((v) => (
          <Tip key={v} content={name(v) ? `${name(v)!.nome} — ${name(v)!.meridiano}` : "ponto"}>
            <Badge variant="solid" className="gap-1 py-1 font-mono text-xs">{v}<button onClick={() => onChange(value.filter((x) => x !== v))} aria-label="remover"><X className="size-3" /></button></Badge>
          </Tip>
        ))}
      </div>
      <div className="relative">
        <Input value={q} placeholder="Buscar ponto: VB20, Zusanli, Fígado…" onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(hits[0]?.code ?? q); } }} />
        {hits.length > 0 && (
          <ul className="absolute z-20 mt-1 w-full overflow-hidden rounded-md border bg-card shadow-soft">
            {hits.map((p) => <li key={p.code}><button type="button" className="flex w-full justify-between px-3 py-1.5 text-left text-sm hover:bg-secondary" onClick={() => add(p.code)}><span><b className="font-mono">{p.code}</b> {p.nome}</span><span className="text-xs text-muted-foreground">{p.meridiano}</span></button></li>)}
          </ul>
        )}
      </div>
    </div>
  );
}

function Control({ f, v, set, schema, catalog }: { f: FieldDef; v: any; set: (v: any) => void; schema: Schema; catalog: any[] }) {
  switch (f.type) {
    case "textarea": return <Textarea value={v ?? ""} onChange={(e) => set(e.target.value)} rows={3} />;
    case "text": return <Input value={v ?? ""} onChange={(e) => set(e.target.value)} />;
    case "number": return <div className="flex items-center gap-2"><Input type="number" className="w-28" value={v ?? ""} onChange={(e) => set(e.target.value === "" ? null : Number(e.target.value))} />{f.unit && <span className="text-xs text-muted-foreground">{f.unit}</span>}</div>;
    case "computed": return <div className="rounded-md bg-muted px-3 py-2 text-sm">{v ?? "—"} {f.unit}</div>;
    case "scale": return (
      <div className="flex items-center gap-3">
        <div className="flex-1"><EvaSlider value={v ?? null} onChange={set} /></div>
        <span className="w-10 text-center font-serif text-xl font-semibold">{v ?? "—"}</span>
      </div>);
    case "select": return <Chips options={f.options!} value={v ? [v] : []} onToggle={(o) => set(v === o ? null : o)} />;
    case "multiselect": return <Chips options={f.options!} labels={f.option_labels} value={v ?? []} onToggle={(o) => { const a: string[] = v ?? []; set(a.includes(o) ? a.filter((x) => x !== o) : [...a, o]); }} />;
    case "bool": return (
      <div className="flex gap-1.5">
        {[["Sim", true], ["Não", false]].map(([l, b]) => (
          <button key={String(l)} type="button" onClick={() => set(v === b ? null : b)} className={cn("rounded-full border px-4 py-1 text-xs", v === b ? (b ? "border-destructive bg-destructive text-destructive-foreground" : "border-primary bg-primary text-primary-foreground") : "bg-card hover:bg-secondary")}>{l as string}</button>
        ))}
      </div>);
    case "list": return <ListInput value={v ?? []} onChange={set} />;
    case "points": return <PointsInput value={v ?? []} onChange={set} catalog={catalog} />;
    case "bodymap": return (
      <div className="space-y-2">
        <Chips options={Object.keys(schema.regions)} labels={schema.regions} value={v ?? []} onToggle={(o) => { const a: string[] = v ?? []; set(a.includes(o) ? a.filter((x) => x !== o) : [...a, o]); }} />
      </div>);
  }
  return null;
}

export function FieldRow({ f, st, onSet, onConfirm, onClear, schema, catalog, flash }: { f: FieldDef; st?: FieldState; onSet: (v: any) => void; onConfirm: () => void; onClear: () => void; schema: Schema; catalog: any[]; flash?: number }) {
  const auto = st && st.source !== "manual" && st.source !== "calc" && !st.confirmed;
  const filled = st && !isEmpty(st.value);
  return (
    <div key={flash} className={cn("rounded-md p-2 transition-colors", auto && "field-auto", st?.conflict && "field-conflict", flash && "field-flash")}>
      <div className="mb-1.5 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{f.label}{f.required && <span className="text-accent"> *</span>}</span>
        {f.hint && <Tip content={f.hint}><CircleHelp className="size-3.5 text-muted-foreground" /></Tip>}
        {filled && st && (
          <Tip content={<div className="space-y-1"><div><b>{sourceLabel[st.source]}</b> · confiança {Math.round(st.confidence * 100)}%</div>{st.evidence && <div className="italic">“{st.evidence}”</div>}{st.rule && <div className="font-mono text-[10px] opacity-70">{st.rule}</div>}{st.note && <div>{st.note}</div>}{st.alternatives?.map((a, i) => <div key={i} className="text-accent">divergência ({a.source ?? "alt"}): {JSON.stringify(a.value)}</div>)}</div>}>
            <span className="flex items-center gap-1">
              <Badge variant={SRC_VARIANT[st.source]}>{sourceLabel[st.source]}{st.source !== "manual" && ` ${Math.round(st.confidence * 100)}%`}</Badge>
              {st.conflict && <AlertTriangle className="size-3.5 text-accent" />}
            </span>
          </Tip>
        )}
        <span className="ml-auto flex gap-1">
          {auto && <Button size="sm" variant="ghost" className="h-6 gap-1 px-2 text-[11px]" onClick={onConfirm}><Check className="size-3" />confirmar</Button>}
          {filled && f.type !== "computed" && <Button size="icon" variant="ghost" className="size-6" onClick={onClear} aria-label="limpar"><X className="size-3" /></Button>}
        </span>
      </div>
      <Control f={f} v={st?.value} set={onSet} schema={schema} catalog={catalog} />
    </div>
  );
}

export function FormView({ schema, mode, form, onSet, onConfirm, onClear, flash, catalog }: { schema: Schema; mode: string; form: Form; onSet: (id: string, v: any) => void; onConfirm: (id: string) => void; onClear: (id: string) => void; flash: Record<string, number>; catalog: any[] }) {
  const sections = schema.sections.filter((s) => s.modes.includes(mode));
  return (
    <div className="space-y-3">
      {sections.map((s) => {
        const fields = schema.fields.filter((f) => f.section === s.id);
        const n = fields.filter((f) => f.type !== "computed" && !isEmpty(form[f.id]?.value)).length;
        return (
          <Section key={s.id} title={s.title} defaultOpen={["queixa", "soap_s", "soap_p", "contra"].includes(s.id)} badge={n > 0 && <Badge variant="default">{n}/{fields.filter((f) => f.type !== "computed").length}</Badge>}>
            {fields.map((f) => <FieldRow key={f.id} f={f} st={form[f.id]} schema={schema} catalog={catalog} flash={flash[f.id]} onSet={(v) => onSet(f.id, v)} onConfirm={() => onConfirm(f.id)} onClear={() => onClear(f.id)} />)}
          </Section>
        );
      })}
    </div>
  );
}
