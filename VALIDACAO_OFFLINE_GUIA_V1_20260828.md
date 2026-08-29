# Validação offline — Guia de uso v1

Data: 28/08/2026

## Escopo

- página validada em `http://127.0.0.1:8767/guia.html`;
- nenhuma publicação online realizada;
- navegação integrada ao dashboard por `Guia de uso`;
- linguagem voltada à leitura e priorização territorial, sem direcionamento institucional explícito.

## Conteúdo confirmado

- 8 seções principais: roteiro, legenda, regra da escada, leitura da célula, explicabilidade, decisão, imagens/3D e FAQ;
- fluxo em 6 etapas, da área de estudo à decisão;
- 6 itens da legenda explicados separadamente;
- tabela com os 9 exemplos completos da escada;
- intervalos completos de F e E descritos abaixo da tabela;
- simulador interativo da regra;
- explicação dos três modelos e dos níveis alto, médio e baixo;
- regra de FCU Tipo 1 e FCU Tipo 2;
- explicabilidade organizada da visão global à leitura local, com limites interpretativos visíveis;
- 10 perguntas frequentes pesquisáveis;
- 6 recortes reais: mapa e legenda, painel de uma célula, três gráficos de explicabilidade e visualização 3D.

## Testes funcionais

- página respondeu HTTP 200;
- conteúdo textual não vazio e sem sobreposição de erro;
- zero erros registrados no console;
- todos os seis recortes carregaram com dimensão válida;
- seção de explicabilidade validada com sequência global → célula → comparação → curvas;
- os alertas de limite interpretativo permanecem visíveis abaixo dos gráficos;
- simulador testado com F = 25%: E = 15%, prioritária até 32,5%, atenção seguinte 7,5% e total destacado 40%;
- para 10.000 células, o simulador apresentou 3.250 prioritárias, 750 de atenção e 6.000 em demais áreas;
- pesquisa `explicabilidade` filtrou corretamente a nova pergunta correspondente;
- ampliação dos novos gráficos abriu e fechou por clique e pela tecla Escape;
- links locais `Início`, `Guia de uso` e `Voltar ao mapa` foram resolvidos corretamente;
- dashboard principal permaneceu funcional, com mapa carregado e nenhuma imagem quebrada;
- alternância de idioma do dashboard apresentou `Home / User guide / Learn more` e restaurou `Início / Guia de uso / Saiba mais`.

## Validação visual

- desktop testado em 1440 × 1000, sem rolagem horizontal;
- tela estreita testada em 390 × 844, sem rolagem horizontal da página;
- a tabela usa rolagem interna na tela estreita;
- cartões, fluxo, gráficos, simulador e FAQ reorganizam-se em uma coluna no celular;
- navegação por seções permanece horizontal e rolável em telas estreitas.

## Resultado

Guia v1 aprovado para validação do usuário no pacote offline. A versão online permaneceu inalterada.
