Migration notes

Steps to migrate code from a vault's `x/LLM` folder into this repository. Replace `<VAULT_ROOT>` and `<DEST>` with your paths.

1) Create destination and copy files

Windows (PowerShell):

	$VaultRoot = 'C:\path\to\vault'
	$Dest = 'C:\path\to\dest'
	New-Item -ItemType Directory -Path $Dest -Force
	robocopy "$VaultRoot\x\LLM" $Dest /E /XD "papers" ".venv" "__pycache__"

Linux / macOS (bash):

	VAULT_ROOT=/path/to/vault
	DEST=/path/to/dest
	mkdir -p "$DEST"
	rsync -av --exclude 'papers' --exclude '.venv' --exclude '__pycache__' "$VAULT_ROOT/x/LLM/" "$DEST/"

2) Adjust imports (if needed):

	python tools/refactor_imports.py "<DEST>"

3) Create virtual env, install and test:

	python -m venv uv
	# Windows
	.\\uv\\Scripts\\Activate.ps1
	# Linux / macOS
	source uv/bin/activate
	pip install -r requirements.txt
	pytest -q
	python cli.py --dry-run

4) Git init & push:

	git init
	git add .
	git commit -m "Initial scaffold: paper-pipeline (extracted from vault)"
	# create remote manually or with GitHub CLI (optional):
	# gh repo create <owner>/<repo> --public --source=. --remote=origin --push
