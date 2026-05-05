Migration notes

1) Criar pasta destino e copiar (PowerShell):
New-Item -ItemType Directory -Path "D:\git\paper-pipeline"
robocopy "D:\ChrisVault4.0\x\LLM" "D:\git\paper-pipeline" /E /XD "papers" ".venv" "__pycache__"

ou (git-bash/rsync):
mkdir -p /d/git/paper-pipeline
rsync -av --exclude 'papers' --exclude '.venv' --exclude '__pycache__' "D:/ChrisVault4.0/x/LLM/" "D:/git/paper-pipeline/"

2) Ajustar imports:
python tools/refactor_imports.py "D:\git\paper-pipeline"

3) Criar venv, instalar e testar:
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest -q
python cli.py --dry-run

4) Git init & push:
git init
git add .
git commit -m "Initial scaffold: paper-pipeline (extracted from vault)"
# criar repo remoto manualmente ou usar GitHub CLI:
gh repo create youruser/paper-pipeline --public --source=. --remote=origin --push
