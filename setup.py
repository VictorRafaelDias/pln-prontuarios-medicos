#!/usr/bin/env python
"""Setup do Prontuário Qi (multiplataforma).

Uso:  python setup.py            -> instala tudo (venv, pip, modelo spaCy, NLTK, npm)
      python setup.py --skip-node  -> pula o npm install
      python setup.py --nlp-only   -> só baixa modelo spaCy + recursos NLTK (já dentro do venv)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
SPACY_MODEL = "pt_core_news_md"
NLTK_RESOURCES = ["stopwords", "rslp"]


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    subprocess.run([str(c) for c in cmd], cwd=str(cwd or ROOT), check=True, shell=(os.name == "nt" and cmd[0] == "npm"))


def step(msg: str) -> None:
    print(f"\n=== {msg} ===")


def ensure_python_version() -> None:
    if sys.version_info < (3, 11):
        sys.exit(f"Python 3.11+ é necessário (encontrado {sys.version.split()[0]}).")


def ensure_venv() -> None:
    step("Ambiente virtual (.venv)")
    if not venv_python().exists():
        run([sys.executable, "-m", "venv", VENV])
    else:
        print("já existe")


def pip_install() -> None:
    step("Dependências Python")
    py = venv_python()
    run([py, "-m", "pip", "install", "--upgrade", "pip", "--quiet"])
    run([py, "-m", "pip", "install", "-r", ROOT / "requirements.txt"])


def download_spacy_model() -> None:
    step(f"Modelo spaCy {SPACY_MODEL}")
    py = venv_python()
    ok = subprocess.run([str(py), "-c", f"import spacy; spacy.load('{SPACY_MODEL}')"], capture_output=True).returncode == 0
    if ok:
        print("já instalado")
        return
    run([py, "-m", "spacy", "download", SPACY_MODEL])


def download_nltk() -> None:
    step("Recursos NLTK (stopwords, RSLP)")
    py = venv_python()
    # Pasta local ao projeto (portável e compatível com a validação de caminhos do NLTK ≥ 3.9)
    target = ROOT / "backend" / "nltk_data"
    target.mkdir(parents=True, exist_ok=True)
    code = (
        "import nltk\n"
        f"for r in {NLTK_RESOURCES!r}:\n"
        f"    ok = nltk.download(r, download_dir={str(target)!r}, quiet=True)\n"
        "    print(r, 'ok' if ok else 'FALHOU')\n"
    )
    run([py, "-c", code])


def npm_install() -> None:
    step("Dependências Node (npm)")
    if not shutil.which("npm"):
        print("npm não encontrado — instale o Node.js 18+ e rode novamente.")
        return
    run(["npm", "install", "--no-audit", "--no-fund"], cwd=ROOT)
    run(["npm", "install", "--no-audit", "--no-fund"], cwd=ROOT / "frontend")


def create_env() -> None:
    step("Arquivo .env")
    env, example = ROOT / ".env", ROOT / ".env.example"
    if not env.exists() and example.exists():
        shutil.copy(example, env)
        print(".env criado a partir de .env.example (defina ANTHROPIC_API_KEY para ativar o LLM)")
    else:
        print("já existe" if env.exists() else ".env.example não encontrado")


def main() -> None:
    ensure_python_version()
    args = set(sys.argv[1:])
    if "--nlp-only" in args:
        download_spacy_model()
        download_nltk()
        return
    ensure_venv()
    pip_install()
    download_spacy_model()
    download_nltk()
    if "--skip-node" not in args:
        npm_install()
    create_env()
    print("\nPronto! Para iniciar:  npm run dev   (ou iniciar.bat / ./iniciar.sh)")


if __name__ == "__main__":
    main()
