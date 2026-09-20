# GM TV+ Football Data

Cache público de metadados de futebol usado pelo GM TV+.

Fontes:
- football-data.org: calendário, partidas, times, escudos e emblemas disponíveis no plano configurado.
- OpenFootball: fallback público para calendário.
- Wikidata/Wikimedia Commons: fallback de artwork quando a fonte principal não fornece imagem.

O aplicativo não recebe o token do football-data.org. A chave fica somente em `FOOTBALL_DATA_TOKEN`, dentro dos GitHub Actions Secrets.

Feed público:
`data/football-feed.json`

A atualização automática roda a cada duas horas e também pode ser disparada manualmente em **Actions**.
