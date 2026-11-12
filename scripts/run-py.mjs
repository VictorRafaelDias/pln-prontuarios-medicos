// Executa um script Python do projeto com o interpretador do .venv (multiplataforma).
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const py = process.platform === "win32" ? join(root, ".venv", "Scripts", "python.exe") : join(root, ".venv", "bin", "python");
const r = spawnSync(py, process.argv.slice(2), { cwd: root, stdio: "inherit", env: { ...process.env, PYTHONUTF8: "1" } });
process.exit(r.status ?? 1);
