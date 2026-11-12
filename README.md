# PLN — Prontuários médicos (Prontuário Qi)

Sistema **local** de documentação clínica para uma clínica de acupuntura. Durante a consulta ele escuta a conversa entre acupunturista e paciente, transcreve em tempo real, processa o texto com um **pipeline de PLN inspecionável** e preenche sozinho o formulário de anamnese/evolução. O profissional revisa, corrige, salva ou descarta. Todo campo automático é uma **sugestão** até ser confirmado.

Projeto acadêmico da disciplina de Processamento de Linguagem Natural. **Todos os dados de pacientes no repositório são fictícios.**

## Stack

| Camada | Tecnologias |
|---|---|
| Frontend | React + Vite + TypeScript + Tailwind + componentes estilo shadcn/ui (Radix) + lucide-react + Recharts |
| Backend | Python 3.11+ · FastAPI · SQLite (SQLModel) · Pydantic |
| PLN | spaCy `pt_core_news_md` · NLTK (stopwords + stemmer RSLP) · regex · scikit-learn (TF-IDF e métricas) |
| LLM (opcional) | Anthropic SDK **no backend** (a chave nunca vai ao navegador) |
| Voz | Web Speech API do Chrome (pt-BR, contínua, parciais) |

## Instalação e execução

Requisitos: Python 3.11+, Node 18+ e Chrome (para o microfone).

```bash
python setup.py     # .venv, dependências, modelo spaCy, recursos NLTK, npm install, .env
npm run dev         # API (porta 8010) + frontend (http://localhost:5173) juntos
```

Atalhos: `iniciar.bat` (Windows) ou `./iniciar.sh` (Linux/macOS) fazem tudo e abrem o navegador.
Outros comandos: `npm test` (pytest) · `npm run eval` (avaliação com o gold standard).

O banco `backend/data/prontuario.db` é criado e populado com **5 pacientes fictícios** na primeira execução.

### Configurar o LLM (opcional)

Copie `.env.example` para `.env` e preencha:

```
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-opus-5-5     # ou claude-sonnet-5-5 / claude-haiku-5-5 (mais baratos)
```

Sem chave, o sistema funciona 100% com o PLN clássico e mostra o selo **“Somente PLN clássico”**. O custo exibido no Laboratório é uma **estimativa** (preços de referência embutidos, ajustáveis no `.env`).

### Uso no Chrome e privacidade

A Web Speech API do Chrome **envia o áudio para servidores do Google** para transcrever. Os demais dados ficam na sua máquina (SQLite local). Em navegadores sem suporte há um aviso e a opção de **digitar/colar** a transcrição. Há também o botão **Simular consulta**, que “fala” uma transcrição fictícia (com negações, ex-hábitos, números por extenso, incerteza e oralidade) para testar sem microfone. O consentimento LGPD é obrigatório para salvar.

O formulário de localização usa um **mapa corporal SVG clicável** (frente/costas).

Atalhos: **Espaço** grava/pausa (fora de campos) · **Ctrl+S** vai à revisão · **Ctrl+K** abre a busca global (pacientes, queixas, padrões de MTC, pontos).

## Telas

Início · Nova consulta (dados + LGPD → transcrição ao vivo × formulário em tempo real → revisão) · Atualizar prontuário (nova sessão SOAP, com resumo da última sessão) · Pacientes (busca instantânea e filtros) · Prontuário (Anamnese, Sessões, Evolução da dor/EVA, Documentos, Histórico de alterações) · **Laboratório PLN** · Configurações (status do LLM, clínica, backup/restauração). PDF clínico com cabeçalho da clínica. Rascunho salvo automaticamente a cada 10 s.

---

## Arquitetura do PLN

O pipeline vive em `backend/nlp/`. Cada etapa é uma classe (`nlp/stages/sNN_*.py`) que recebe o estado da anterior e registra **entrada, saída e tempo (ms)**; o orquestrador é `nlp/pipeline.py`. Tudo pode ser inspecionado no **Laboratório PLN** (modo passo a passo, texto anotado, tabelas, estatísticas, comparativo Regras × LLM, avaliação, inspeção do LLM, **editor de dicionários com reprocessamento imediato** e exportação em JSON/HTML/PDF).

| # | Etapa | O que faz | Por que |
|---|---|---|---|
| 1 | Entrada (ASR) | Texto bruto + timestamp + falante (Profissional/Paciente) | O falante muda o peso da informação: relato × pergunta/ditado |
| 2 | Normalização | Remove hesitações (“é...”, “tipo”, “né”, “aham”), padroniza pontuação, expande abreviações, converte números por extenso (“dez cigarros” → 10, “uns três meses” → 3 meses). Mostra o diff | Ruído da fala quebra regras; dígitos permitem extrair EVA, frequência e duração |
| 3 | Sentenças | Fronteira rígida por fala + pontuação | Negação e mapeamento funcionam por sentença |
| 4 | Tokenização | spaCy; índice e posição; contagem de tokens do LLM (real com chave, estimada sem) | Compara tokenização por palavras × subpalavras |
| 5 | Stopwords | NLTK + extras − **palavras preservadas** | ver decisões abaixo |
| 6 | Lema × Stem | spaCy × RSLP lado a lado | Agrupar variações; lema é legível, stem é agressivo |
| 7 | POS e dependências | Parser do spaCy + árvore (displaCy) | Sintaxe, lateralidade e tempo verbal |
| 8 | NER clínico híbrido | `EntityRuler` com dicionários JSON editáveis + regex (intensidade, frequência, tempo, pontos) + NER estatístico | O modelo geral não conhece “VB20” nem “estagnação de qi” |
| 9 | Negação e incerteza | NegEx adaptado ao português (gatilhos, janela, terminadores, pseudo-negação, estado passado) | Evita registrar “fumante” porque a palavra “fumo” apareceu |
| 10 | Mapeamento | Regras + pares pergunta→resposta + similaridade TF-IDF/cosseno, com confiança | Entidade sozinha não preenche campo |
| 11 | Extração por LLM | JSON estrito (saída estruturada) com valor, confiança e trecho de origem | Entende paráfrases que regras não cobrem |
| 12 | Fusão | Combina Regras + LLM, marcando origem (Regras / LLM / Ambos / Manual) | Os dois erram de formas diferentes |

Os dicionários (`nlp/resources/dictionaries/*.json`), os gatilhos de negação, as stopwords e as abreviações são arquivos JSON editáveis.

### Decisões de projeto

- **Por que preservar negações nas stopwords?** A lista do NLTK contém “não”, “nem”, “sem”, “muito”, “pouco”, “já”. Em texto clínico são exatamente as palavras que decidem o significado (“não fumo” ≠ “fumo”; “dor muito forte” ≠ “dor forte”). A lista de preservadas é separada por categoria (negação, intensidade, tempo, incerteza, contraste) e a interface justifica cada uma.
- **Por que abordagem híbrida?** O NER estatístico foi treinado em texto geral (pessoas, lugares, organizações). Dicionários dão precisão e controle sobre termos clínicos e de MTC; regex captura valores numéricos; o spaCy cobre o restante. O LLM entra por cima para paráfrases, e a fusão evita depender cegamente de qualquer um.
- **Regra de prioridade da fusão (etapa 12):** P1 campo confirmado nunca é sobrescrito · P2 só um método extraiu → vale esse · P3 concordam → “Ambos”, confiança combinada 1−(1−c₁)(1−c₂) · P4 divergem em contraindicação → vale a afirmação (segurança primeiro) · P5 divergem em campo estruturado → vale a regra numérica explícita (≥ 0,85), senão a maior confiança · P6 divergem em texto livre → maior confiança (LLM com +0,05); o outro valor fica em “alternativas”.
- **Saída estruturada em vez de tool_choice forçado:** modelos recentes rejeitam `tool_choice` forçado; o JSON Schema garante JSON válido sem isso.
- **Respostas curtas dependem da pergunta:** “Não.” só vira dado junto da pergunta anterior do profissional (ex.: “Está grávida?”).

### Avaliação

`nlp/gold/gold_standard.json` tem **10 transcrições fictícias** anotadas manualmente (7 anamneses e 3 sessões SOAP, com casos difíceis). O botão **Rodar avaliação** calcula precisão, recall e F1 por campo e geral (Regras, LLM e Híbrido), matrizes de confusão e a lista de falsos positivos/negativos com o trecho. Resultado atual das **Regras: F1 ≈ 0,92** (macro-F1 ≈ 0,90). LLM e Híbrido só são avaliados com chave configurada.

> Ressalva honesta: gold standard e regras foram escritos pelo mesmo autor, no mesmo conjunto de casos. O F1 é um **indicativo**, não uma medida de generalização.

### Limitações

- Cobertura dos dicionários é limitada (os mais comuns em acupuntura); termos fora deles dependem do LLM.
- “pulso” (MTC) e “pulso” (punho) são ambíguos; só vale como MTC com descritor depois (“pulso fino”).
- Lateralidade e pares pergunta→resposta usam heurísticas simples (resposta imediata à pergunta anterior).
- Web Speech API erra nomes de medicamentos e pontos falados; o profissional pode editar a transcrição.
- O caminho do LLM foi testado com **cliente simulado** (sem chave no desenvolvimento); a chamada real depende de configuração do usuário.
- O mapa corporal é um desenho esquemático (regiões geométricas), suficiente para marcar a localização, mas não anatômico.

## Estrutura

```
backend/app/     API FastAPI, modelos SQLite, seed, PDF
backend/nlp/     pipeline (stages/), dicionários, avaliação, gold standard
backend/tests/   pytest (normalização, números, negação, NER, mapeamento, LLM simulado, fusão, avaliação)
frontend/src/    pages/ (telas), components/, lib/
scripts/         execução da API, testes e avaliação
```
