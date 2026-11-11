// Sobe a API FastAPI usando o Python do .venv (multiplataforma).
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const py = process.platform === "win32" ? join(root, ".venv", "Scripts", "python.exe") : join(root, ".venv", "bin", "python");
if (!existsSync(py)) {
  console.error("Ambiente Python não encontrado. Rode primeiro:  python setup.py");
  process.exit(1);
}
const port = process.env.API_PORT || "8010";
const args = ["-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--port", port, "--host", "127.0.0.1", ...(process.argv.includes("--no-reload") ? [] : ["--reload", "--reload-dir", "backend/app", "--reload-dir", "backend/nlp"])];
const child = spawn(py, args, { cwd: root, stdio: "inherit", env: { ...process.env, PYTHONUTF8: "1" } });
child.on("exit", (code) => process.exit(code ?? 0));
