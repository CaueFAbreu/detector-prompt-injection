# Detector de Prompt Injection em Português

[![CI](https://github.com/CaueFAbreu/detector-prompt-injection/actions/workflows/ci.yml/badge.svg)](https://github.com/CaueFAbreu/detector-prompt-injection/actions/workflows/ci.yml)

Detector de prompt injection e jailbreak para mensagens em português, pensado como guardrail de chatbots: recebe a mensagem de um usuário antes de ela chegar ao LLM e indica se ela é uma tentativa de ataque.

> **Status:** em desenvolvimento. Concluídas a estrutura do repositório, a [definição do problema](docs/01_problema.md), com a política de decisão e o protocolo de avaliação fixados antes da coleta de dados, e o [levantamento, a obtenção e a auditoria quantitativa das fontes de dados](docs/02_dados.md). Próximas etapas: auditoria de rótulos e construção do dataset, modelos de referência, fine-tuning de um Transformer, publicação no Hugging Face e integração como guardrail.

## Stack

Python · Hugging Face Hub · pandas · Matplotlib · pytest · Ruff · GitHub Actions

## Instalação

Pré-requisitos: Python 3.13 e Git.

```bash
git clone https://github.com/CaueFAbreu/detector-prompt-injection.git
cd detector-prompt-injection
python -m venv .venv
```

Ative o ambiente virtual:

```powershell
# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
```

```bash
# Linux / macOS
source .venv/bin/activate
```

Instale as dependências:

```bash
python -m pip install -r requirements-dev.txt
```

`requirements.txt` contém apenas as dependências de execução; `requirements-dev.txt` acrescenta as de teste e lint.

## Dados

Os dados não são versionados. Baixe as fontes públicas, na revisão fixada e com conferência de integridade, com:

```bash
python -m src.obtencao
```

O download tem cerca de 3,6 GB e vai para `data/raw/`. Fontes, licenças, critérios de escolha e como confirmar que os arquivos são os mesmos deste projeto estão em [docs/02_dados.md](docs/02_dados.md).

A auditoria das fontes (contagens, duplicatas, comprimentos e sobreposição entre fontes) é gerada com:

```bash
python -m src.auditoria
```

O resultado vai para [reports/auditoria_fontes.json](reports/auditoria_fontes.json), e os gráficos estão em [notebooks/01_auditoria.ipynb](notebooks/01_auditoria.ipynb).

## Verificações

São os mesmos comandos executados pela integração contínua:

```bash
ruff check .
ruff format --check .
pytest
```
