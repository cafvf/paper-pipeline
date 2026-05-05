# paper-pipeline

Pipeline de ingestão e avaliação de artigos extraído de ChrisVault4.0 (`x/LLM`).

## Objetivo
Tornar o pipeline standalone, configurável pelo `VAULT_ROOT` e executável localmente.

## Quickstart (Windows PowerShell)
1. Copiar código do vault (exclui `papers/`):
   New-Item -ItemType Directory -Path "D:\git\paper-pipeline"
   robocopy "D:\ChrisVault4.0\x\LLM" "D:\git\paper-pipeline" /E /XD "papers" ".venv" "__pycache__"

2. Ajustar imports (veja `tools/refactor_imports.py`):
   python tools/refactor_imports.py "D:\git\paper-pipeline"

3. Criar venv e instalar:
   python -m venv .venv
   . .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt

4. Teste smoke:
   pytest -q
   python cli.py --dry-run

## Configuração
Copie `config.example.yaml` → `config.yaml` e configure `vault_root`, chaves Zotero/LMStudio etc.

## Licença
MIT
