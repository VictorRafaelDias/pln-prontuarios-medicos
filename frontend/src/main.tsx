import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

/** Evita tela branca: mostra o erro com opção de recarregar (o rascunho da consulta é salvo a cada 10 s). */
class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div style={{ maxWidth: 560, margin: "15vh auto", padding: 24, fontFamily: "Inter, sans-serif" }}>
        <h1 style={{ fontFamily: "Fraunces, serif", fontSize: 28 }}>Algo deu errado</h1>
        <p style={{ color: "#666" }}>Seu rascunho é salvo automaticamente a cada 10 segundos. Recarregue a página para continuar.</p>
        <pre style={{ background: "#0001", padding: 12, borderRadius: 8, overflow: "auto", fontSize: 12 }}>{this.state.error.message}</pre>
        <button onClick={() => location.reload()} style={{ padding: "8px 16px", borderRadius: 8, border: 0, background: "#5f7f6a", color: "#fff", cursor: "pointer" }}>Recarregar</button>
      </div>
    );
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ErrorBoundary>
  </React.StrictMode>
);
