# Validação offline — legenda, QML, prioridades e FCUs

Data: 28/08/2026

## Escopo

- somente pacote offline em `http://127.0.0.1:8767/index.html`;
- nenhuma publicação Vercel realizada nesta revisão;
- legenda no layout `Estilo QML`, `Prioridade do modelo` e `FCU`;
- ranking QML com 50 tons por `ranking_total`;
- filtros independentes em zoom afastado e aproximado;
- FCUs interativas com prioridade de clique sobre a célula.

## QML e filtros

- 3.774.138 células processadas em cada zoom de 6 a 11;
- 367.581 células de atenção prioritária;
- 110.741 células de atenção;
- 3.295.816 células em demais áreas;
- 50 cores QML distintas confirmadas no zoom 6;
- tiles independentes gerados para `priority`, `attention` e `other`;
- em Salvador, no zoom 11, as três classes carregaram 12 de 12 tiles, sem falhas;
- no zoom 13, o canvas apresentou:
  - prioridade + atenção: 205.966 pixels visíveis;
  - somente atenção: 48.040 pixels visíveis;
  - todas as classes desligadas: 0 pixels visíveis;
  - somente demais áreas: 275.322 pixels visíveis.

## FCUs

- Salvador carregou 400 polígonos, todos classificados como FCU Tipo 1 na base atual;
- Curitiba foi usada para testar os dois tipos: 601 polígonos Tipo 1 e 34 polígonos Tipo 2;
- ao desligar um tipo, seus polígonos recebem `pointer-events: none` e não bloqueiam a célula;
- ao desligar ambos, as camadas base, status e canvas são removidas do mapa;
- ao ligar um tipo, somente seus polígonos voltam a receber o clique.

## Testes reais de clique

- FCU Tipo 2 `Jardim São Vicente`, Curitiba:
  - com a FCU ligada, o popup territorial abriu e a célula selecionada não mudou;
  - com a FCU desligada, o mesmo clique abriu a célula `200ME54546N84960_A_A`;
- FCU Tipo 1 `Nova Vitória`, Salvador:
  - o clique abriu o popup da FCU;
  - a célula selecionada permaneceu `200ME66568N98484_A_D`;
  - o popup exibiu nome, ID, código, tipo, baixa evidência, médias do modelo, área de estudo, município e número de células.

## Estado entregue

- Salvador restaurado;
- ranking QML ligado;
- atenção prioritária ligada;
- atenção ligada;
- demais áreas desligada;
- FCU Tipo 1 ligada;
- FCU Tipo 2 ligada;
- console sem erros de página durante a validação funcional.
