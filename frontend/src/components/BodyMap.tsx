import { cn } from "@/lib/utils";

type Shape = { id: string; t: "e" | "r"; a: number[] };
// Elipse: [cx, cy, rx, ry] · Retângulo: [x, y, largura, altura, raio]. Vista frontal: direita do paciente fica à esquerda da tela.
const FRONT: Shape[] = [
  { id: "cabeca", t: "e", a: [100, 30, 22, 26] }, { id: "pescoco", t: "r", a: [90, 54, 20, 16, 5] },
  { id: "torax", t: "r", a: [70, 74, 60, 52, 10] }, { id: "abdomen", t: "r", a: [72, 128, 56, 42, 8] },
  { id: "quadril_d", t: "r", a: [70, 172, 30, 28, 8] }, { id: "quadril_e", t: "r", a: [100, 172, 30, 28, 8] },
  { id: "ombro_d", t: "e", a: [60, 84, 17, 12] }, { id: "ombro_e", t: "e", a: [140, 84, 17, 12] },
  { id: "braco_d", t: "r", a: [42, 96, 18, 46, 8] }, { id: "braco_e", t: "r", a: [140, 96, 18, 46, 8] },
  { id: "cotovelo_d", t: "e", a: [51, 148, 9, 9] }, { id: "cotovelo_e", t: "e", a: [149, 148, 9, 9] },
  { id: "antebraco_d", t: "r", a: [40, 158, 16, 42, 7] }, { id: "antebraco_e", t: "r", a: [144, 158, 16, 42, 7] },
  { id: "mao_d", t: "e", a: [46, 212, 9, 12] }, { id: "mao_e", t: "e", a: [154, 212, 9, 12] },
  { id: "coxa_d", t: "r", a: [72, 204, 26, 70, 10] }, { id: "coxa_e", t: "r", a: [102, 204, 26, 70, 10] },
  { id: "joelho_d", t: "e", a: [85, 285, 13, 11] }, { id: "joelho_e", t: "e", a: [115, 285, 13, 11] },
  { id: "perna_d", t: "r", a: [74, 297, 22, 72, 9] }, { id: "perna_e", t: "r", a: [104, 297, 22, 72, 9] },
  { id: "pe_d", t: "e", a: [84, 384, 14, 9] }, { id: "pe_e", t: "e", a: [116, 384, 14, 9] },
];
// Costas: espelha as peças laterais (a direita do paciente fica à direita da tela)
const mirror = (s: Shape): Shape => (s.t === "e" ? { ...s, a: [200 - s.a[0], ...s.a.slice(1)] } : { ...s, a: [200 - s.a[0] - s.a[2], ...s.a.slice(1)] });
const BACK: Shape[] = [
  { id: "cabeca", t: "e", a: [100, 30, 22, 26] }, { id: "cervical", t: "r", a: [90, 54, 20, 16, 5] },
  { id: "dorsal", t: "r", a: [70, 74, 60, 54, 10] }, { id: "lombar", t: "r", a: [74, 130, 52, 36, 8] },
  { id: "gluteo_e", t: "r", a: [72, 168, 28, 34, 10] }, { id: "gluteo_d", t: "r", a: [100, 168, 28, 34, 10] },
  ...FRONT.filter((s) => /^(ombro|braco|cotovelo|antebraco|mao|coxa|joelho|perna|pe)_/.test(s.id)).map(mirror),
];

function View({ shapes, value, onToggle, readOnly, regions, label }: { shapes: Shape[]; value: string[]; onToggle: (id: string) => void; readOnly?: boolean; regions: Record<string, string>; label: string }) {
  return (
    <figure className="flex flex-col items-center">
      <svg viewBox="0 0 200 400" className="h-72 w-auto" role="group" aria-label={`Mapa corporal — ${label}`}>
        {shapes.map((s) => {
          const on = value.includes(s.id);
          const common = {
            className: cn("stroke-foreground/30 transition-colors", on ? "fill-accent/70 stroke-accent" : "fill-primary/10", !readOnly && "cursor-pointer hover:fill-primary/30"),
            strokeWidth: 1.2, onClick: () => !readOnly && onToggle(s.id), tabIndex: readOnly ? -1 : 0, role: "button" as const, "aria-pressed": on,
            "aria-label": regions[s.id] ?? s.id,
            onKeyDown: (e: React.KeyboardEvent) => { if (!readOnly && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onToggle(s.id); } },
          };
          return s.t === "e" ? (
            <ellipse key={s.id} cx={s.a[0]} cy={s.a[1]} rx={s.a[2]} ry={s.a[3]} {...common}><title>{regions[s.id] ?? s.id}</title></ellipse>
          ) : (
            <rect key={s.id} x={s.a[0]} y={s.a[1]} width={s.a[2]} height={s.a[3]} rx={s.a[4]} {...common}><title>{regions[s.id] ?? s.id}</title></rect>
          );
        })}
      </svg>
      <figcaption className="text-xs text-muted-foreground">{label}</figcaption>
    </figure>
  );
}

export function BodyMap({ value, onChange, regions, readOnly }: { value: string[]; onChange?: (v: string[]) => void; regions: Record<string, string>; readOnly?: boolean }) {
  const toggle = (id: string) => onChange?.(value.includes(id) ? value.filter((x) => x !== id) : [...value, id]);
  return (
    <div className="space-y-2">
      <div className="flex justify-center gap-6">
        <View shapes={FRONT} value={value} onToggle={toggle} readOnly={readOnly} regions={regions} label="Frente" />
        <View shapes={BACK} value={value} onToggle={toggle} readOnly={readOnly} regions={regions} label="Costas" />
      </div>
      <p className="text-center text-xs text-muted-foreground">
        {value.length ? value.map((v) => regions[v] ?? v).join(" · ") : readOnly ? "Nenhuma região marcada" : "Clique nas regiões afetadas"}
      </p>
    </div>
  );
}
