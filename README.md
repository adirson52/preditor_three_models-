# Dashboard B - Preditor FCU

Dashboard público e offline com três modelos EBM para predição espacial de FCU. Esta versão usa ranking geral em escadas e inclui Salvador.

## Versão ranking em escadas

- A classe de ação considera todas as células da área no `ranking_total`.
- O mapa usa sempre o `Ranking geral`, preservando a rampa QML contínua vermelho–amarelo–verde–azul no intervalo fixo de 1 a 104.032.
- A linha `ranking QML`, no grupo `Estilo QML`, liga e desliga a camada QML sem trocar de simbologia.
- `Prioridade do modelo` aparece como grupo de filtros da legenda: atenção prioritária, atenção e demais áreas.
- O grupo `Prioridade do modelo` permite ligar e desligar atenção prioritária, atenção e demais áreas de forma independente.
- O grupo `FCU` permite ligar e desligar FCU Tipo 1 e FCU Tipo 2; uma FCU visível recebe o clique antes da célula e abre seu popup territorial.
- A situação territorial é independente da classe de ação: fora da FCU, FCU Tipo 1 ou FCU Tipo 2.
- FCU Tipo 2 ocorre quando pelo menos 50% das células válidas da FCU têm três modelos baixos ou dois baixos e um médio; as demais são FCU Tipo 1.
- O painel de cada célula mostra Completo, Morfológico e IBGE/Espectral como alto, médio ou baixo.
- A visualização 3D de Salvador usa as mesmas classes e as geometrias contínuas das FCUs.
- Nos zooms 6–9 os pontos usam 1 pixel; nos zooms 10–11 usam marcador compacto; a partir do zoom 12 o tamanho próximo original é preservado.
- As FCUs usam uma única camada vetorial interativa, com contorno e transparência suavizados nos zooms afastados.

## Conteudo publicado

- `index.html`: dashboard final.
- `data_tiles/`: tiles estaticos do mapa, pontos, lookup de busca e FCUs originais.
- `vercel.json`: headers de cache e gzip para os tiles.
- `data_tiles/final/ranking_rules_escada.json`: limites e contagens por área.
- `data_tiles/final/estilos_qgis/`: estilos QML públicos.
- `data_tiles/final/overview_qml/`: visão geral com a rampa QML antiga.
- `data_tiles/final/overview_action/`: visão geral categórica gerada como ativo técnico, sem uso na visualização principal.
- `PROMPT_DASHBOARD_FCU_ESCADA.md`: prompt reutilizável da especificação completa.
- `tools/dashboard_generator_0407.py`: copia do gerador usado neste checkpoint.
- `tools/consolidate_lookup.py`: utilitario que consolida o lookup de busca para reduzir arquivos no deploy.
- `tools/gerar_overview_qml.py`: gera os tiles QML separados por prioridade e por zoom.
- `tools/validar_overview_qml.py`: valida contagens, paleta e opacidades dos tiles QML.

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
