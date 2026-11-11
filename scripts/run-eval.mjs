import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const py = process.platform === "win32" ? join(root, ".venv", "Scripts", "python.exe") : join(root, ".venv", "bin", "python");
const code = `
import sys, json; sys.path.insert(0, 'backend')
from nlp.evaluation import run_evaluation
r = run_evaluation()
for k, v in r['approaches'].items():
    print(k, v if not v.get('available') else {**v['overall'], 'macro_f1': v['macro_f1']})
`;
const r = spawnSync(py, ["-c", code], { cwd: root, stdio: "inherit", env: { ...process.env, PYTHONUTF8: "1" } });
process.exit(r.status ?? 1);
