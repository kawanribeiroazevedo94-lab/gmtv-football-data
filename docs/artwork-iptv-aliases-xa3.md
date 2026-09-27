# Artwork XA3 — nomes recebidos da IPTV

## Diagnóstico reproduzido

As capturas de 26/09/2026 mostram 14 confrontos. O APK XA2 já separa nomes e horários, mas seis nomes não encontram imagem no catálogo publicado no commit `67585e188e5e9cc76e7f4c468ac2d47613b440d0`.

O código Kotlin real da XA2 foi executado com esses nomes: 22 URLs presentes em 28 participantes. Os seis resultados `null` correspondem exatamente aos fallbacks mostrados nas capturas.

| Nome recebido | Entidade do catálogo | Alteração |
| --- | --- | --- |
| MACED. DO NORTE | North Macedonia — `espn:team:463` | Alias revisado |
| SUIGA | Switzerland — `espn:team:475` | Grafia recebida da IPTV, revisada |
| TCHEQUIA | Czechia — `espn:team:450` | Alias Tchéquia |
| OPERARIO | Operário PR — `espn:team:18187` | Alias Operário |
| EUA | United States — `espn:team:660` | Alias EUA |
| PERU | Peru — `espn:team:211` | Novo registro validado |

A normalização existente já ignora caixa e acentos. Nenhuma regra de aproximação de nomes foi adicionada. O Android continua rejeitando um nome quando o catálogo fornece mais de uma entidade possível sem contexto suficiente.

## Evidência de identidade

`SUIGA` aparece literalmente na captura. A interpretação como Suíça foi conferida contra o adversário e a data: a [UEFA registra Macedônia do Norte × Suíça em 26/09/2026](https://www.uefa.com/uefanationsleague/teams/128/matches/). Trata-se de um alias revisado dessa grafia, não de correção automática de qualquer palavra parecida.

O feed publicado registra Operário-PR × Ceará em 26/09/2026 às 16:30, correspondendo ao confronto exibido. A entidade e o escudo do Operário foram conferidos no [registro do provedor](https://site.api.espn.com/apis/site/v2/sports/soccer/bra.2/teams/18187?lang=pt&region=br). O alias não elimina sufixos de outros clubes.

O Peru foi encontrado na [lista de seleções do provedor](https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.worldq.conmebol/teams?limit=100&lang=pt&region=br), com ID `211` e imagem `https://a.espncdn.com/i/teamlogos/countries/500/per.png`. A resposta PNG foi decodificada integralmente e inspecionada visualmente antes da entrega.

As seis URLs responderam HTTP 200 com `image/png`, 500 × 500 pixels. As cinco imagens existentes mantêm suas URLs; somente o Peru acrescenta uma imagem ao catálogo. Para seleções, estas imagens são bandeiras.

## Verificação e limites

Com o catálogo corrigido, o mesmo Kotlin da XA2 resolve os 28 nomes para as URLs dos IDs esperados. Passaram 90 testes Python, incluindo as regressões das abreviações e a rejeição de nomes aproximados não cadastrados.

`tests/fixtures/iptv_names_20260926.json` transcreve os nomes e horários visíveis. O campo `title` reconstrói esses valores no formato de canal já conhecido; não representa uma exportação dos títulos brutos do Xtream. Não contém credenciais nem IDs privados de canais.

Nenhum arquivo Android é alterado. Os aliases são dados do catálogo e sobrevivem à regeneração pela rotina existente. Partidas, datas, horários, canais e demais imagens não são substituídos pela atualização.

A competição permanece desconhecida quando não está identificada no título utilizado pela XA2. Esta atualização não atribui competições às partidas nem acrescenta jogos à IPTV. A confirmação visual dos seis casos na TV continua necessária.
