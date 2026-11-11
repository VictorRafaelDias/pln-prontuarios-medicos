# PLN — Prontuários médicos (Prontuário Qi)

Sistema local de documentação clínica para acupuntura, com pipeline de PLN inspecionável (projeto da disciplina de Processamento de Linguagem Natural).

> README completo (arquitetura do PLN, decisões e limitações) em construção.

## Como rodar

```bash
python setup.py      # cria .venv, instala dependências, baixa spaCy pt_core_news_md e NLTK (stopwords, RSLP), npm install
npm run dev          # sobe API (porta 8010) + frontend (http://localhost:5173)
```

No Windows: `iniciar.bat`. Sem `ANTHROPIC_API_KEY` no `.env`, funciona só com o PLN clássico.

Testes: `npm test` · Avaliação: `npm run eval`

Observação: a Web Speech API do Chrome envia o áudio aos servidores do Google. Todos os dados de pacientes do repositório são fictícios.
