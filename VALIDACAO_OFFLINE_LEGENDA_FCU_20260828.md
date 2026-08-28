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
- reativar prioridade, atenção ou demais áreas religa automaticamente o ranking QML;
- a linha desligada é indicada por fundo/opacidade e ponto de estado, sem texto adicional e sem riscar o nome.

## QML e filtros

- 3.774.138 células processadas em cada zoom de 6 a 11;
- 367.581 células de atenção prioritária;
- 110.741 células de atenção;
- 3.295.816 células em demais áreas;
- 50 cores QML distintas confirmadas no zoom 6;
- tiles independentes gerados para `priority`, `attention` e `other`;
- zooms 6–9: ponto de 1 pixel;
- zooms 10–11: marcador compacto em cruz de 5 pixels;
- zoom 12 ou superior: raio próximo original preservado;
- fatores de opacidade da visão geral: 0,50; 0,58; 0,66; 0,75; 0,86; 1,00 nos zooms 6 a 11;
- os 50 tons e as duas faixas QML foram confirmados em todos os zooms;
- em Salvador, no zoom 11, prioridade e atenção carregaram 6 tiles cada, sem falhas;
- no zoom 13, o canvas apresentou:
  - prioridade + atenção: 205.966 pixels visíveis;
  - somente atenção: 48.040 pixels visíveis;
  - todas as classes desligadas: 0 pixels visíveis;
  - somente demais áreas: 275.322 pixels visíveis.

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
