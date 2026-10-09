# Métricas das redes do criador

Conexão autorizada é simulada: Instagram, TikTok, YouTube e X usam a mesma
interface `Provider.fetch(connection, start, end)` em `provider.py`. O token
fictício é validado e descartado; não implementamos OAuth nem API real de redes.

Cada conexão tem seus próprios posts. Snapshot é identificado por **post +
instante capturado**; repetições e janelas sobrepostas não somam contagens.
O estado atual usa apenas o snapshot mais recente de cada post e soma esses
estados, nunca snapshots históricos. Snapshot antigo não regride métricas;
mesma identidade com contagens diferentes retorna 409 e rollback.
`captured_at`, `fetched_at` e `last_sync_at` distinguem captura e consulta.

Timeout/5xx têm backoff de 1s, 2s, até **3 tentativas**. `429` respeita
`Retry-After` em segundos ou HTTP-date, usando relógio e sleep injetáveis.
O teto de espera **total** é 5s por sync. Se o provedor exige mais, retornamos
`deferred` com `next_allowed_at` persistido; nenhuma chamada antecipada é feita.
Não existe worker oculto: o chamador agenda nova tentativa para esse instante.
401 e outros erros permanentes não são repetidos. Na interface Python, tentativas
e teto podem ser configurados até 5 e 30s respectivamente.

## Exemplo

```bash
curl -s "$BASE/connections" -H 'Content-Type: application/json' -d '{"id":"c1","platform":"instagram","token":"fake-authorized-token"}'
curl -s "$BASE/connections/c1/sync" -H 'Content-Type: application/json' -d '{"start":"2026-10-09T00:00:00Z","end":"2026-10-10T00:00:00Z","responses":[{"posts":[{"id":"p1","captured_at":"2026-10-09T14:00:00Z","views":100,"likes":10,"comments":2}]}]}'
curl -s "$BASE/connections/c1"
```

Sync retorna `status: "synced"`, `inserted_snapshots: 1` e
`totals: {"views":100,"likes":10,"comments":2}`. Repetir retorna
`inserted_snapshots: 0`, mesmos totais. Para simular falha antes do sucesso,
coloque `{"status":429,"retry_after":"2"}` antes da resposta de posts;
para timeout use `{"status":"timeout"}`. Os timestamps devem incluir fuso.
A janela inclusiva filtra `captured_at`, não data de publicação do post.

Com mais tempo: worker assíncrono, paginação/cursor do provedor, armazenamento
seguro de tokens e limites compartilhados entre conexões. Neste demo síncrono,
a transação fica aberta durante a espera limitada do provedor.

## Rodar e verificar

Python 3.12 com base de fusos IANA (incluída no Ubuntu); sem `pip install`.

```bash
python3 -m unittest -v
python3 app.py
```

API na porta 8080. `PORT`, `HOST` (padrão 127.0.0.1), `DATABASE_PATH` (padrão
`data.sqlite3`) e `API_TOKEN` configuram o processo. Com `API_TOKEN`, envie
`Authorization: Bearer ...`; `/health` fica público. Os exemplos abaixo usam
`BASE` como a URL do processo ou de um proxy HTTPS. `test_http.py` executa o
fluxo pela rede HTTP real, além dos testes de domínio com relógio controlado.

Respostas são JSON; sucesso 200, entrada inválida 422, conflito 409, ausente
404. JSON malformado retorna 400. SQLite persiste estado em transações
`BEGIN IMMEDIATE`; uma operação inválida faz rollback, inclusive de alterações
parciais. Reiniciar preserva dados. Cada execução de testes usa banco isolado.

## Limites desta entrega

O adaptador HTTP é uma demonstração síncrona, não um servidor de produção.
SQLite guarda um documento de estado por aplicação: simples para verificar as
invariantes e a persistência, mas inadequado para grande volume. Com mais tempo,
normalizaria tabelas e índices, adicionaria autenticação por usuário/tenant,
limites operacionais, observabilidade e migrações. O token compartilhado não
substitui autorização por recurso. Não exponha dados reais neste demo.

## Uso de IA

Codex implementou, testou e fez revisão automatizada das regras, exemplos e
resultados a pedido de Leon Hatori. Não declaramos revisão humana que ainda
não ocorreu. Detalhes em [AI_USAGE.md](AI_USAGE.md).
