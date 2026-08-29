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

- 3.774.138 células preservadas na base e reveladas integralmente no zoom 11;
- 367.581 células de atenção prioritária;
- 110.741 células de atenção;
- 3.295.816 células em demais áreas;
- 50 cores QML distintas confirmadas em todos os zooms de 6 a 11;
- cada área usa seu próprio `ranking_total`, de 1 até o total de células local, dividido nas 50 classes do QML;
- camada QML unificada gerada em `overview_qml`, com amostragem visual estável nos zooms afastados e todas as células no zoom 11;
- prioridade categórica separada em `overview_action_classes/priority` e `overview_action_classes/attention`;
- demais áreas permanece como subcamada lógica transparente;
- zooms 6–11: ponto de 1 pixel;
- zooms 12, 13 e 14: raios progressivos de 1,35 px, 2,15 px e 3,10 px;
- zoom 15 ou superior: raio próximo original preservado;
- divisores de amostragem nos zooms 6 a 11: 32, 16, 8, 4, 2 e 1;
- fatores de opacidade da visão geral: 0,42; 0,48; 0,56; 0,65; 0,78 e 0,92 nos zooms 6 a 11;
- os 50 tons do `estilo_revelando2608.qml` usam a mesma opacidade dentro de cada zoom; no mapa interativo, a opacidade progride de 0,72 no zoom 12 para 1 no zoom 15;
- em Salvador, no zoom 11, QML, prioridade e atenção carregaram 6 tiles cada, sem falhas.

## Validação das 11 áreas de estudo

Todas as áreas disponíveis no seletor foram abertas no navegador real após a atualização. A tabela mostra a faixa local confirmada pelo validador de dados e os mosaicos QML realmente carregados no zoom de enquadramento automático da área.

| Área | Ranking QML local | Zoom | Tiles QML | Imagens quebradas | Resultado |
|---|---:|---:|---:|---:|---|
| Belém - RGInt | 1–206.709 | 9 | 8 | 0 | OK |
| Curitiba - Conc. Urbana | 1–363.467 | 9 | 5 | 0 | OK |
| Fortaleza - Conc. Urbana | 1–257.306 | 10 | 5 | 0 | OK |
| Goiânia - Conc. Urbana | 1–306.292 | 9 | 4 | 0 | OK |
| Macapá - RGInt | 1–60.100 | 8 | 6 | 0 | OK |
| Redenção - RGInt | 1–74.553 | 7 | 6 | 0 | OK |
| Rio de Janeiro - Arranjos Populacionais | 1–101.166 | 8 | 5 | 0 | OK |
| Rio de Janeiro - Grande Conc. Urbana | 1–799.668 | 10 | 9 | 0 | OK |
| Rio de Janeiro - Médias Conc. Urbanas | 1–364.678 | 8 | 14 | 0 | OK |
| Salvador - Conc. Urbana | 1–225.164 | 11 | 6 | 0 | OK |
| São Paulo - Conc. Urbana | 1–1.015.035 | 9 | 5 | 0 | OK |

Os 11 arquivos QML derivados por área também responderam HTTP 200 no servidor offline.

Em todas as 11 áreas, desligar `ranking QML` preservou prioridade e atenção; religar o QML e desligar somente atenção prioritária preservou QML e atenção. Não houve erro de página.

O validador de dados percorreu as 3.774.138 células e confirmou, área por área, que as quantidades reais de atenção prioritária, atenção e demais áreas coincidem exatamente com os limites da escada em `ranking_rules_escada.json`.

## Independência das camadas

- nos zooms 12 a 15 de Salvador, a camada QML interativa preservou as classes do ranking local e aumentou raio e opacidade progressivamente, sem o salto visual anterior;
- o botão `ranking QML` removeu e recolocou somente a camada QML;
- prioridade e atenção permaneceram com controles próprios;
- demais áreas permaneceu com 0 pixels na camada de ação, por definição transparente;
- zoom 11: 6 tiles QML, 6 tiles de atenção prioritária e 6 tiles de atenção carregados simultaneamente;
- ao desligar somente o QML no zoom 11, os 12 tiles categóricos permaneceram;
- ao desligar somente atenção prioritária, permaneceram 6 tiles QML e 6 tiles de atenção.
- o seletor de mapa-base exibe ícone local, rótulo acessível `Escolher mapa-base` e abre as opções `Ruas` e `Satelite` sem depender da imagem ausente do Leaflet.

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

- na primeira abertura, somente o ranking QML fica ligado;
- atenção prioritária, atenção, demais áreas, FCU Tipo 1 e FCU Tipo 2 começam desligadas;
- a legenda mantém a ordem Ranking QML → Prioridade do modelo → FCU;
- após qualquer alteração, a combinação escolhida é salva no navegador e restaurada ao recarregar a página;
- persistência testada com Ranking QML + atenção prioritária + FCU Tipo 1, mantendo exatamente o mesmo estado após recarga;
- minimapa de localização aberto por padrão no canto inferior direito, com retângulo do enquadramento principal;
- minimapa sincronizado com movimento, zoom e alternância entre ruas e satélite;
- botão de recolher/abrir funcional e condição persistida após recarregar;
- console sem erros de página durante a validação funcional;
- a célula `200ME66568N98484_A_D`, em Salvador, abriu com Modelo completo, Morfologia e IBGE simultaneamente;
- `mapa_3d_real.html` foi aberto com uma célula real de cada uma das 11 áreas; em todas houve resposta válida, um canvas MapLibre, término do carregamento, ausência de sobreposição de erro e zero erros de página.

## Validação reproduzível

Execute `python tools/validar_overview_qml.py` para conferir contagens, 50 cores, opacidades e ocupação dos PNGs em todos os zooms da visão geral.

Execute `python tools/validar_camadas_areas.py` para conferir as 3.774.138 células e as quantidades de cada classe nas 11 áreas de estudo.
