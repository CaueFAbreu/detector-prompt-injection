# Detector de Prompt Injection em Português

[![CI](https://github.com/CaueFAbreu/detector-prompt-injection/actions/workflows/ci.yml/badge.svg)](https://github.com/CaueFAbreu/detector-prompt-injection/actions/workflows/ci.yml)

Detector de prompt injection e jailbreak para mensagens em português, pensado como guardrail de chatbots: recebe a mensagem de um usuário antes de ela chegar ao LLM e indica se ela é uma tentativa de ataque.

> **Status:** em desenvolvimento. Concluídas a estrutura do repositório e a [definição do problema](docs/01_problema.md), com a política de decisão e o protocolo de avaliação fixados antes da coleta de dados. Próximas etapas: construção do dataset, modelos de referência, fine-tuning de um Transformer, publicação no Hugging Face e integração como guardrail.

## Stack

Python · pytest · Ruff · GitHub Actions

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

## Verificações

São os mesmos comandos executados pela integração contínua:

```bash
ruff check .
ruff format --check .
pytest
```
