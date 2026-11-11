import { useCallback, useEffect, useRef, useState } from "react";

// Web Speech API (Chrome): pt-BR, contínua, com resultados parciais.
const SR: any = typeof window !== "undefined" ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition : null;
export const speechSupported = !!SR;

export function useSpeech(opts: { lang: string; onFinal: (text: string) => void; onInterim: (text: string) => void; onError?: (msg: string) => void }) {
  const [listening, setListening] = useState(false);
  const rec = useRef<any>(null);
  const want = useRef(false);
  const cb = useRef(opts);
  cb.current = opts;

  const build = useCallback(() => {
    const r = new SR();
    r.lang = cb.current.lang || "pt-BR";
    r.continuous = true;
    r.interimResults = true;
    r.maxAlternatives = 1;
    r.onresult = (ev: any) => {
      let interim = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const res = ev.results[i];
        if (res.isFinal) cb.current.onFinal(res[0].transcript.trim());
        else interim += res[0].transcript;
      }
      cb.current.onInterim(interim.trim());
    };
    r.onerror = (e: any) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        want.current = false;
        cb.current.onError?.("Permissão do microfone negada. Libere o microfone nas configurações do site.");
      } else if (e.error === "audio-capture") {
        want.current = false;
        cb.current.onError?.("Nenhum microfone encontrado.");
      } else if (e.error === "network") {
        cb.current.onError?.("Falha de rede no reconhecimento de voz (o Chrome usa servidores do Google).");
      }
    };
    // o Chrome encerra a sessão após silêncios: reinicia enquanto o usuário quiser gravar
    r.onend = () => {
      cb.current.onInterim("");
      if (want.current) {
        try { r.start(); } catch { /* já iniciado */ }
      } else setListening(false);
    };
    return r;
  }, []);

  const start = useCallback(() => {
    if (!SR) return false;
    want.current = true;
    rec.current = rec.current || build();
    try { rec.current.start(); } catch { /* já iniciado */ }
    setListening(true);
    return true;
  }, [build]);

  const stop = useCallback(() => {
    want.current = false;
    try { rec.current?.stop(); } catch { /* ignore */ }
    setListening(false);
    cb.current.onInterim("");
  }, []);

  useEffect(() => () => { want.current = false; try { rec.current?.abort(); } catch { /* ignore */ } }, []);
  return { listening, start, stop, supported: !!SR };
}
