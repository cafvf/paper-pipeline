# paper-pipeline

Pipeline standalone para ingestao, triagem e avaliacao de artigos com Zotero,
LM Studio e notas em um cofre Obsidian.

## Objetivo

Manter o codigo e os artefatos de runtime fora do cofre. O repositorio guarda
`paper_pipeline/`, testes, configuracao, `papers/` e `index/`; o cofre
Obsidian fica configurado separadamente como fonte/destino de notas.

## Estado Atual

O pipeline atual e centrado em triagem de artigos a partir de colecoes
operacionais do Zotero, com apoio de contexto lexical do Obsidian, LM Studio,
conversao de PDF, artefatos auditaveis e notas de decisao humana.

Uma rodada recente de auditoria documentou o caminho incremental para evoluir o
projeto para uma assistente local Obsidian + Zotero baseada no par
`projeto/objetivo <-> artigo`. Esse roadmap preserva a regra central de
seguranca: primeiro ler, classificar e exportar revisoes; somente depois de
aprovacao humana aplicar tags no Zotero ou criar notas permanentes no
Obsidian.

## Quickstart

1. Instale as dependencias:

   ```bash
   uv sync --locked
   ```

2. Copie a configuracao de exemplo:

   ```bash
   cp config.example.yaml config.yaml
   ```

3. Edite `config.yaml` e `.env`.

   Defina `VAULT_ROOT` no `.env` para o caminho absoluto do seu cofre Obsidian.
   Arquivos de decisao humana devem ir para uma inbox unica do Obsidian definida
   em `.env` ou variaveis de ambiente. `VAULT_ROOT` deve ser absoluto; os demais
   caminhos podem ser relativos a ele.
   Os caminhos em `paths.llm_root`, `paths.papers_root` e `paths.index_root`
   ficam relativos ao arquivo de configuracao e, por padrao, apontam para este
   repositorio.

4. Rode os testes:

   ```bash
   uv run pytest -q -o addopts=
   ```

5. Teste o CLI:

   ```bash
   uv run paper-pipeline run --config config.yaml --dry-run
   ```

## Documentacao

- `docs/vision.md`: problema, camadas Obsidian/Zotero e limites da LLM.
- `docs/architecture.md`: arquitetura atual, fluxo alvo e fronteiras de escrita.
- `docs/roadmap.md`: aderencia aos 13 projetos planejados.
- `docs/development_guidelines.md`: diretrizes de engenharia, TDD/XP/Clean Code/Spec-Driven e politica obrigatoria de testes.
- `docs/efforts_authoring.md`: como estruturar notas em `Efforts/` para melhorar a extração de `ProjectProfile`.
- `docs/modules.md`: responsabilidades, entradas, saidas e efeitos colaterais.
- `docs/data_contracts.md`: contratos esperados para projeto, artigo, matching,
  classificacao, revisao humana e runs.
- `docs/zotero_policy.md`: politica de leitura/escrita, tags e credenciais.
- `docs/obsidian_policy.md`: politica de identificacao de projetos, revisoes e
  notas permanentes.
- `docs/human_review_workflow.md`: fluxo recomendacao -> revisao -> aprovacao.
- `docs/development_plan.md`: ciclos pequenos de implementacao e validacao.
- `docs/workflow_spec.md`: comandos independentes, artefatos, reviews por
  rodada, camadas de entrada da LLM e politica de execucao noturna.
- `docs/reading_protocol_criteria.md`: criterios operacionais derivados do
  protocolo de leitura local do usuario para recomendacao de estagios Zotero.

## Desenvolvimento

O desenvolvimento deste repositorio segue conjuntamente Test-Driven
Development, Extreme Programming, Clean Code e Spec-Driven Development.

- comportamento novo ou alterado comeca pela spec, contrato, schema ou plano;
- toda mudanca de comportamento exige testes automatizados no mesmo diff;
- implementacao sem teste nao conclui a entrega;
- refatoracao deve manter o design simples, nomes claros, baixo acoplamento e
  pouca duplicacao.

Consulte `docs/development_guidelines.md` para o fluxo esperado de trabalho e
os criterios de revisao.

## Seguranca Operacional

- Nao versionar `config.yaml`, `.env`, caches, PDFs, bancos locais ou artefatos
  de runtime.
- Manter `save_payloads: false` salvo quando houver uma razao explicita para
  auditar payloads locais.
- Usar adapters/fakes em testes de Zotero; comandos com credenciais podem ler a
  API real.
- Tratar qualquer escrita em Zotero ou no cofre Obsidian como acao
  explicitamente aprovada pelo usuario.

## Migracao Do Layout Antigo

Este repositorio nao espera mais existir dentro de `x/LLM`. Referencias antigas
a `x/LLM/pipeline_config.example.yaml`, `x/LLM/papers` ou execucao com
`cwd="x/LLM"` devem apontar para a raiz do repositorio e para
`config.example.yaml`.

## Licenca

MIT
