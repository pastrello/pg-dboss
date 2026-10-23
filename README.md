# DBOSS — Database Optimized Operating System

**Repositório oficial:** https://github.com/pastrello/pg-dboss

Observabilidade e análise de PostgreSQL, Linux e OpenZFS em uma ferramenta.
Integra o legado **PG Intelligence 0.1.8** (coletor contínuo e histórico SQL)
com **DBOS Intelligence 0.2.1** (coletas Linux/ZFS/PG18 e comparação de
intervalos). Interface principal: `dboss`. Agente Rust ainda experimental.

> **Segurança:** o DBOSS observa o banco de aplicação em modo somente
> leitura. `dboss collect` e `dboss run` **gravam no banco de telemetria
> separado do PG Intelligence**, além de arquivos JSON locais de host.
> Não há execução automática de `pg_prewarm`, DDL, remoção de índices,
> alteração de parâmetros PostgreSQL, kernel ou ZFS.

## Guia rápido — para retomar o projeto após uma pausa

No Rocky Linux 8/9/10 (ou outro ambiente Linux de desenvolvimento):

```bash
git clone https://github.com/pastrello/pg-dboss.git
cd pg-dboss
./install.sh                     # cria .venv, instala o pacote e roda testes
.venv/bin/dboss --version
.venv/bin/dboss --help
```

Se já houver um clone:

```bash
cd pg-dboss
git switch main
git pull --ff-only origin main
./install.sh
```

O instalador usa Python >= 3.9 e `psycopg` 3; para Rocky 8, use
preferencialmente Python 3.12. O ambiente Rust/cargo é opcional. O padrão
`./install.sh` **não inicia serviços e não configura bancos**.

### Escolha o tipo de teste

| Objetivo | Comando | Conecta ao PostgreSQL? | Grava no banco? |
|---|---|---|---|
| Testar o pacote | `./install.sh` | Não | Não |
| Verificar ambiente | `./install.sh --doctor` | Não | Não |
| Rodar testes offline | `./install.sh --self-test` | Não | Não |
| Ver memória/ARC/ZFS | `.venv/bin/dboss host --output host.json` | Não | Não |
| Coletar PG18 + host | `.venv/bin/dboss probe --output sample-a.json` | Sim, somente leitura | Não |
| Comparar coletas | `.venv/bin/dboss analyze --before sample-a.json --after sample-b.json --output interval.json` | Não | Não |
| Produzir recomendações | `.venv/bin/dboss advise --interval interval.json --output advice.json` | Não | Não |
| Ler as recomendações | `.venv/bin/dboss review --advice advice.json` | Não | Não |
| Coleta contínua unificada | `.venv/bin/dboss run -c /etc/pgintel/pgintel.ini` | Sim | **Somente na telemetria** |

**Importante:** `--output` **não sobrescreve arquivos já existentes**.
Escolha nomes novos em cada coleta. Os relatórios podem conter nomes de
bancos, tabelas, caminhos e outras informações internas; mantenha-os privados.

## Procedimento 1 — Teste pontual PG18 + OpenZFS (sem banco de telemetria)

Exemplo com libpq `PGSERVICE` previamente configurado, sem senha na
linha de comando:

```bash
cd pg-dboss
./install.sh

# Opcional: apenas host Linux/OpenZFS.
.venv/bin/dboss host --output host.json

# Duas coletas na mesma instância PostgreSQL 18, separadas por
# um intervalo representativo da carga de trabalho.
PGSERVICE=meu_pg18 .venv/bin/dboss probe --output sample-a.json
# Execute a segunda coleta após a carga representativa.
PGSERVICE=meu_pg18 .venv/bin/dboss probe --output sample-b.json

# Delas deriva-se o intervalo; nada é reconsultado nesta fase.
.venv/bin/dboss analyze \
  --before sample-a.json --after sample-b.json --output interval.json

# Advisor experimental (somente leitura dos arquivos).
.venv/bin/dboss advise --interval interval.json --output advice.json
.venv/bin/dboss review --advice advice.json --limit 20
```

`dboss postgres --output postgres.json` coleta somente métricas do banco.
`dboss inspect --host host.json --postgres sample-a.json` produz uma
avaliação pontual offline; o segundo arquivo também pode ser uma coleta
`postgres`. `probe` agrega host e PostgreSQL em um JSON.

A senha de acesso deve ser fornecida pelos mecanismos seguros do libpq
(ex.: `PGSERVICE` + `~/.pgpass` com permissões apropriadas), não adicionada
aos exemplos ou ao Git.

### Como interpretar `advice.json`

O Advisor sinaliza `investigate` quando identifica, em um intervalo,
ao menos **1.000 faltas em shared_buffers** e acertos inferiores a **90%**.
`non_scan_activity` indica atividade de blocos sem buscas por índice no
intervalo — **não** que o índice é inútil. `observe` e
`cache_effective_in_sample` são categorias de observação.

Um único intervalo fornece **evidência exploratória**, não uma política de
cache. Faltas em `shared_buffers` podem ser atendidas pelo ARC ou cache
Linux; não equivalem necessariamente a I/O físico. O ARC é global ao host.

Para combinar intervalos **não sobrepostos**, somente após confirmar
manualmente que pertencem à mesma instância e banco:

```bash
.venv/bin/dboss advise \
  --interval intervalo1.json --interval intervalo2.json \
  --assume-same-source --output advice-multiperiodo.json
```

Os arquivos antigos não possuem identidade de origem verificável. O flag
`--assume-same-source` é uma responsabilidade explícita do operador.
Os dados `top-N` não cobrem necessariamente todas as relações.
**Nenhuma classificação autoriza prewarm, DROP INDEX ou tuning automático.**

## Procedimento 2 — Histórico contínuo com PG Intelligence

O DBOSS reutiliza **exatamente um coletor SQL agendado**: o motor
`pgintel` (FAST 60s; SLOW 15min; SIZE 60min por padrão). A observação
de memória e ARC é acrescentada no mesmo processo, a cada 300s por
padrão, sem uma segunda coleta PostgreSQL periódica.

A configuração existente em `/etc/pgintel/pgintel.ini` identifica o
banco monitorado e o **repositório separado** de telemetria:

```bash
# Conectividade e permissões no ambiente configurado:
.venv/bin/dboss monitor -c /etc/pgintel/pgintel.ini check

# Uma execução: grava telemetria e salva um host JSON privado.
.venv/bin/dboss collect -c /etc/pgintel/pgintel.ini

# Monitoramento contínuo: execute SOMENTE se o pgintel anterior NÃO
# estiver rodando para a mesma instância.
.venv/bin/dboss run -c /etc/pgintel/pgintel.ini \
  --host-interval 300
```

Por padrão o histórico host fica em `~/.local/state/dboss/host` (ou
`$XDG_STATE_HOME/dboss/host`), diretório privado 0700, arquivos 0600.
A retenção é de até 288 snapshots; configure `--host-dir` e
`--host-keep` se necessário. Arquivos antigos são removidos apenas
desse histórico específico.

**NÃO execute `pgintel run` e `dboss run` em paralelo para a mesma
instância.** Antes de qualquer substituição, verifique:

```bash
systemctl status pgintel --no-pager
ps -ef | grep -E '[p]gintel|[d]boss run'
```

A migração/ativação de um serviço DBOSS **não é automática**. Não faça
`stop`, `disable`, `enable` ou alterações de systemd sem um plano de
transição e rollback.

Para conferir o histórico e o custo do agente:

```bash
.venv/bin/dboss monitor -c /etc/pgintel/pgintel.ini health --hours 24
.venv/bin/dboss monitor -c /etc/pgintel/pgintel.ini report --hours 24
.venv/bin/dboss monitor -c /etc/pgintel/pgintel.ini capabilities
```

O comando legado `pgintel`, seu repositório de métricas, migrações SQL,
instalador `install-rocky.sh` e serviço `pgintel.service` são preservados,
com suporte de origem PG13–18. As novas análises DBOS são **PG18-only**.

## Instalação no sistema, diagnóstico e solução de problemas

```bash
./install.sh --help
./install.sh --doctor
./install.sh --self-test
sudo ./install.sh --install
```

A opção `--install` instala uma CLI isolada em
`/opt/dboss/venv/bin/dboss`, sem substituir um serviço existente.
**Não existe configuração de systemd DBOSS automática nesta fase.**

A opção `sudo ./install.sh --legacy-configure` aciona o instalador
histórico PG Intelligence, que **pode criar objetos de telemetria**
conforme aprovação explícita. Não use-a apenas para rodar testes.

Dicas rápidas:

- `File exists` ao gerar JSON: escolha outro nome; a proteção contra
  sobrescrita é intencional.
- `database_stats_reset = NULL`: válido no PostgreSQL 18. O analisador
  compara o início da instância e os contadores; um reset ou reinício
  incompatível invalida a comparação.
- `dboss advise` não aceita `advice.json` como entrada: use
  `interval.json`. Para visualizar `advice.json`, use `dboss review`.
- Sem `pg_stat_statements`: algumas métricas do PG Intelligence podem
  ficar indisponíveis. A ativação da extensão/preload não é automática.
- Permissões recusadas no diretório de host: o usuário deve ser proprietário
  e o diretório privado (0700). Não relaxe permissões.
- Zero `idx_scan` **não é prova** de índice dispensável.
- O protótipo Rust está em `crates/dboss-agent` e não substitui a coleta
  Python atual nem é executado automaticamente.

## Limites, segurança e continuidade

- Não alteramos o banco de aplicação, índices, PGDATA, ZFS ou kernel.
- O repositório de telemetria do PG Intelligence **é gravado** em
  `collect/run`; confirme conexão, privilégios e retenção antes de rodar.
- Os relatórios `sample*.json`/`interval*.json`/`advice*.json` e
  históricos host **não devem ser commitados** com informações de clientes.
- Resultados de Advisor baseados em uma janela não demonstram ganho
  de latência, cache nem redução de escrita.
- O código Rust continua experimental. Uma migração só deve acontecer
  após paridade funcional, benchmarks de CPU/RAM/latência e rollback.

**Documentação complementar:** [arquitetura](docs/ARCHITECTURE.md),
[estado e pendências](docs/PROJECT-STATE.md),
[compatibilidade PG13–18](docs/COMPATIBILITY.md),
[segurança da coleta](docs/PRODUCTION_SAFETY.md),
[estratégia Rust](docs/RUST-STRATEGY.md),
[orientação da instalação legada](docs/SEMI_PRODUCTION_HOWTO.md) e
[histórico do PG Intelligence](docs/PG-INTELLIGENCE-ORIGINAL.md).

Para retomar em outro chat/Codex: consulte
`AGENTS.md`, `docs/PROJECT-STATE.md` e este `README.md` antes de qualquer
alteração. **GitHub é a fonte oficial de código, estado e decisões.**
