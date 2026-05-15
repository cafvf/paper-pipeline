import json
from pathlib import Path

from paper_pipeline.obsidian_inventory import main, scan_obsidian_projects, write_projects_jsonl
from paper_pipeline.schema_validation import validate_instance


def write_note(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_scan_obsidian_projects_extracts_profiles_for_all_effort_states(tmp_path: Path):
    write_note(
        tmp_path / "Efforts" / "On" / "CPTu Bayesian Soil Classification.md",
        """---
project_id: cptu_bayesian_classification
title: CPTu Bayesian Soil Classification
objectives:
  - Develop a hybrid probabilistic model for CPTu soil classification
methods:
  - CPTu
  - Robertson chart
knowledge_gaps:
  - distance to nonlinear chart regions
expected_outputs:
  - paper
  - python implementation
priority: high
tags:
  - "#soil-classification"
  - "#CPT-classification"
  - "#soil-classification"
---
# CPTu Bayesian Soil Classification
[[Atlas/Concepts/Bayesian Inference]]
""",
    )
    write_note(
        tmp_path / "Efforts" / "Ongoing" / "Nested" / "Jetted Conductors.md",
        """# Jetted Conductors

## Objectives
- Understand installation limits for jetted conductors.

## Methods
- finite element analysis
- field back-analysis

## Knowledge Gaps
- soil setup mechanisms under offshore loading

## Expected Outputs
- literature review

See also [[Atlas/Maps/Offshore Foundations]].
""",
    )
    write_note(
        tmp_path / "Efforts" / "Simmering" / "Probabilistic Rocks.md",
        """---
tags: "#rock-mechanics"
methods: Bayesian updating
priority: low
---
# Probabilistic Rocks

## Objectives
- Explore probabilistic rock characterization.
""",
    )
    write_note(
        tmp_path / "Efforts" / "Terminated" / "Archived Effort.md",
        """# Archived Effort

## Expected Outputs
- retrospective note
""",
    )
    write_note(tmp_path / "Atlas" / "Concepts" / "Should Not Scan.md", "# Atlas note\n")

    projects = scan_obsidian_projects(tmp_path)

    assert [project["source_path"] for project in projects] == [
        "Efforts/On/CPTu Bayesian Soil Classification.md",
        "Efforts/Ongoing/Nested/Jetted Conductors.md",
        "Efforts/Simmering/Probabilistic Rocks.md",
        "Efforts/Terminated/Archived Effort.md",
    ]

    by_state = {project["project_state"]: project for project in projects}

    on_project = by_state["on"]
    assert on_project["project_id"] == "cptu_bayesian_classification"
    assert on_project["title"] == "CPTu Bayesian Soil Classification"
    assert on_project["objectives"] == ["Develop a hybrid probabilistic model for CPTu soil classification"]
    assert on_project["methods"] == ["CPTu", "Robertson chart"]
    assert on_project["knowledge_gaps"] == ["distance to nonlinear chart regions"]
    assert on_project["expected_outputs"] == ["paper", "python implementation"]
    assert on_project["priority"] == "high"
    assert on_project["state_source"] == "Efforts/On"
    assert on_project["tags"] == ["#soil-classification", "#CPT-classification"]
    assert on_project["links"] == ["Atlas/Concepts/Bayesian Inference"]
    assert on_project["content_hash"].startswith("sha256:")

    ongoing_project = by_state["ongoing"]
    assert ongoing_project["project_id"] == "jetted_conductors"
    assert ongoing_project["title"] == "Jetted Conductors"
    assert ongoing_project["objectives"] == ["Understand installation limits for jetted conductors."]
    assert ongoing_project["methods"] == ["finite element analysis", "field back-analysis"]
    assert ongoing_project["knowledge_gaps"] == ["soil setup mechanisms under offshore loading"]
    assert ongoing_project["expected_outputs"] == ["literature review"]
    assert ongoing_project["priority"] == "medium"
    assert ongoing_project["state_source"] == "Efforts/Ongoing"
    assert ongoing_project["links"] == ["Atlas/Maps/Offshore Foundations"]

    simmering_project = by_state["simmering"]
    assert simmering_project["methods"] == ["Bayesian updating"]
    assert simmering_project["tags"] == ["#rock-mechanics"]
    assert simmering_project["priority"] == "low"

    terminated_project = by_state["terminated"]
    assert terminated_project["title"] == "Archived Effort"
    assert terminated_project["expected_outputs"] == ["retrospective note"]
    assert terminated_project["state_source"] == "Efforts/Terminated"

    for project in projects:
        validate_instance(project, "project_profile.schema.json")
        assert "text" not in project
        assert "body" not in project


def test_scan_obsidian_projects_tolerates_malformed_frontmatter_and_defaults_safely(tmp_path: Path):
    write_note(
        tmp_path / "Efforts" / "On" / "Malformed.md",
        """---
title: Broken Metadata
tags: [#broken
priority: urgent
---
# Recovered Project

## Objectives
- Recover from invalid frontmatter.

## Methods
- resilient parsing

## Knowledge Gaps
- malformed yaml should not crash the scanner

## Expected Outputs
- stable inventory row

[[Atlas/Concepts/Parsing]]
""",
    )

    projects = scan_obsidian_projects(tmp_path)

    assert len(projects) == 1
    project = projects[0]
    assert project["title"] == "Recovered Project"
    assert project["project_id"] == "recovered_project"
    assert project["priority"] == "medium"
    assert project["tags"] == []
    assert project["links"] == ["Atlas/Concepts/Parsing"]
    assert project["objectives"] == ["Recover from invalid frontmatter."]
    assert project["methods"] == ["resilient parsing"]
    assert project["knowledge_gaps"] == ["malformed yaml should not crash the scanner"]
    assert project["expected_outputs"] == ["stable inventory row"]
    validate_instance(project, "project_profile.schema.json")


def test_scan_obsidian_projects_ignores_notes_outside_supported_effort_states(tmp_path: Path):
    write_note(tmp_path / "Efforts" / "Backlog" / "Future Idea.md", "# Future Idea\n")
    write_note(tmp_path / "Projects" / "Project.md", "# Project\n")
    write_note(tmp_path / "Efforts" / "On" / "Tracked.md", "# Tracked\n")

    projects = scan_obsidian_projects(tmp_path)

    assert [project["source_path"] for project in projects] == ["Efforts/On/Tracked.md"]
    assert projects[0]["project_state"] == "on"


def test_scan_obsidian_projects_handles_missing_efforts_tree_as_empty_inventory(tmp_path: Path):
    write_note(tmp_path / "Atlas" / "Concepts" / "Soil.md", "# Soil\n")

    assert scan_obsidian_projects(tmp_path) == []


def test_scan_obsidian_projects_filters_placeholder_values_from_semantic_fields(tmp_path: Path):
    write_note(
        tmp_path / "Efforts" / "On" / "Sparse.md",
        """---
tags:
  - efforts
  - efforts
priority: unknown
---
# Sparse

## Objectives
-
- n/a
- Build a bounded project profile.

## Methods
—
""",
    )

    project = scan_obsidian_projects(tmp_path)[0]

    assert project["objectives"] == ["Build a bounded project profile."]
    assert project["methods"] == []
    assert project["tags"] == ["efforts"]
    assert project["priority"] == "medium"
    validate_instance(project, "project_profile.schema.json")


def test_write_projects_jsonl_is_deterministic_and_does_not_duplicate_full_note_body(tmp_path: Path):
    long_private_paragraph = (
        "PRIVATE BODY TEXT THAT MUST NOT BE COPIED INTO PROJECTS JSONL because it is neither "
        "an extracted field nor a bounded contract value."
    )
    write_note(
        tmp_path / "Efforts" / "On" / "A.md",
        f"""# Project A

## Objectives
- Build project A.

{long_private_paragraph}
""",
    )
    write_note(
        tmp_path / "Efforts" / "Ongoing" / "B.md",
        """# Project B

## Methods
- compare methods
""",
    )

    projects = scan_obsidian_projects(tmp_path)
    output_path = tmp_path / "data" / "projects.jsonl"

    first = write_projects_jsonl(output_path, projects)
    second = write_projects_jsonl(output_path, list(reversed(projects)))

    assert first == second == output_path
    lines = output_path.read_text(encoding="utf-8").splitlines()
    loaded = [json.loads(line) for line in lines]
    assert [row["source_path"] for row in loaded] == [
        "Efforts/On/A.md",
        "Efforts/Ongoing/B.md",
    ]
    assert long_private_paragraph not in output_path.read_text(encoding="utf-8")
    for row in loaded:
        validate_instance(row, "project_profile.schema.json")


def test_obsidian_inventory_module_main_writes_projects_jsonl(tmp_path: Path):
    write_note(
        tmp_path / "Efforts" / "On" / "Runnable.md",
        """# Runnable

## Objectives
- confirm the module can be executed directly
""",
    )
    output_path = tmp_path / "data" / "projects.jsonl"

    exit_code = main(["--vault-root", str(tmp_path), "--output", str(output_path)])

    assert exit_code == 0
    loaded = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert len(loaded) == 1
    assert loaded[0]["title"] == "Runnable"


def test_cli_scan_obsidian_writes_default_project_inventory(tmp_path: Path, capsys):
    from paper_pipeline.cli import main as cli_main

    write_note(
        tmp_path / "vault" / "Efforts" / "On" / "Runnable.md",
        """# Runnable

## Objectives
- confirm CLI scan-obsidian works
""",
    )
    output_path = tmp_path / "data" / "projects.jsonl"

    exit_code = cli_main(["scan-obsidian", "--vault-root", str(tmp_path / "vault"), "--output", str(output_path)])

    assert exit_code == 0
    assert "projects=1" in capsys.readouterr().out
    loaded = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert loaded[0]["title"] == "Runnable"


def test_scan_obsidian_projects_handles_real_effort_patterns_with_emoji_headings_and_numeric_priority(tmp_path: Path):
    write_note(
        tmp_path / "Efforts" / "On" / "Artigo 3D SBL e GPR.md",
        """---
type: effort
priority: 1
project: '[[Caracterização Probabilistica de Solos]]'
tags:
  - efforts
  - effort/paper_candidate
---
# Artigo 3D SBL e GPR

> [!info] Por que este projeto importa?
> Publicação pro currículo

## 🎯 Objetivo

- Revisar e organizar melhor o artigo de modelagem 3D de SUTT usando SBL e GPR.

## 📤 Entregas / Outputs

- Artigo finalizado e submetido a periódico de Eng. de Petróleo ou Geotecnia [[Periódicos-Alvo - Geotecnia Offshore e Petróleo]]
""",
    )
    write_note(
        tmp_path / "Efforts" / "Ongoing" / "Caracterização Probabilistica de Solos.md",
        """---
type: effort
effort_kind: project_hub
priority: 1
tags:
  - efforts
  - effort/project_hub
---
# Objetivo

Reunir um conjunto de técnicas para caracterização de solos de maneira a mensurar também a incerteza estatística dos dados.

# Como fazer?

- consolidar benchmarks
- organizar dados

# Caracterização Probabilistica de Solos

## 🎯 Objetivo

- Montar formulações e modelagens avançadas de caracterização probabilística de solo a partir de dados de ensaios técnicos

## 📤 Entregas / Outputs

- Arcabouço teórico e prático sobre caracterização probabilística de solos
- Artigo sobre a modelagem GPR e SBL publicado
""",
    )
    write_note(
        tmp_path / "Efforts" / "Simmering" / "Análise Probabilística de Projeto de Fundação de Poço.md",
        """---
type: effort
priority: 2
---
## 🎯 Objetivo

- Montar um conjunto de soluções integradas para dimensionamento estrutural probabilístico para fundação de poço.

## 📤 Entregas / Outputs

- Códigos computacionais que realizem avaliações de beta/probabilidade de falha
""",
    )
    write_note(
        tmp_path / "Efforts" / "Terminated" / "Arquivadas" / "Roadmap Integrado Mestre - integrado ao Efforts.md",
        """---
type: effort
priority: 3
state: terminated
---
# Roadmap Integrado Mestre

## Objetivos permanentes

- Entrega aplicada e reputação técnica
- Portfolio de pesquisa publicável
""",
    )

    projects = scan_obsidian_projects(tmp_path)
    by_path = {project["source_path"]: project for project in projects}

    article = by_path["Efforts/On/Artigo 3D SBL e GPR.md"]
    assert article["title"] == "Artigo 3D SBL e GPR"
    assert article["priority"] == "high"
    assert article["objectives"] == ["Revisar e organizar melhor o artigo de modelagem 3D de SUTT usando SBL e GPR."]
    assert article["knowledge_gaps"] == []
    assert article["expected_outputs"] == [
        "Artigo finalizado e submetido a periódico de Eng. de Petróleo ou Geotecnia [[Periódicos-Alvo - Geotecnia Offshore e Petróleo]]"
    ]

    hub = by_path["Efforts/Ongoing/Caracterização Probabilistica de Solos.md"]
    assert hub["title"] == "Caracterização Probabilistica de Solos"
    assert hub["project_id"] == "caracterizacao_probabilistica_de_solos"
    assert hub["priority"] == "high"
    assert hub["objectives"] == [
        "Montar formulações e modelagens avançadas de caracterização probabilística de solo a partir de dados de ensaios técnicos"
    ]
    assert hub["methods"] == ["consolidar benchmarks", "organizar dados"]
    assert hub["knowledge_gaps"] == []
    assert hub["expected_outputs"] == [
        "Arcabouço teórico e prático sobre caracterização probabilística de solos",
        "Artigo sobre a modelagem GPR e SBL publicado",
    ]

    foundation = by_path["Efforts/Simmering/Análise Probabilística de Projeto de Fundação de Poço.md"]
    assert foundation["title"] == "Análise Probabilística de Projeto de Fundação de Poço"
    assert foundation["priority"] == "medium"
    assert foundation["objectives"] == [
        "Montar um conjunto de soluções integradas para dimensionamento estrutural probabilístico para fundação de poço."
    ]
    assert foundation["knowledge_gaps"] == []
    assert foundation["expected_outputs"] == [
        "Códigos computacionais que realizem avaliações de beta/probabilidade de falha"
    ]

    roadmap = by_path["Efforts/Terminated/Arquivadas/Roadmap Integrado Mestre - integrado ao Efforts.md"]
    assert roadmap["title"] == "Roadmap Integrado Mestre"
    assert roadmap["priority"] == "low"
    assert roadmap["objectives"] == [
        "Entrega aplicada e reputação técnica",
        "Portfolio de pesquisa publicável",
    ]


def test_scan_obsidian_projects_extracts_outcome_methods_and_alerts_from_roadmap_style_notes(tmp_path: Path):
    write_note(
        tmp_path / "Efforts" / "Simmering" / "Roadmap do Portfólio de Pesquisa.md",
        """---
type: effort
priority: 3
---
# Roadmap do Portfólio de Pesquisa

## Outcome (o que ficará escrito)
- Convenção única de sequenciamento do portfólio para F1 e F2.

## Finalidade do documento
Este documento organiza o conjunto de ideias e propostas de trabalho em um portfólio coerente de pesquisa aplicada.

## Pergunta central do portfólio
Como transformar dados geotécnicos offshore limitados e indiretos em inferência útil sob incerteza?

## Eixos metodológicos recorrentes
- inferência Bayesiana
- propagação de incerteza
- random fields e variabilidade espacial

## Sinais de alerta desta versão
1. Não diluir a F1 chamando qualquer problema com CPTu de "classificação".
2. Em `2.1`, manter o modelo Abaqus enxuto.
""",
    )

    project = scan_obsidian_projects(tmp_path)[0]

    assert project["title"] == "Roadmap do Portfólio de Pesquisa"
    assert project["priority"] == "low"
    assert project["objectives"] == [
        "Este documento organiza o conjunto de ideias e propostas de trabalho em um portfólio coerente de pesquisa aplicada.",
        "Como transformar dados geotécnicos offshore limitados e indiretos em inferência útil sob incerteza?",
    ]
    assert project["methods"] == [
        "inferência Bayesiana",
        "propagação de incerteza",
        "random fields e variabilidade espacial",
    ]
    assert project["knowledge_gaps"] == [
        'Não diluir a F1 chamando qualquer problema com CPTu de "classificação".',
        "Em `2.1`, manter o modelo Abaqus enxuto.",
    ]
    assert project["expected_outputs"] == [
        "Convenção única de sequenciamento do portfólio para F1 e F2."
    ]


def test_scan_obsidian_projects_uses_operational_outcome_sections_and_priority_letters(tmp_path: Path):
    write_note(
        tmp_path / "Efforts" / "Ongoing" / "Aba de Classificação.md",
        """---
type: effort
priority: A
---
## Guia de parâmetros (opções sugeridas)

## Project
- [[Sest-Solos]]

## Outcome (artefato que vai existir)
- Uma aba de Classificação de Solos baseada em dados de CPTu

## Bloqueios / Dependências
-

## Definition of Done (auditável)
- [ ] Aba completa
""",
    )

    project = scan_obsidian_projects(tmp_path)[0]

    assert project["title"] == "Aba de Classificação"
    assert project["priority"] == "high"
    assert project["knowledge_gaps"] == []
    assert project["expected_outputs"] == ["Uma aba de Classificação de Solos baseada em dados de CPTu"]
