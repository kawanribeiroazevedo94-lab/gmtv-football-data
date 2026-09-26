# Artwork para os jogos disponíveis no IPTV

`data/football-artwork.json` contém metadados de imagens. Não contém partidas,
horários, canais, URLs de reprodução nem credenciais. O catálogo não determina
quais jogos aparecem no aplicativo. Essa seleção pertence à lista Xtream.

O cliente XA1 usa os canais das categorias `JOGOS DO DIA` já reconhecidas pelo
aplicativo. Cada canal real pode criar uma linha. A agenda pública não adiciona
partidas à tela. Títulos que não seguem o formato reconhecido continuam visíveis
com seu texto original e com seu canal. Datas futuras não são inferidas a partir
de uma categoria que só informa jogos de hoje.

## Identidade e imagens

`data/artwork-catalog.json` conserva o ID da entidade no fornecedor, nome,
aliases revisados, competição/país, URL de origem e prova de download/PNG.
Os nomes preservam `SC`, `FC` e `Club`: Barcelona SC não é Barcelona, e FIFA
Club World Cup não é FIFA World Cup. Homônimos usam o contexto da competição;
uma associação ambígua retorna ausência de imagem, sem escolher o primeiro
resultado. Equipes femininas têm IDs próprios.

O catálogo é uma base finita. Uma entidade desconhecida pode aparecer como jogo
real do IPTV com o fallback, até que sua imagem e seus aliases sejam validados.
Uma nova imagem validada não exige outro APK. Não há promessa de cobertura
universal nem de identificação de qualquer formato livre de título Xtream.

Para ampliar a base, registrar a identidade e os aliases, confirmar a URL HTTPS
e o PNG, revisar a imagem e acrescentar a prova em `artwork-catalog.json`.
`generate_artwork_catalog.py` também exporta novas entradas PNG já publicáveis
do cache V2, sem promover `candidateUrl`. O catálogo revisado tem prioridade.

## Correções da atualização

- Classificação semântica mantém palavras significativas como `football club`.
- Uma falha de consulta não apaga uma imagem anteriormente validada no V2.
- Rejeições explícitas continuam revogando imagens.
- Chaves de clube podem incluir a competição e não se tornam defaults globais.
- Consultas de descoberta têm limite por execução e respeitam HTTP 429.
- Descoberta não aceita arbitrariamente o primeiro resultado de busca no Commons.

As imagens permanecem nos seus fornecedores. No Android, a correção UA1 mantém
um User-Agent identificável para a Wikimedia, `ContentScale.Fit` e fallback de
erro/URL ausente. O cache em memória do catálogo só conserva a última resposta
boa durante o processo; na primeira carga sem catálogo disponível os jogos
continuam visíveis com fallback.

## Comandos

```sh
python3 -m unittest discover -s tests -q
python3 scripts/refresh_catalog_cache.py
```

O segundo comando atualiza apenas as imagens do snapshot existente. O workflow
normal mantém a geração dos feeds para compatibilidade e publica o catálogo.
Esses feeds não são usados pelo fluxo XA1 para inventar jogos sem canal IPTV.

Download HTTP 200, decodificação PNG e testes de identidade não substituem o
build Android nem a validação visual na TV.
