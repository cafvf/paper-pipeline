---
type: note
up: "[[Atlas/Atlas]]"
aliases: []
tags:
  - protocol
  - reading
  - research
created: 2026-03-13
changed: 2026-04-28
---
# Research Reading Protocol
### Geomechanics Applied to Structural Analysis in Oil & Gas
_Versão 1.4 | Março 2026 | Documento vivo - revisar a cada 6 meses_

---

## 0. Filosofia do protocolo

Este protocolo resolve três problemas distintos e independentes:

1. **Volume**: como processar um grande influxo de artigos sem afundar.
2. **Profundidade**: como identificar o que realmente merece estudo completo e implementação.
3. **Utilidade**: como garantir que o que você leu vira insumo concreto para seus papers.

A lógica central é um **funil de três camadas progressivas**. O artigo só avança quando passa um gate explícito. A maioria fica e morre nas primeiras camadas, e isso é o comportamento correto.

> **Regra de ouro**: literature notes no Obsidian só são criadas a partir de `TO REVIEW`.
> Descartes em `TO LOOK` ficam apenas no Zotero com tags mínimas.

---

## 1. Fluxo completo: quando criar cada tipo de nota

```text
Artigo capturado
  -> Zotero: import + citekey
  -> Tags: @look + #topic
  -> Gate 1: ao menos 1 trigger?
     -> nao: descarte, sem nota
     -> sim:
        -> triagem de abstract + intro + conclusao
        -> score 6 criterios
        -> Gate 2: score >= 3/6?
           -> nao: permanece em Look
           -> sim:
              -> criar Literature Note
              -> preencher secoes 1, 2, 3
              -> Gate 3: criterios de TO DIG?
                 -> nao: permanece em Review
                 -> sim:
                    -> leitura profunda + anotacoes no Zotero
                    -> preencher secoes de deep reading, selecao manual e saidas
                    -> extrair Dots, Concepts, MOCs e possiveis Efforts
                    -> se houver implementacao:
                       -> testar codigo/metodo
                       -> marcar @code-tested
                       -> vincular a Paper Note se couber
```

---

## 2. As três camadas

### TO LOOK
> "Por que peguei este artigo?"

**Tempo investido:** 2-5 min (título + abstract apenas)
**Ferramenta:** Zotero
**Decisão:** salvar ou descartar

**Inclusão: salvar se ao menos 1 trigger for verdadeiro**

- Título contém keyword ativa do seu trabalho.
- Domínio do problema alinhado ao que você está estudando agora.
- Autor ou journal está na sua lista monitorada.
- O artigo foi citado por uma referência que você já estuda em profundidade.
- O artigo apareceu em busca com termo que você definiu e quer monitorar.

**Trigger adicional para artigos de revisão**

- Um bom review pode te entregar dezenas de referências filtradas. Salve mesmo quando o subtópico ainda estiver periférico.
- Aplique `@needs-reread` se a revisão tiver mais de 5 anos em subáreas que evoluem rápido, como ML, PINNs e métodos probabilísticos.
- Se ainda não souber o subtipo da revisão, trate o item como `source_type: review-paper` e refine o subtipo depois em `method_tags`.

**Saída ao descartar**

- Sem literature note.
- O artigo fica apenas no Zotero, sem tags ou com `!discarded` se você quiser registrar volume de triagem.

**Tags mínimas no Zotero**

- Obrigatória: `@look` + ao menos 1 `#topic`
- Opcional: `!seminal`

---

### TO REVIEW
> "Vale construir isso na minha base de conhecimento?"

**Tempo investido:** 10-15 min (abstract + intro + conclusão)
**Ferramenta:** Zotero + Obsidian
**Decisão:** criar nota e classificar, ou manter só em `TO LOOK`

**Gate de avanço: criar literature note se score >= 3/6**

| #   | Critério                                                            | Sim / Não |
| --- | ------------------------------------------------------------------- | --------- |
| 1   | Relevância direta ao meu trabalho atual                             |           |
| 2   | Metodologia identificável e comparável                              |           |
| 3   | Recência (<= 10 anos ou seminal/clássico)                           |           |
| 4   | Credibilidade dos autores (h-index > 15 em geomecânica ou ISRM/SPE) |           |
| 5   | Sinaliza um gap que eu posso explorar                               |           |
| 6   | Consigo escrever a frase que eu citaria                             |           |

**Score:** ___ / 6

**Teste prático do critério 6**

Escreva agora, em uma frase, como você citaria este artigo. Se não conseguir, o artigo não passou de verdade.

**Quando o item for uma revisão**

- O critério 2 vira: a estratégia de busca é explícita? Os critérios de inclusão e exclusão estão declarados?
- Revisão narrativa sem estratégia de busca declarada é útil, mas deve ser marcada com cautela, por exemplo em `quality_tags` com `!weak-methods`.
- O critério 6 também pode ser satisfeito de dois modos:
  - "Vou citar no background"
  - "Vou usar para minerar referências e alimentar `TO LOOK`"

**O que preencher na literature note neste estágio**

- `Capture Trigger`
- `Structural Check`
- `Abstract Critique`

**Tags aplicadas**

- `@review`
- ao menos 1 `%method`
- ao menos 1 `$use-tag` quando houver utilidade clara

**Importante**

Artigos que ficam em `TO REVIEW` sem avançar continuam valendo como nota. A nota registra por que o item não mereceu aprofundamento e treina seu critério ao longo do tempo.

---

### TO DIG
> "Preciso estudar este artigo completamente e implementar, criticar ou reaproveitar seu método."

**Tempo investido:** 1-4+ horas
**Ferramenta:** Zotero PDF + Obsidian
**Decisão:** avançar apenas se todos os 5 critérios forem verdadeiros

**Gate de avanço: todos obrigatórios**

| #   | Critério (paper original)                                                | Critério (review paper)                                           | Sim / Não |
| --- | ------------------------------------------------------------------------ | ----------------------------------------------------------------- | --------- |
| 1   | Método novo que eu ainda não tenho no toolkit                            | Define o estado da arte de um subtópico em que estou trabalhando? |           |
| 2   | Equações, parâmetros e condições explícitos o suficiente para reproduzir | A síntese identifica gaps explícitos e acionáveis?                |           |
| 3   | Resultados validados contra solução analítica, experimento ou campo      | A seleção de papers é criteriosa? O risco de viés é declarado?    |           |
| 4   | Aplicável ao meu domínio sem re-adaptação conceitual maior               | Posso minerar as referências para alimentar `TO LOOK`?            |           |
| 5   | Implementar ou criticar este trabalho gera seção no meu paper            | Este review me posiciona para extensão, recorte ou refutação?     |           |

**O que preencher na literature note neste estágio**

- `Deep Reading` completo
- `Selecao manual a partir do Zotero`
- seção de implementação ou de saídas para o sistema

**Quando o item for uma revisão**

- O diagrama de método vira um **mapa de cobertura**.
- Depois da síntese principal, percorra a bibliografia do review e envie para `TO LOOK` os artigos ainda não capturados.
- Documente o capture trigger como: `Citado por: [citekey do review]`.

**Convenção de highlights no Zotero PDF**

| Cor      | Hex       | Usar para                             |
| -------- | --------- | ------------------------------------- |
| Amarelo  | `#ffd400` | Achados principais                    |
| Vermelho | `#ff6666` | Críticas, limitações, fraquezas       |
| Azul     | `#5b9bd5` | Método, equações, formulação          |
| Verde    | `#5fb236` | Frases citáveis no paper              |
| Cinza    | `#7f8c8d` | Observações neutras, apoio e contexto |
| Roxo     | `#a66dd4` | Dúvidas, confusões e perguntas        |
| Laranja  | `#f39c12` | Definições, fontes e referências      |
| Magenta  | `#d2527f` | Diversos / sem destino imediato       |

**Separação entre as duas notas**

- `Atlas/Literature/Zotero/{{citekey}}.md` = nota-fonte com abstract, PDF, highlights, comentários e `block-id` por annotation.
- `Atlas/Literature/Zotero/{{citekey}} - Literature.md` = nota interpretativa com protocolo, crítica, integração com MOCs/Efforts e links manuais para trechos da nota Zotero.
- A literature note não deve duplicar automaticamente highlights do Zotero.

**Tags aplicadas**

- `@dig`
- `@annotated` após leitura completa
- `@code-tested` após implementação testada

---

## 3. Taxonomia de tags

Tags são o segundo eixo de organização. O primeiro são as coleções do Zotero e os tipos do vault.

### `@` - Estágio do protocolo

| Tag             | Quando aplicar                        |
| --------------- | ------------------------------------- |
| `@look`         | Capturado, ainda não triado           |
| `@review`       | Passou pela triagem inicial           |
| `@dig`          | Selecionado para leitura profunda     |
| `@annotated`    | Leitura completa com highlights úteis |
| `@code-tested`  | Método implementado e testado         |
| `@needs-reread` | Precisa de releitura                  |

### `#` - Tópico geomecânico

**Mecânica das rochas**

| Tag                    | Descrição                                  |
| ---------------------- | ------------------------------------------ |
| `#rock-mechanics`      | Tópico geral                               |
| `#rock-strength`       | Resistência, ensaios, critérios de ruptura |
| `#failure-criteria`    | Mohr-Coulomb, Hoek-Brown, Drucker-Prager   |
| `#constitutive-models` | Modelos elasto-plásticos, viscoelásticos   |
| `#rock-deformation`    | Compressibilidade, módulos elásticos       |

**Caracterização probabilística de solos**

| Tag                           | Descrição                                      |
| ----------------------------- | ---------------------------------------------- |
| `#prob-soil-characterization` | Tópico geral                                   |
| `#bayesian-inference`         | Inferência bayesiana em parâmetros geotécnicos |
| `#bayesian-updating`          | Atualização com dados de campo e ensaio        |
| `#generative-models`          | GANs, VAEs e modelos generativos               |
| `#dictionary-learning`        | Sparse representation e dicionários            |
| `#PINNs-geomech`              | PINNs em geomecânica                           |
| `#uncertainty-quantification` | Quantificação de incerteza                     |
| `#spatial-variability`        | Variabilidade espacial e Kriging               |
| `#random-fields`              | Campos aleatórios                              |

**Classificação de solos com métodos avançados**

| Tag                             | Descrição                      |
| ------------------------------- | ------------------------------ |
| `#soil-classification`          | Tópico geral                   |
| `#ML-classification`            | ML supervisionado              |
| `#deep-learning-geotech`        | Deep learning aplicado a solos |
| `#probabilistic-classification` | Saída probabilística           |
| `#CPT-classification`           | Baseada em CPT/CPTu            |
| `#SPT-classification`           | Baseada em SPT                 |
| `#transfer-learning`            | Transfer learning              |

**Confiabilidade estrutural**

| Tag                       | Descrição                            |
| ------------------------- | ------------------------------------ |
| `#structural-reliability` | Tópico geral                         |
| `#Monte-Carlo`            | Simulação de Monte Carlo             |
| `#FORM-SORM`              | Métodos FORM e SORM                  |
| `#Markov-Chain`           | Cadeias de Markov                    |
| `#MCMC`                   | Markov Chain Monte Carlo             |
| `#failure-probability`    | Probabilidade de falha e índice beta |
| `#fragility-curves`       | Curvas de fragilidade                |
| `#sensitivity-analysis`   | Sensibilidade global                 |
| `#limit-state`            | Estado limite                        |

**Perfuração e poço**

| Tag                   | Descrição                           |
| --------------------- | ----------------------------------- |
| `#wellbore-stability` | Estabilidade de poço                |
| `#drilling-geomech`   | Geomecânica aplicada à perfuração   |
| `#mud-weight`         | Janela operacional de lama          |
| `#borehole-failure`   | Breakout, tensile fracture, colapso |

**Produção e integridade**

| Tag                     | Descrição                 |
| ----------------------- | ------------------------- |
| `#sand-production`      | Sanding                   |
| `#fault-reactivation`   | Reativação de falhas      |
| `#induced-seismicity`   | Sismicidade induzida      |
| `#structural-integrity` | Integridade de estruturas |

**Análise de tensões**

| Tag                    | Descrição                       |
| ---------------------- | ------------------------------- |
| `#structural-analysis` | Análise estrutural              |
| `#stress-state`        | Tensões in situ                 |
| `#stress-path`         | Trajetória de tensões           |
| `#overburden`          | Sobrecarga e densidade de rocha |

### `%` - Método / abordagem

| Tag                  | Descrição             |
| -------------------- | --------------------- |
| `%analytical`        | Solução fechada       |
| `%semi-analytical`   | Aproximação analítica |
| `%FEM`               | Elementos finitos     |
| `%FDM`               | Diferenças finitas    |
| `%DEM`               | Elementos discretos   |
| `%BEM`               | Elementos de contorno |
| `%experimental`      | Ensaios laboratoriais |
| `%field-data`        | Dados de campo        |
| `%case-study`        | Estudo de caso        |
| `%empirical`         | Correlações empíricas |
| `%machine-learning`  | ML/AI aplicado        |
| `%narrative-review`  | Revisão narrativa     |
| `%systematic-review` | Revisão sistemática   |
| `%scoping-review`    | Scoping review        |
| `%meta-analysis`     | Meta-análise          |

**Software - complemento ao método**

Use em conjunto com a tag de método correspondente. Exemplo: `%FEM` + `%abaqus`.

| Tag            | Descrição              |
| -------------- | ---------------------- |
| `%abaqus`      | Abaqus                 |
| `%ansys`       | ANSYS                  |
| `%plaxis`      | PLAXIS                 |
| `%flac`        | FLAC / FLAC3D          |
| `%pfc`         | PFC                    |
| `%opensees`    | OpenSees               |
| `%comsol`      | COMSOL                 |
| `%matlab`      | MATLAB                 |
| `%python-sci`  | Python científico      |
| `%opengeomech` | OpenGeoSys / similares |
| `%rocscience`  | Suite Rocscience       |

### `$` - Uso no paper

| Tag             | Onde entra              | Quando atribuir                      |
| --------------- | ----------------------- | ------------------------------------ |
| `$background`   | Introdução / background | Em `TO REVIEW` se sustenta contexto  |
| `$gap-signal`   | Introdução / motivação  | Em `TO REVIEW` se aponta lacuna útil |
| `$methods-cite` | Métodos                 | Em `TO DIG` ao diagramar o método    |
| `$discussion`   | Discussão               | Em `TO DIG` após ler resultados      |
| `$extend`       | Trabalhos futuros       | Em `TO DIG` se abre extensão         |
| `$paper-01`     | Paper 01                | Ao vincular a um manuscrito          |
| `$paper-02`     | Paper 02                | Ao vincular a um manuscrito          |

### `!` - Qualidade e alertas

| Tag               | Critério                           |
| ----------------- | ---------------------------------- |
| `!seminal`        | Referência fundacional             |
| `!high-impact`    | Journal Q1 ou alta citação         |
| `!weak-methods`   | Método fraco ou pouco transparente |
| `!conflicting`    | Conflita com outro paper relevante |
| `!data-available` | Dataset público disponível         |

---

## 4. Regra de aplicação de tags por estágio

| Momento                     | Tags obrigatórias                | Tags opcionais                           |
| --------------------------- | -------------------------------- | ---------------------------------------- |
| Captura (`TO LOOK`)         | `@look` + >= 1 `#topic`          | `!seminal`                               |
| Triagem (`TO REVIEW`)       | `@review` + `#topic` + `%method` | `$background`, `$gap-signal`, `!quality` |
| Leitura profunda (`TO DIG`) | `@dig` + `$use-tags`             | `@annotated`                             |
| Implementação               | `@code-tested`                   | `$extend`                                |
| Vínculo com paper           | `$paper-XX`                      | Todos os `$` relevantes                  |

### Nota sobre sobreposição metodológica

Caracterização probabilística de solos, classificação de solos e confiabilidade estrutural compartilham métodos. Quando um paper cruzar domínios, aplique tags dos dois blocos sem medo.

Exemplos:

| Situação                                          | Tags recomendadas                                                                   |
| ------------------------------------------------- | ----------------------------------------------------------------------------------- |
| MCMC para inferência de parâmetros de solo        | `#prob-soil-characterization` + `#MCMC` + `#bayesian-inference`                     |
| Confiabilidade com classificação bayesiana        | `#structural-reliability` + `#probabilistic-classification` + `#bayesian-inference` |
| PINN para quantificar incerteza em confiabilidade | `#PINNs-geomech` + `#uncertainty-quantification` + `#structural-reliability`        |
| Dictionary learning para classificação de CPT     | `#dictionary-learning` + `#CPT-classification` + `#soil-classification`             |

> Sobreposição de tags não é redundância. É o que permite filtros cruzados realmente úteis.

---

## 5. Estrutura Zotero

```text
My Library
- Look
- Review
- Dig
- Papers
  - Paper_01_[Titulo]
  - Paper_02_[Titulo]
  - Paper_03_[Titulo]
```

**Regras**

- Um artigo pode existir simultaneamente em `Dig` e em uma coleção de paper, sem duplicação.
- Coleções representam estágio de leitura e vínculo com paper.
- Tags representam assunto, método, qualidade e uso.

---

## 6. Estrutura Obsidian no vault atual

```text
ChrisVault4.0/
- x/Templates/
  - LiteratureProtocolTemplate.md
  - ConceptTemplate.md
  - PaperTemplate.md
- Atlas/Literature/
- Atlas/Concepts/
- Atlas/Papers/
- Atlas/Maps/
```

**Regras**

- `TO LOOK` fica só no Zotero.
- `TO REVIEW` e `TO DIG` usam duas notas complementares, ambas em `Atlas/Literature/Zotero/`:
  - `{{citekey}}.md` para o bruto importado
  - `{{citekey}} - Literature.md` para a leitura trabalhada
- Saída mínima de uma leitura relevante: síntese + Dot ou update de MOC.
- Conceitos técnicos recorrentes sobem para `Atlas/Concepts/`.
- Artigos que já servem diretamente a manuscritos alimentam `Atlas/Papers/`.

---

## 7. Plugins necessários

| Onde     | Plugin             | Função                        |
| -------- | ------------------ | ----------------------------- |
| Zotero   | Better BibTeX      | Citekeys estáveis             |
| Zotero   | PDF nativo (v7+)   | Highlights exportáveis        |
| Obsidian | Zotero Integration | Importa metadados e anotações |
| Obsidian | Templater          | Renderiza templates           |

> Zotero 8+: use Zotero Integration diretamente.

---

## 8. Checklist de revisão do protocolo

- [ ] A taxonomy de `#topics` ainda reflete meus temas ativos?
- [ ] Os journals monitorados continuam relevantes?
- [ ] O percentual de artigos que chega a `TO DIG` está entre 5% e 10%?
- [ ] Os artigos em `TO REVIEW` estão sendo usados nos papers?
- [ ] As revisões estão gerando mineração útil de referências para `TO LOOK`?
- [ ] Existem concepts ou dots criados sem backlinks nem reaproveitamento?

---

## 9. Notas de versão

| Versão | Data | Mudança |
|--------|------|---------|
| 1.0 | Mar 2026 | Versão inicial: protocolo Look / Review / Dig |
| 1.1 | Mar 2026 | Atualização da taxonomy com novos temas ativos |
| 1.2 | Mar 2026 | Ajuste da taxonomy e nota de sobreposição metodológica |
| 1.3 | Mar 2026 | Inclusão do sub-bloco de softwares como complemento ao método |
| 1.4 | Mar 2026 | Inclusão do ramo para review papers: triggers em TO LOOK, critérios alternativos em TO REVIEW e TO DIG, mapa de cobertura e mineração de referências |
