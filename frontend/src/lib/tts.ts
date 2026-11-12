import { useCallback, useEffect, useState } from "react";

// Síntese de voz do navegador (Web Speech API / speechSynthesis): local, gratuita e sem chave.
export const ttsSupported = typeof window !== "undefined" && "speechSynthesis" in window;

export type Gender = "f" | "m" | "n";
export interface VoicePrefs { patient?: string; professional?: string; rate: number }

const FEMALE = /maria|francisca|luciana|fernanda|vit[oó]ria|camila|thalita|leila|giovanna|heloisa|raquel|helia|yara|brenda|elza|antonia|google portugu[eê]s do brasil|female|feminina|zira|hazel|susan|ines/i;
const MALE = /daniel|antonio|ant[oô]nio|felipe|ricardo|donato|cristiano|duarte|fernando|jorge|valerio|male|masculin|david|mark|george|humberto/i;

export function voiceGender(v: SpeechSynthesisVoice): Gender {
  if (FEMALE.test(v.name)) return "f";
  if (MALE.test(v.name)) return "m";
  return "n";
}

export function sexToGender(sex?: string): Gender {
  return sex === "F" ? "f" : sex === "M" ? "m" : "n";
}

/** Vozes em português, pt-BR primeiro (ordem estável). */
export function portugueseVoices(all: SpeechSynthesisVoice[]): SpeechSynthesisVoice[] {
  return all
    .filter((v) => v.lang.toLowerCase().startsWith("pt"))
    .sort((a, b) => Number(b.lang.toLowerCase() === "pt-br") - Number(a.lang.toLowerCase() === "pt-br") || a.name.localeCompare(b.name));
}

export function useVoices() {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  useEffect(() => {
    if (!ttsSupported) return;
    const load = () => setVoices(portugueseVoices(window.speechSynthesis.getVoices()));
    load();
    window.speechSynthesis.addEventListener("voiceschanged", load);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", load);
  }, []);
  return voices;
}

export interface Assignment { voice: SpeechSynthesisVoice | null; pitch: number }

/**
 * Escolhe a voz de cada falante. Paciente: pelo sexo cadastrado; profissional: pela configuração.
 * Garante que as duas vozes sejam DIFERENTES (se só existir uma voz, diferencia pelo tom).
 */
export function assignVoices(voices: SpeechSynthesisVoice[], patientSex: string | undefined, profGender: Gender, prefs: VoicePrefs) {
  const byUri = (u?: string) => voices.find((v) => v.voiceURI === u) ?? null;
  const pick = (g: Gender, avoid?: SpeechSynthesisVoice | null): SpeechSynthesisVoice | null => {
    const same = voices.filter((v) => voiceGender(v) === g && v !== avoid);
    return same[0] ?? voices.find((v) => v !== avoid) ?? voices[0] ?? null;
  };
  const pg = sexToGender(patientSex);
  const prof = byUri(prefs.professional) ?? pick(profGender);
  let pat = byUri(prefs.patient);
  if (!pat) {
    // "outro/não informado": voz diferente da do profissional, com tom neutro
    pat = pg === "n" ? voices.find((v) => v !== prof) ?? prof : pick(pg, prof);
  }
  const clash = pat !== null && pat === prof;
  return {
    patient: { voice: pat, pitch: clash ? (pg === "f" ? 1.25 : pg === "m" ? 0.8 : 1.1) : 1 } as Assignment,
    professional: { voice: prof, pitch: clash ? (profGender === "f" ? 1.0 : 0.9) : 1 } as Assignment,
  };
}

/** Fala o texto e resolve quando termina (ou se for cancelado / falhar). */
export function speak(text: string, a: Assignment, rate: number): Promise<void> {
  return new Promise((resolve) => {
    if (!ttsSupported || !text.trim()) return resolve();
    const u = new SpeechSynthesisUtterance(text);
    if (a.voice) { u.voice = a.voice; u.lang = a.voice.lang; } else u.lang = "pt-BR";
    u.rate = rate;
    u.pitch = a.pitch;
    u.onend = () => resolve();
    u.onerror = () => resolve();
    window.speechSynthesis.speak(u);
  });
}

export function stopSpeaking() {
  if (ttsSupported) window.speechSynthesis.cancel();
}

const KEY = "qi:voices";
export function loadPrefs(): VoicePrefs {
  try { return { rate: 1, ...(JSON.parse(localStorage.getItem(KEY) || "{}")) }; } catch { return { rate: 1 }; }
}
export function savePrefs(p: VoicePrefs) {
  try { localStorage.setItem(KEY, JSON.stringify(p)); } catch { /* ignore */ }
}

/** Estimativa da duração da fala (ms), usada para "digitar" as palavras em sincronia com a voz. */
export const estimateMs = (text: string, rate: number) => Math.max(900, (text.split(/\s+/).length * 360) / Math.max(0.5, rate));

export function usePrefs() {
  const [prefs, setPrefs] = useState<VoicePrefs>(loadPrefs);
  const update = useCallback((patch: Partial<VoicePrefs>) => setPrefs((p) => { const n = { ...p, ...patch }; savePrefs(n); return n; }), []);
  return [prefs, update] as const;
}
