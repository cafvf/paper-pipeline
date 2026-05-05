# paper-pipeline

Pipeline standalone para ingestao, triagem e avaliacao de artigos com Zotero,
LM Studio e notas em um cofre Obsidian.

## Objetivo

Manter o codigo e os artefatos de runtime fora do cofre. O repositorio guarda
`paper_pipeline/`, testes, configuracao, `papers/` e `index/`; o cofre
Obsidian fica configurado separadamente como fonte/destino de notas.

## Quickstart

1. Instale as dependencias:

   ```bash
   uv sync
   ```

2. Copie a configuracao de exemplo:

   ```bash
   cp config.example.yaml config.yaml
   ```

3. Edite `config.yaml`.

   Defina `vault_root` para o caminho do seu cofre Obsidian quando quiser que
   inbox, notas de literatura e contexto lexical sejam lidos/escritos no cofre.
   Os caminhos em `paths.llm_root`, `paths.papers_root` e `paths.index_root`
   ficam relativos ao arquivo de configuracao e, por padrao, apontam para este
   repositorio.

4. Rode os testes:

   ```bash
   uv run pytest -q
   ```

5. Teste o CLI:

   ```bash
   uv run paper-pipeline run --config config.yaml --dry-run
   ```

## Licenca

MIT
