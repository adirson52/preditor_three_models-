# Prompt — Dashboard Preditor FCU com ranking geral em escadas

Atualize ou reconstrua o dashboard geoespacial do Preditor FCU preservando o modelo, os dados, o tamanho atual dos pontos, a busca por célula, os links externos, o painel analítico e a visualização 3D.

## Regra de classificação

Para cada área de estudo, calcule:

- `N_total`: todas as células da área;
- `N_FCU`: células pertencentes à FCU original;
- `F = N_FCU / N_total`;
- `E`: expansão permitida pela escada.

Use esta escada:

| Percentual de FCU | Expansão total E |
|---|---:|
| Até 10% | igual ao percentual de FCU |
| Acima de 10% até 12,5% | 10% |
| Acima de 12,5% até 15% | 11% |
| Acima de 15% até 17,5% | 12% |
| Acima de 17,5% até 20% | 13% |
| Acima de 20% até 22,5% | 14% |
| Acima de 22,5% | 15% |

Limite a expansão ao restante da área: `E_final = mínimo(E, 100% - F)`.

Ordene todas as células da área pelo `ranking_total`, sem retirar as células da FCU original:

- atenção prioritária: primeiras `F + E_final/2` da área;
- atenção: faixa seguinte de `E_final/2`;
- demais áreas: restante;
- sem resultado: células sem ranking válido.

A FCU original determina as quantidades, mas não garante que uma célula FCU esteja nas faixas. A posição no ranking geral decide quais células entram.

### Comportamento obrigatório da escada

| FCU original F | Expansão E | Prioritária até | Atenção seguinte | Total destacado |
|---:|---:|---:|---:|---:|
| 5% | 5% | 7,5% | 2,5% | 10% |
| 8% | 8% | 12% | 4% | 16% |
| 10% | 10% | 15% | 5% | 20% |
| 12% | 10% | 17% | 5% | 22% |
| 14% | 11% | 19,5% | 5,5% | 25% |
| 16% | 12% | 22% | 6% | 28% |
| 18% | 13% | 24,5% | 6,5% | 31% |
| 21% | 14% | 28% | 7% | 35% |
| 25% | 15% | 32,5% | 7,5% | 40% |

Use esses nove casos como testes obrigatórios da implementação. A coluna “Prioritária até” é `F + E/2`; “Atenção seguinte” é somente a segunda metade de `E`; e “Total destacado” é `F + E`.

## Três modelos

Mostre por célula os três resultados:

- Modelo Completo;
- Modelo Morfológico;
- Modelo IBGE, correspondente ao modelo não morfológico e composto somente por informações do IBGE.

Cada modelo ordena todas as células da área pela sua própria pontuação e usa as mesmas quantidades do ranking geral:

- alto: quantidade equivalente à atenção prioritária;
- médio: quantidade equivalente à atenção;
- baixo: restante.

Em empates, ordene pelo ID da célula em ordem crescente para manter as quantidades exatas.

## FCU Tipo 1 e Tipo 2

Mantenha a situação territorial independente da classe de ação:

- fora da FCU original;
- FCU Tipo 1 — original mantida;
- FCU Tipo 2 — original em revisão.

Uma célula possui baixa evidência quando apresenta três modelos baixos ou dois modelos baixos e um médio. Uma FCU será Tipo 2 quando pelo menos 50% de suas células com resultados válidos tiverem baixa evidência. Todas as demais serão Tipo 1.

## Visualização 2D

- usar o `Ranking geral` como única visualização dos pontos, sem seletor de modo;
- implementar `ranking QML` como uma única camada, ligada e desligada pela linha correspondente dentro de `Estilo QML`;
- no Ranking geral, usar `ranking_total` calculado separadamente dentro de cada área de estudo; todas as células da área entram na própria faixa de 1 até o total local, dividida em 50 classes da mesma rampa vermelho → amarelo → verde → azul do `estilo_revelando2608.qml`;
- implementar `Prioridade do modelo` como outra camada, separada do QML, com três subcamadas: atenção prioritária, atenção e demais áreas;
- garantir independência completa: desligar o QML não altera as subcamadas de prioridade, e desligar qualquer prioridade não altera o QML;
- no Ranking geral, rankings menores são vermelhos e rankings maiores são azuis; as 50 classes usam a opacidade integral definida no arquivo `estilo_revelando2608.qml`;
- atenção prioritária: vermelho `#d7191c`;
- atenção: laranja `#f28e2b`;
- permitir ligar e desligar separadamente atenção prioritária, atenção e demais áreas no grupo `Prioridade do modelo`; demais áreas permanece transparente, mas conserva sua função lógica e de clique;
- sem resultado: transparente;
- preservar o tamanho atual dos pontos no zoom próximo e deixá-los clicáveis;
- nos zooms 6–11, renderizar cada ponto em 1 pixel;
- aplicar fatores globais de opacidade 0,42; 0,48; 0,56; 0,65; 0,78; 0,92 nos zooms 6 a 11 e manter as 50 cores do QGIS; no mapa interativo, aumentar a opacidade de 0,72 no zoom 12 para 1 no zoom 15;
- fazer o raio crescer gradualmente no mapa interativo: 1,35 px no zoom 12, 2,15 px no zoom 13, 3,10 px no zoom 14 e tamanho próximo original a partir do zoom 15;
- FCU Tipo 1: cinza-escuro com preenchimento translúcido e contorno contínuo;
- FCU Tipo 2: cinza-claro com preenchimento translúcido e contorno tracejado;
- desenhar cada FCU uma única vez em camada vetorial, sem canvas ou camada-base duplicados;
- suavizar espessura, opacidade e preenchimento das FCUs nos zooms 9, 10 e 11, preservando o estilo próximo a partir do zoom 12;
- legenda organizada somente em `Estilo QML`, `Prioridade do modelo` e `FCU`;
- quando uma FCU visível for clicada, priorizar o popup da FCU sobre o clique da célula e mostrar nome, código, identificador, tipo, município, área de estudo, número de células e estatísticas disponíveis;
- quando um tipo de FCU estiver desligado, remover sua interatividade para permitir o clique na célula abaixo;
- implementar as seis linhas da legenda como botões de alternância estáveis, com estado acessível e sem escrever “ativa/desativa” nos rótulos;
- filtros independentes para as duas dimensões;

## Painel da célula

Ao clicar em uma célula, mostre:

- ID, município e área de estudo;
- classe de ação e ranking geral;
- situação territorial e identificação da FCU, quando houver;
- Modelo Completo: alto, médio ou baixo;
- Modelo Morfológico: alto, médio ou baixo;
- Modelo IBGE: alto, médio ou baixo;
- pontuação ou probabilidade de cada modelo;
- links para Google Maps, Street View e visualização 3D.

## Visualização 3D

- manter edificações e alturas GBA;
- colorir atenção prioritária em vermelho e atenção em laranja;
- deixar demais áreas e sem resultado transparentes;
- sobrepor FCU Tipo 1 e Tipo 2 em cinza translúcido;
- preservar seleção, popup, filtros, rotação, inclinação e retorno ao mapa 2D.

## Guia de uso

- criar uma página `guia.html`, ligada ao dashboard pela aba `Guia de uso`;
- usar linguagem institucional e natural, orientada à análise territorial, sem apresentar a página como manual exclusivo de uma instituição ou equipe específica;
- organizar o conteúdo em: roteiro rápido, interpretação da legenda, regra da escada, leitura da célula, explicabilidade, orientação para decisão, imagens/3D e FAQ;
- apresentar o fluxo `área de estudo → classe de ação → concordância dos três modelos → situação FCU → imagens/3D → decisão`;
- incluir a tabela integral da escada e um simulador de F, E, limite prioritário e atenção seguinte;
- explicar que cada área possui ranking próprio e que posições brutas de áreas diferentes não são diretamente comparáveis;
- explicar que vermelho indica prioridade relativa, não confirmação;
- explicar a independência entre classe de ação e situação territorial;
- usar recortes reais do dashboard para ilustrar legenda, painel da célula, explicabilidade e 3D;
- explicar os gráficos na sequência `importância global → decomposição da célula → comparação local → curvas das variáveis`, com frases curtas e apoio visual;
- distinguir explicitamente influência global de contribuição local e deixar visível que impacto não implica causa nem confirmação territorial;
- permitir ampliar os recortes, pesquisar o FAQ e navegar de volta ao mapa;
- garantir layout limpo, responsivo, acessível por teclado e sem rolagem horizontal indevida em telas estreitas.

## Estado e qualidade das camadas do mapa

- manter a ordem da legenda: Ranking QML, Prioridade do modelo e FCU;
- na primeira abertura, ativar somente o Ranking QML;
- persistir localmente a última combinação de camadas escolhida pelo usuário;
- nos zooms afastados, usar amostragem progressiva estável, ponto de 1 pixel e transparência reduzida para preservar a leitura do mapa-base;
- revelar progressivamente mais células ao aproximar, mostrar todas a partir do zoom 11 e aumentar o tamanho dos pontos de forma contínua entre os zooms 12 e 15.
- incluir um minimapa recolhível no canto inferior direito, com retângulo do enquadramento principal, sincronização de movimento/zoom/mapa-base e persistência do estado aberto ou recolhido.

## Arquivos de entrega

Produza:

- dashboard online sem substituir a versão anterior;
- versão offline executada por servidor HTTP local;
- GPKG com camadas `celulas_acao`, `fcu_tipos`, `resumo_area` e `regra_escada`;
- QML para as células de ação, mantendo o tamanho visível dos pontos;
- Ranking geral graduado por `ranking_total`, com a rampa QML contínua original;
- QML para FCU Tipo 1 e Tipo 2 com transparência;
- JSON com regras, limites e quantidades por área;
- validação funcional do mapa 2D, busca, clique, filtros, painéis, links e 3D.
