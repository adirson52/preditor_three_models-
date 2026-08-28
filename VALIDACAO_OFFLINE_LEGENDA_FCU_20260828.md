# Validação offline — legenda, QML, prioridades e FCUs

Data: 28/08/2026

## Escopo

- somente pacote offline em `http://127.0.0.1:8767/index.html`;
- nenhuma publicação Vercel realizada nesta revisão;
- legenda no layout `Estilo QML`, `Prioridade do modelo` e `FCU`;
- ranking QML com 50 tons por `ranking_total`;
- filtros independentes em zoom afastado e aproximado;
- FCUs interativas com prioridade de clique sobre a célula;
- pontos e FCUs suavizados progressivamente conforme o zoom.

## Legenda reconstruída

- controle organizado somente em `Estilo QML`, `Prioridade do modelo` e `FCU`;
- as seis linhas são botões nativos com `role="switch"` e `aria-checked`;
- o estado permanece estável após a atualização visual da legenda;
- `ranking QML` controla somente a camada QML única;
- atenção prioritária, atenção e demais áreas controlam somente as subcamadas de `Prioridade do modelo`;
- os dois conjuntos são independentes e nenhum botão religa ou desliga o outro;
- a linha desligada é indicada por fundo/opacidade e ponto de estado, sem texto adicional e sem riscar o nome.

## QML e filtros

- 3.774.138 células processadas em cada zoom de 6 a 11;
- 367.581 células de atenção prioritária;
- 110.741 células de atenção;
- 3.295.816 células em demais áreas;
- 50 cores QML distintas confirmadas no zoom 6;
- camada QML unificada gerada em `overview_qml`;
- prioridade categórica separada em `overview_action_classes/priority` e `overview_action_classes/attention`;
- demais áreas permanece como subcamada lógica transparente;
- zooms 6–9: ponto de 1 pixel;
- zooms 10–11: marcador compacto em cruz de 5 pixels;
- zoom 12 ou superior: raio próximo original preservado;
- fatores de opacidade da visão geral: 0,50; 0,58; 0,66; 0,75; 0,86; 1,00 nos zooms 6 a 11;
- os 50 tons e as duas faixas QML foram confirmados em todos os zooms;
- em Salvador, no zoom 11, QML, prioridade e atenção carregaram 6 tiles cada, sem falhas.

## Independência das camadas

- zoom 13, camadas simultâneas:
  - QML: 205.966 pixels;
  - atenção prioritária: 190.575 pixels;
  - atenção: 48.143 pixels;
  - demais áreas: 0 pixels, por definição transparente;
- ao desligar somente o QML, seu canvas ficou com 0 pixels e prioridade/atenção permaneceram em 190.575/48.143;
- ao religar o QML e desligar somente atenção prioritária, o QML permaneceu com 205.966 pixels, atenção com 48.143 e prioritária ficou em 0;
- zoom 11: 6 tiles QML, 6 tiles de atenção prioritária e 6 tiles de atenção carregados simultaneamente;
- ao desligar somente o QML no zoom 11, os 12 tiles categóricos permaneceram;
- ao desligar somente atenção prioritária, permaneceram 6 tiles QML e 6 tiles de atenção.

## FCUs

- Salvador carregou 400 polígonos, todos classificados como FCU Tipo 1 na base atual;
- Curitiba foi usada para testar os dois tipos: 601 polígonos Tipo 1 e 34 polígonos Tipo 2;
- ao desligar um tipo, seus polígonos recebem `pointer-events: none` e não bloqueiam a célula;
- a FCU é desenhada uma única vez pela camada vetorial interativa; canvas e camada-base duplicados foram removidos;
- contorno e preenchimento das FCUs ficam progressivamente mais leves nos zooms 9, 10 e 11;
- o estilo próximo original é preservado a partir do zoom 12;
- ao desligar ambos, a camada vetorial de status é removida do mapa;
- ao ligar um tipo, somente seus polígonos voltam a receber o clique.

## Testes reais de clique

- FCU Tipo 2 `Jardim São Vicente`, Curitiba:
  - com somente Tipo 2 ligado, 34 polígonos ficaram visíveis e interativos;
  - o popup exibiu nome, ID, código, tipo, baixa evidência, médias do modelo, área de estudo, município e número de células;
- FCU Tipo 1 `Monte Santo`, Curitiba:
  - com somente Tipo 1 ligado, 601 polígonos ficaram visíveis e interativos;
  - o popup territorial abriu com o resultado `FCU tipo 1` e os demais atributos esperados.

## Estado entregue

- Salvador restaurado;
- ranking QML ligado;
- atenção prioritária ligada;
- atenção ligada;
- demais áreas desligada;
- FCU Tipo 1 ligada;
- FCU Tipo 2 ligada;
- console sem erros de página durante a validação funcional;
- `mapa_3d_real.html` respondeu HTTP 200, abriu com canvas MapLibre e carregou os filtros das classes e das duas FCUs sem erro de página.

## Validação reproduzível

Execute `python tools/validar_overview_qml.py` para conferir contagens, 50 cores, opacidades e ocupação dos PNGs em todos os zooms da visão geral.
