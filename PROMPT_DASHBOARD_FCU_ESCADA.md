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
- Modelo IBGE/Espectral, correspondente ao modelo não morfológico.

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

- atenção prioritária: vermelho `#d7191c`;
- atenção: laranja `#f28e2b`;
- demais áreas: transparente;
- sem resultado: transparente;
- preservar o tamanho atual dos pontos e deixá-los clicáveis;
- FCU Tipo 1: cinza-escuro com preenchimento translúcido e contorno contínuo;
- FCU Tipo 2: cinza-claro com preenchimento translúcido e contorno tracejado;
- desenhar as FCUs sem bloquear o clique nos pontos abaixo;
- legenda separada em “Classe de ação” e “Situação territorial”;
- filtros independentes para as duas dimensões;
- mostrar na legenda o percentual FCU, a expansão, a quantidade prioritária e a quantidade em atenção da área selecionada.

## Painel da célula

Ao clicar em uma célula, mostre:

- ID, município e área de estudo;
- classe de ação e ranking geral;
- situação territorial e identificação da FCU, quando houver;
- Modelo Completo: alto, médio ou baixo;
- Modelo Morfológico: alto, médio ou baixo;
- Modelo IBGE/Espectral: alto, médio ou baixo;
- pontuação ou probabilidade de cada modelo;
- links para Google Maps, Street View e visualização 3D.

## Visualização 3D

- manter edificações e alturas GBA;
- colorir atenção prioritária em vermelho e atenção em laranja;
- deixar demais áreas e sem resultado transparentes;
- sobrepor FCU Tipo 1 e Tipo 2 em cinza translúcido;
- preservar seleção, popup, filtros, rotação, inclinação e retorno ao mapa 2D.

## Arquivos de entrega

Produza:

- dashboard online sem substituir a versão anterior;
- versão offline executada por servidor HTTP local;
- GPKG com camadas `celulas_acao`, `fcu_tipos`, `resumo_area` e `regra_escada`;
- QML para as células de ação, mantendo o tamanho visível dos pontos;
- QML para FCU Tipo 1 e Tipo 2 com transparência;
- JSON com regras, limites e quantidades por área;
- validação funcional do mapa 2D, busca, clique, filtros, painéis, links e 3D.
