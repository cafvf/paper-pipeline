# Exemplos de Reescrita de Efforts

Este documento reúne 10 notas reais do vault que valem como referência para reescrita.

Critério de escolha:

- alta centralidade no portfólio atual;
- diversidade de tipos de effort;
- potencial de melhorar o `projects.jsonl`;
- utilidade como modelo para outras notas.

Princípio geral: não é necessário reescrever tudo. O maior ganho vem de:

- manter um título real e estável;
- declarar `Objetivo`, `Como fazer`, `Lacunas` e `Entregas / Outputs`;
- separar backlog de contexto;
- deixar a `Próxima ação` executável;
- evitar headings genéricos ou templates não apagados.

## 1. Artigo 3D SBL e GPR

Arquivo real: `Efforts/On/Artigo 3D SBL e GPR.md`

Por que é modelo:

- é um paper candidate ativo;
- já tem escopo, entrega e histórico ricos;
- só precisa de mais separação entre objetivo, plano e backlog.

Reescrita sugerida:

```md
# Artigo 3D SBL e GPR

## 🎯 Objetivo
- Finalizar e submeter um artigo sobre modelagem 3D de `S_u` com SBL e GPR em dados offshore brasileiros.
- O foco imediato é fechar a análise probabilística de capacidade de carga e consolidar a narrativa final do paper.

## Como fazer
- Revisar a estrutura do artigo e reduzir o texto para um escopo publicável.
- Finalizar a seção de capacidade de carga e sua interpretação probabilística.
- Consolidar as comparações entre GPR, SBL, krigagem e metodologia BR.
- Fechar conclusão, fluxograma e nota sobre IA/disponibilização de dados.

## Lacunas
- Falta fechar o estudo estatístico das capacidades de carga.
- Falta decidir o recorte final para manter o artigo com tamanho defensável.
- Falta revisão final antes do envio aos coautores e ao periódico.

## 📤 Entregas / Outputs
- Manuscrito final revisado.
- Figuras finais e fluxograma do artigo.
- Submissão a periódico-alvo.

## Próxima ação
- Fechar a seção de estudo estatístico das capacidades de carga e decidir o corte final do artigo.

## Backlog relacionado
- Revisar conclusão.
- Revisar aviso sobre IA e disponibilização de dados.
- Melhorar fluxograma.

## Log de progresso
- Manter apenas marcos que mudam o estado do trabalho.
```

## 2. Bayes Lote 1 - Likelihood, Priors Conjugadas e Modelo Normal

Arquivo real: `Efforts/On/Bayes Lote 1 - Likelihood, Priors Conjugadas e Modelo Normal.md`

Por que é modelo:

- já está perto de um formato bom;
- serve como padrão para study cycles curtos;
- precisa só alinhar headings ao contrato do scanner.

Reescrita sugerida:

```md
# Bayes Lote 1 - Likelihood, Priors Conjugadas e Modelo Normal

## 🎯 Objetivo
- Construir a base mínima de inferência Bayesiana necessária para avançar nas frentes probabilísticas do portfólio.

## Como fazer
- Estudar likelihood e posterior em um exemplo pequeno.
- Montar um caso Normal-Normal com prior conjugada.
- Implementar um notebook Python mínimo e reproduzível.
- Registrar a interpretação de prior, likelihood, posterior e posterior predictive.

## Lacunas
- Falta transformar o estudo em uma nota conceitual consolidada.
- Falta verificar por simulação o resultado analítico do exemplo.
- Falta explicitar os próximos lotes de estudo derivados.

## 📤 Entregas / Outputs
- Nota conceitual sobre likelihood e posterior.
- Exemplo Normal-Normal resolvido.
- Notebook mínimo reproduzível.

## Próxima ação
- Implementar o exemplo Normal-Normal com solução analítica e checagem por simulação.
```

## 3. Sest-Solos

Arquivo real: `Efforts/Ongoing/Sest-Solos.md`

Por que é modelo:

- é hub operacional central;
- hoje está muito próximo de um quadro de backlog;
- precisa deixar claro objetivo, frentes e critérios de priorização.

Reescrita sugerida:

```md
# Sest-Solos

## 🎯 Objetivo
- Coordenar a evolução do Sest-Solos como plataforma aplicada de geotecnia, sustentando demandas da Petrobras e frentes de pesquisa derivadas.

## Como fazer
- Priorizar abas e funcionalidades em execução neste ciclo.
- Manter separação entre entregas de produto, refatoração e P&D associado.
- Usar efforts filhos para cada frente executável e evitar concentrar detalhe operacional neste hub.

## Lacunas
- Falta definir claramente quais abas estão ativas neste ciclo.
- Falta separar backlog estrutural de backlog de pesquisa.
- Falta registrar critérios de prioridade entre demandas operacionais e P&D.

## 📤 Entregas / Outputs
- Funcionalidades entregues no Sest-Solos.
- Backlog priorizado por ciclo.
- Lista clara de efforts filhos ativos.

## Próxima ação
- Definir quais abas e refatorações entram no ciclo atual e mover o restante para backlog explícito.

## Child efforts ativos
- [[Aba de Classificação]]
- [[Aba de Adensamento Térmico]]

## Backlog estratégico
- Incertezas na krigagem.
- Cravabilidade.
- P&D ligado a artigos e benchmarks.
```

## 4. Caracterização Probabilistica de Solos

Arquivo real: `Efforts/Ongoing/Caracterização Probabilistica de Solos.md`

Por que é modelo:

- é hub de pesquisa estruturante;
- hoje mistura headings genéricos com headings semânticos;
- precisa virar um hub limpo e legível para máquina.

Reescrita sugerida:

```md
# Caracterização Probabilistica de Solos

## 🎯 Objetivo
- Organizar a linha de pesquisa de caracterização probabilística de solos, integrando formulação, benchmark, implementação e aplicação em engenharia.

## Como fazer
- Consolidar os esforços de modelagem 1D, 2D e 3D.
- Estruturar a ponte entre caracterização probabilística e confiabilidade.
- Usar efforts filhos para artigos, ports e benchmarks específicos.

## Lacunas
- Falta definir melhor o horizonte desta frente e seus limites.
- Falta consolidar benchmarks e formulações mínimas antes de abrir novas subfrentes.
- Falta transformar o backlog longo em child efforts mais nítidos.

## 📤 Entregas / Outputs
- Arcabouço teórico e prático de caracterização probabilística de solos.
- Artigo sobre GPR e SBL publicado.
- Ports relevantes de Matlab para Python.

## Próxima ação
- Consolidar filhos imediatos e benchmarks da frente antes de abrir novas linhas.

## Child efforts prioritários
- [[Artigo 3D SBL e GPR]]
- [[Conversão SBL 3D Python]]
- [[Conversão GPR 3D Python]]
```

## 5. Aba de Classificação

Arquivo real: `Efforts/Ongoing/Aba de Classificação.md`

Por que é modelo:

- representa bem um effort operacional;
- o conteúdo está bom, mas ainda carrega texto de template;
- é excelente padrão para entregas de software com homologação.

Reescrita sugerida:

```md
# Aba de Classificação

## 🎯 Objetivo
- Entregar uma aba de classificação de solos baseada em CPTu dentro do Sest-Solos.

## Como fazer
- Implementar os ábacos de Robertson por furo.
- Consolidar visualizações por profundidade.
- Fechar exportações e documentação da aba.
- Validar a solução com o time da BR.

## Lacunas
- Falta homologação final.
- Falta fechar exportações dos cálculos.
- Falta consolidar a documentação funcional da aba.

## 📤 Entregas / Outputs
- Aba de classificação funcional no Sest-Solos.
- Exportações dos cálculos da aba.
- Documentação mínima de uso e validação.

## Próxima ação
- Validar os ábacos e gráficos com o Edge e fechar a exportação dos limites de camada.

## Bloqueios / Dependências
- Revisão e validação do Edge.
```

## 6. Conversão GPR 3D Python

Arquivo real: `Efforts/Ongoing/Conversão GPR 3D Python.md`

Por que é modelo:

- é um effort de implementação técnica;
- o template ainda está muito visível;
- precisa alinhar nome, escopo e DoD.

Reescrita sugerida:

```md
# Conversão GPR 3D Python

## 🎯 Objetivo
- Portar a modelagem 3D em GPR para Python de forma reproduzível e útil para o artigo e para a linha de caracterização probabilística.

## Como fazer
- Revisar a função de verossimilhança usada no código original.
- Portar a lógica principal para Python com organização modular.
- Documentar os blocos centrais do algoritmo e o fluxo de execução.
- Preparar exemplos mínimos para validação.

## Lacunas
- Falta fechar o entendimento formal da verossimilhança.
- Falta validar o port contra resultados conhecidos.
- Falta registrar o desenho do código e sua documentação mínima.

## 📤 Entregas / Outputs
- Código GPR 3D operante em Python.
- Documentação técnica do port.
- Exemplo mínimo de validação.

## Próxima ação
- Estudar e documentar a função de verossimilhança usada no código original.
```

## 7. Classificação Robertson

Arquivo real: `Efforts/Ongoing/Classificação Robertson.md`

Por que é modelo:

- é uma ponte entre software, benchmark e documentação;
- já tem um escopo quase pronto;
- precisa ganhar um título explícito e uma seção de lacunas mais clara.

Reescrita sugerida:

```md
# Classificação Robertson

## 🎯 Objetivo
- Estruturar a classificação de Robertson como benchmark computacional e base documental para uso em CPTu.

## Como fazer
- Implementar numericamente os quatro ábacos.
- Consolidar visualizações e normalizações.
- Montar a documentação técnica no Atlas.
- Usar o resultado como baseline para extensões probabilísticas.

## Lacunas
- Falta completar os ábacos restantes.
- Falta incorporar classificação USCS e revisão de literatura complementar.
- Falta transformar o material em documentação consolidada e benchmark reusável.

## 📤 Entregas / Outputs
- Conjunto de classes para classificação de Robertson.
- Visualizações associadas.
- Nota/Atlas explicando parâmetros, fronteiras e implicações.

## Próxima ação
- Inserir os outros ábacos de Robertson nas classes já criadas.
```

## 8. Análise Probabilística de Projeto de Fundação de Poço

Arquivo real: `Efforts/Simmering/Análise Probabilística de Projeto de Fundação de Poço.md`

Por que é modelo:

- é uma frente estratégica forte de F2;
- hoje está mais como visão de programa do que como effort legível;
- precisa ser escrita como hub embrionário ou programa em espera.

Reescrita sugerida:

```md
# Análise Probabilística de Projeto de Fundação de Poço

## 🎯 Objetivo
- Estruturar a frente de confiabilidade aplicada ao projeto de fundação de poço, integrando incerteza geotécnica e resposta estrutural.

## Como fazer
- Revisar a interface com o Simcon.
- Identificar as variáveis aleatórias prioritárias do problema.
- Definir um caso-base de confiabilidade estrutural para validação inicial.
- Preparar a ponte com a frente de caracterização probabilística de solos.

## Lacunas
- Falta uma formulação mínima do caso-base.
- Falta revisar o código já existente e sua compatibilidade com o Simcon atual.
- Falta explicitar a primeira pergunta publicável da frente.

## 📤 Entregas / Outputs
- Código de avaliação de probabilidade de falha ou índice de confiabilidade.
- Integração inicial com o Simcon.
- Definição do primeiro caso-base publicável.

## Próxima ação
- Revisar o código existente e mapear a interface mínima de input/output com o Simcon.
```

## 9. CPTu Probabilístico, Estratigrafia e Interpretação sob Incerteza

Arquivo real: `Efforts/Simmering/CPTu Probabilístico, Estratigrafia e Interpretação sob Incerteza.md`

Por que é modelo:

- é um hub sofisticado e importante;
- já está rico conceitualmente;
- precisa só de um resumo operacional mais curto no topo.

Reescrita sugerida:

```md
# CPTu Probabilístico, Estratigrafia e Interpretação sob Incerteza

## 🎯 Objetivo
- Consolidar a frente F1 do portfólio: interpretação probabilística de CPTu, estratigrafia e classificação sob incerteza.

## Como fazer
- Usar [[Classificação Robertson]], [[Caracterização Probabilistica de Solos]] e [[Modelagem por Krigagem]] como antecedentes diretos.
- Abrir trabalhos publicáveis apenas quando houver benchmark, dados mínimos e janela real de execução.
- Manter a sequência canônica da frente explícita.

## Lacunas
- Falta promover um primeiro child effort publicável da F1.
- Falta consolidar benchmark mínimo e formulação mínima do trabalho `1.1`.
- Falta manter o hub enxuto, deixando detalhes extensos em anexos ou notas-filhas.

## 📤 Entregas / Outputs
- Sequência canônica da F1.
- Critério claro para abertura de child efforts.
- Mapa de trabalhos publicáveis e benchmarks mínimos.

## Próxima ação
- Consolidar Robertson, validação geológica e formulação mínima antes de promover o primeiro child effort da frente.

## Anexos estratégicos
- Sequência canônica.
- Mini-fichas dos trabalhos `1.1` a `1.7`.
- Bifurcações metodológicas da frente.
```

Observação: esta nota já está boa. O ajuste principal é de forma, não de conteúdo.

## 10. Roadmap do Portfólio de Pesquisa

Arquivo real: `Efforts/Simmering/Roadmap do Portfólio de Pesquisa.md`

Por que é modelo:

- é o melhor exemplo de documento estruturante;
- já conversa bem com o scanner;
- serve como padrão para roadmaps e documentos-mestre.

Reescrita sugerida:

```md
# Roadmap do Portfólio de Pesquisa

## Finalidade do documento
Organizar o portfólio de pesquisa em uma sequência canônica por frente, conectando planejamento, posicionamento científico, produção e submissão.

## Pergunta central
Como transformar dados geotécnicos offshore limitados e indiretos, em especial CPTu, em inferência útil, modelagem confiável e decisão de engenharia sob incerteza?

## Eixos metodológicos recorrentes
- inferência Bayesiana
- propagação de incerteza
- seleção e comparação de modelos
- random fields e variabilidade espacial
- completação de dados e baixo posto
- discrepância de modelo

## Outcome
- Convenção única de sequenciamento do portfólio para F1 e F2.

## Lacunas
- Falta materializar novas frentes apenas quando os antecedentes diretos estiverem maduros.
- Falta manter alinhamento entre roadmap, matriz e acompanhamento.

## Próxima ação
- Usar este documento como referência interna de F1/F2 sem duplicar o mapa estratégico do Efforts.
```

Observação: aqui a reescrita é mínima. Esta nota já é uma boa referência de estrutura semântica.

## Padrões que mais melhoram o scanner

- use `# Título real da nota`, não `# Objetivo` ou `# Como fazer?`;
- prefira `## 🎯 Objetivo`, `## Como fazer`, `## Lacunas`, `## 📤 Entregas / Outputs`;
- para roadmap/hub estratégico, prefira `## Finalidade do documento`, `## Pergunta central`, `## Eixos metodológicos recorrentes`, `## Outcome`;
- remova texto de template antes de salvar a nota;
- mova checklists extensos para `Backlog relacionado` ou notas-filhas;
- deixe `Próxima ação` como uma ação única, concreta e executável.
