# Dashboard B - Preditor FCU

Checkpoint do dashboard publico com tres modelos EBM para predicao espacial de FCU.

## Conteudo publicado

- `index.html`: dashboard final.
- `data_tiles/`: tiles estaticos do mapa, pontos, lookup de busca e FCUs originais.
- `vercel.json`: headers de cache e gzip para os tiles.
- `tools/dashboard_generator_0407.py`: copia do gerador usado neste checkpoint.
- `tools/consolidate_lookup.py`: utilitario que consolida o lookup de busca para reduzir arquivos no deploy.

## Arquivos locais fora do deploy

Os GPKGs, GeoParquet, zips, logs e a pasta `downloads/` ficam fora do Git/Vercel por `.gitignore` e `.vercelignore`, pois sao grandes demais para hospedagem gratuita.

## Checkpoint

- Commit base: `9a5f4bb`
- Tag base: `checkpoint-dashboard-b-2026-07-08`
- Versao Vercel: usa lookup consolidado em `data_tiles/final/id_lookup/8`, para ficar abaixo do limite de arquivos do plano gratuito.

## Deploy

```powershell
npx vercel --prod --yes
```
