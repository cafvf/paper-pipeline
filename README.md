# paper-pipeline

Pipeline de ingestão e avaliação de artigos extraído da pasta `x/LLM` de um cofre.

## Objetivo
Tornar o pipeline standalone, configurável pela variável `VAULT_ROOT` e executável localmente.

## Quickstart (substitua os placeholders por caminhos reais)

1) Copiar código do cofre (excluir a pasta de `papers`):

Windows (PowerShell):

   $VaultRoot = 'C:\path\to\vault'   # substitua
   $Dest = 'C:\path\to\dest'         # diretório de destino
   New-Item -ItemType Directory -Path $Dest -Force
   robocopy "$VaultRoot\x\LLM" $Dest /E /XD "papers" ".venv" "__pycache__"

Linux / macOS (bash):

   export VAULT_ROOT=/path/to/vault
   DEST=/path/to/dest
   mkdir -p "$DEST"
   rsync -av --exclude 'papers' --exclude '.venv' --exclude '__pycache__' "$VAULT_ROOT/x/LLM/" "$DEST/"

2) Ajustar imports (se necessário):

   python tools/refactor_imports.py "<DEST>"

3) Criar venv `uv` e instalar dependências:

   python -m venv uv
   # Windows
   .\\uv\\Scripts\\Activate.ps1
   # Linux / macOS
   source uv/bin/activate
   pip install -r requirements.txt

4) Teste rápido:

   pytest -q
   python cli.py --dry-run

## Configuração
Copie `config.example.yaml` → `config.yaml` e preencha `vault_root`, chaves Zotero/LMStudio e outras opções.

## Licença
MIT
