// Componentes de UI no estilo shadcn/ui (Radix + Tailwind + cva), reunidos em um só arquivo.
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import * as TabsP from "@radix-ui/react-tabs";
import * as DialogP from "@radix-ui/react-dialog";
import * as TooltipP from "@radix-ui/react-tooltip";
import * as SliderP from "@radix-ui/react-slider";
import * as SwitchP from "@radix-ui/react-switch";
import * as CollapsibleP from "@radix-ui/react-collapsible";
import * as PopoverP from "@radix-ui/react-popover";
import { cva, type VariantProps } from "class-variance-authority";
import { ChevronDown, X } from "lucide-react";
import { cn } from "@/lib/utils";

/* ---------- Button */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 active:scale-[.98] [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground shadow-soft hover:bg-primary/90",
        accent: "bg-accent text-accent-foreground shadow-soft hover:bg-accent/90",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline: "border border-input bg-card hover:bg-secondary",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/70",
        ghost: "hover:bg-secondary",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: { default: "h-10 px-4 py-2", sm: "h-8 px-3 text-xs", lg: "h-12 px-6 text-base", icon: "h-9 w-9" },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> { asChild?: boolean }
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, asChild, ...p }, ref) => {
  const C = asChild ? Slot : "button";
  return <C ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...p} />;
});
Button.displayName = "Button";

/* ---------- Card, Input, Textarea, Label, Badge, Skeleton */
export const Card = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("rounded-lg border bg-card text-card-foreground shadow-soft", className)} {...p} />
);
export const CardHeader = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => <div className={cn("flex flex-col gap-1 p-5 pb-3", className)} {...p} />;
export const CardTitle = ({ className, ...p }: React.HTMLAttributes<HTMLHeadingElement>) => <h3 className={cn("font-serif text-lg font-semibold leading-tight", className)} {...p} />;
export const CardContent = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => <div className={cn("p-5 pt-0", className)} {...p} />;

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, type, ...p }, ref) => (
  <input ref={ref} type={type} className={cn("flex h-10 w-full rounded-md border border-input bg-card px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50", className)} {...p} />
));
Input.displayName = "Input";
export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(({ className, ...p }, ref) => (
  <textarea ref={ref} className={cn("flex min-h-[72px] w-full rounded-md border border-input bg-card px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", className)} {...p} />
));
Textarea.displayName = "Textarea";
export const Label = ({ className, ...p }: React.LabelHTMLAttributes<HTMLLabelElement>) => <label className={cn("text-sm font-medium leading-none", className)} {...p} />;
export const Select = ({ className, ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) => (
  <select className={cn("h-10 rounded-md border border-input bg-card px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", className)} {...p} />
);
export const Skeleton = ({ className }: { className?: string }) => <div className={cn("animate-pulse rounded-md bg-muted", className)} />;

const badgeVariants = cva("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium transition-colors", {
  variants: {
    variant: {
      default: "border-transparent bg-primary/15 text-primary", outline: "text-foreground", accent: "border-transparent bg-accent/15 text-accent",
      destructive: "border-transparent bg-destructive/15 text-destructive", muted: "border-transparent bg-muted text-muted-foreground",
      solid: "border-transparent bg-primary text-primary-foreground", warn: "border-transparent bg-amber-500/20 text-amber-700 dark:text-amber-300",
    },
  },
  defaultVariants: { variant: "default" },
});
export const Badge = ({ className, variant, ...p }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) => (
  <span className={cn(badgeVariants({ variant }), className)} {...p} />
);

/* ---------- Tabs */
export const Tabs = TabsP.Root;
export const TabsList = ({ className, ...p }: TabsP.TabsListProps) => (
  <TabsP.List className={cn("inline-flex h-10 items-center gap-1 rounded-lg bg-muted p-1 text-muted-foreground", className)} {...p} />
);
export const TabsTrigger = ({ className, ...p }: TabsP.TabsTriggerProps) => (
  <TabsP.Trigger className={cn("inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm [&_svg]:size-4", className)} {...p} />
);
export const TabsContent = ({ className, ...p }: TabsP.TabsContentProps) => (
  <TabsP.Content className={cn("mt-4 focus-visible:outline-none animate-fade-in", className)} {...p} />
);

/* ---------- Dialog */
export const Dialog = DialogP.Root;
export const DialogTrigger = DialogP.Trigger;
export const DialogClose = DialogP.Close;
export function DialogContent({ className, children, ...p }: DialogP.DialogContentProps) {
  return (
    <DialogP.Portal>
      <DialogP.Overlay className="fixed inset-0 z-50 bg-foreground/40 backdrop-blur-[2px] data-[state=open]:animate-in data-[state=open]:fade-in-0" />
      <DialogP.Content className={cn("fixed left-1/2 top-1/2 z-50 grid w-[92vw] max-w-lg -translate-x-1/2 -translate-y-1/2 gap-4 rounded-lg border bg-card p-6 shadow-soft data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 max-h-[90vh] overflow-y-auto", className)} {...p}>
        {children}
        <DialogP.Close className="absolute right-4 top-4 rounded-sm opacity-60 hover:opacity-100"><X className="size-4" /></DialogP.Close>
      </DialogP.Content>
    </DialogP.Portal>
  );
}
export const DialogTitle = ({ className, ...p }: DialogP.DialogTitleProps) => <DialogP.Title className={cn("font-serif text-xl font-semibold", className)} {...p} />;
export const DialogDescription = ({ className, ...p }: DialogP.DialogDescriptionProps) => <DialogP.Description className={cn("text-sm text-muted-foreground", className)} {...p} />;

/* ---------- Tooltip */
export const TooltipProvider = TooltipP.Provider;
export function Tip({ children, content, side = "top", className }: { children: React.ReactNode; content: React.ReactNode; side?: "top" | "bottom" | "left" | "right"; className?: string }) {
  if (!content) return <>{children}</>;
  return (
    <TooltipP.Root delayDuration={120}>
      <TooltipP.Trigger asChild>{children}</TooltipP.Trigger>
      <TooltipP.Portal>
        <TooltipP.Content side={side} sideOffset={6} className={cn("z-[60] max-w-sm rounded-md border bg-card px-3 py-2 text-xs text-card-foreground shadow-soft animate-in fade-in-0 zoom-in-95", className)}>
          {content}
          <TooltipP.Arrow className="fill-card" />
        </TooltipP.Content>
      </TooltipP.Portal>
    </TooltipP.Root>
  );
}

/* ---------- Slider (EVA colorido), Switch, Progress */
export function EvaSlider({ value, onChange, max = 10 }: { value: number | null; onChange: (v: number) => void; max?: number }) {
  return (
    <SliderP.Root className="relative flex h-6 w-full touch-none select-none items-center" value={[value ?? 0]} max={max} step={1} onValueChange={(v) => onChange(v[0])}>
      <SliderP.Track className="slider-eva relative h-2.5 w-full grow overflow-hidden rounded-full opacity-90">
        <SliderP.Range className="absolute h-full bg-transparent" />
      </SliderP.Track>
      <SliderP.Thumb className={cn("block size-5 rounded-full border-2 border-foreground/70 bg-card shadow transition-transform focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring hover:scale-110", value === null && "opacity-40")} />
    </SliderP.Root>
  );
}
export const Switch = ({ className, ...p }: SwitchP.SwitchProps) => (
  <SwitchP.Root className={cn("peer inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent bg-input transition-colors data-[state=checked]:bg-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", className)} {...p}>
    <SwitchP.Thumb className="pointer-events-none block size-5 rounded-full bg-card shadow transition-transform data-[state=checked]:translate-x-5" />
  </SwitchP.Root>
);
export const Progress = ({ value, className }: { value: number; className?: string }) => (
  <div className={cn("h-2 w-full overflow-hidden rounded-full bg-muted", className)}>
    <div className="h-full rounded-full bg-primary transition-all duration-500" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
  </div>
);

/* ---------- Collapsible section */
export function Section({ title, badge, defaultOpen = true, children, className }: { title: React.ReactNode; badge?: React.ReactNode; defaultOpen?: boolean; children: React.ReactNode; className?: string }) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <CollapsibleP.Root open={open} onOpenChange={setOpen} className={cn("rounded-lg border bg-card shadow-soft", className)}>
      <CollapsibleP.Trigger className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left">
        <span className="flex items-center gap-2 font-serif text-base font-semibold">{title}{badge}</span>
        <ChevronDown className={cn("size-4 text-muted-foreground transition-transform", open && "rotate-180")} />
      </CollapsibleP.Trigger>
      <CollapsibleP.Content className="data-[state=open]:animate-fade-in">
        <div className="space-y-3 border-t px-4 py-4">{children}</div>
      </CollapsibleP.Content>
    </CollapsibleP.Root>
  );
}

export const Popover = PopoverP.Root;
export const PopoverTrigger = PopoverP.Trigger;
export const PopoverContent = ({ className, ...p }: PopoverP.PopoverContentProps) => (
  <PopoverP.Portal>
    <PopoverP.Content sideOffset={6} className={cn("z-50 w-72 rounded-md border bg-card p-3 shadow-soft outline-none animate-in fade-in-0 zoom-in-95", className)} {...p} />
  </PopoverP.Portal>
);

export function Empty({ icon, title, children }: { icon?: React.ReactNode; title: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed p-8 text-center text-muted-foreground">
      {icon}
      <p className="font-serif text-base text-foreground">{title}</p>
      {children && <div className="text-sm">{children}</div>}
    </div>
  );
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{children}</kbd>;
}
