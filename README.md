# Dashboard B - Preditor FCU

Dashboard público e offline com três modelos EBM para predição espacial de FCU. Esta versão usa ranking geral em escadas e inclui Salvador.

## Versão ranking em escadas

- A classe de ação considera todas as células da área no `ranking_total`.
- O mapa usa sempre o `Ranking geral`, calculado separadamente em cada área. Cada área distribui todas as suas células no próprio intervalo de 1 até o total local, em 50 faixas, preservando as cores e a opacidade integral do `estilo_revelando2608.qml`.
- A linha `ranking QML`, no grupo `Estilo QML`, liga e desliga uma única camada QML com os 50 tons.
- `Prioridade do modelo` é outra camada, separada do QML, composta pelas subcamadas atenção prioritária, atenção e demais áreas.
- QML e prioridade são independentes: desligar uma prioridade não modifica o QML, e desligar o QML não modifica as três prioridades.
- Em `Prioridade do modelo`, atenção prioritária é vermelha, atenção é laranja e demais áreas permanece transparente.
- O grupo `FCU` permite ligar e desligar FCU Tipo 1 e FCU Tipo 2; uma FCU visível recebe o clique antes da célula e abre seu popup territorial.
- A situação territorial é independente da classe de ação: fora da FCU, FCU Tipo 1 ou FCU Tipo 2.
- FCU Tipo 2 ocorre quando pelo menos 50% das células válidas da FCU têm três modelos baixos ou dois baixos e um médio; as demais são FCU Tipo 1.
- O painel de cada célula mostra Completo, Morfológico e IBGE/Espectral como alto, médio ou baixo.
- A visualização 3D de Salvador usa as mesmas classes e as geometrias contínuas das FCUs.
- Nos zooms 6–9 os pontos usam 1 pixel; nos zooms 10–11 usam marcador compacto; a partir do zoom 12 o tamanho próximo original é preservado.
- As FCUs usam uma única camada vetorial interativa, com contorno e transparência suavizados nos zooms afastados.

## Conteudo publicado

- `index.html`: dashboard final.
- `guia.html`: guia visual de leitura e priorização, com roteiro, legenda, regra da escada, simulador, leitura da célula, orientação analítica e FAQ.
- `assets/guia/`: recortes reais do mapa 2D, painel da célula e visualização 3D usados no guia.
- `data_tiles/`: tiles estaticos do mapa, pontos, lookup de busca e FCUs originais.
- `vercel.json`: headers de cache e gzip para os tiles.
- `data_tiles/final/ranking_rules_escada.json`: limites e contagens por área.
- `data_tiles/final/estilos_qgis/`: estilos QML públicos.
- `data_tiles/final/estilos_qgis/estilo_revelando2608.qml`: cópia canônica do estilo QGIS usado pela camada `ranking QML`.
- `data_tiles/final/estilos_qgis/por_area/`: onze QMLs com as 50 faixas recalculadas para o ranking de cada área de estudo.
- `data_tiles/final/overview_qml/`: camada única da visão geral com todas as células na rampa QML original.
- `data_tiles/final/overview_action/`: visão geral categórica gerada como ativo técnico, sem uso na visualização principal.
- `data_tiles/final/overview_action_classes/`: subcamadas independentes de prioridade e atenção; demais áreas é lógica e transparente.
- `PROMPT_DASHBOARD_FCU_ESCADA.md`: prompt reutilizável da especificação completa.
- `tools/dashboard_generator_0407.py`: copia do gerador usado neste checkpoint.
- `tools/consolidate_lookup.py`: utilitario que consolida o lookup de busca para reduzir arquivos no deploy.
- `tools/gerar_overview_qml.py`: gera a camada QML única e as subcamadas categóricas de prioridade por zoom.
- `tools/validar_overview_qml.py`: valida contagens, paleta e opacidades dos tiles QML.
- `tools/validar_camadas_areas.py`: valida, célula a célula, as classes e os limites da escada nas 11 áreas de estudo.
- `VALIDACAO_OFFLINE_LEGENDA_FCU_20260828.md`: relatório reproduzível dos testes funcionais do mapa, FCUs e 3D.
- `VALIDACAO_OFFLINE_GUIA_V1_20260828.md`: relatório da validação visual e funcional do guia em desktop e tela estreita.

## Execução offline

Dê duplo clique em `iniciar_dashboard_offline.bat`. O atalho abre `http://127.0.0.1:8767/index.html` e deve permanecer aberto durante a navegação.

## Arquivos locais fora do deploy

Os GPKGs, GeoParquet, zips, logs e a pasta `downloads/` ficam fora do Git/Vercel por `.gitignore` e `.vercelignore`, pois sao grandes demais para hospedagem gratuita.

O pacote local contém `downloads/preditor_fcu_salvador_ranking_escada.gpkg` e os dois estilos QML.

## Checkpoint

- Commit base: `9a5f4bb`
- Tag base: `checkpoint-dashboard-b-2026-07-08`
- Versao Vercel: usa lookup consolidado em `data_tiles/final/id_lookup/8`, para ficar abaixo do limite de arquivos do plano gratuito.

## Deploy

```powershell
npx vercel --prod --yes
```
