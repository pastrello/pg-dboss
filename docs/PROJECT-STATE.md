# DBOSS — Project State

Atualizado: 2026-10-23

## Fonte oficial
- GitHub: https://github.com/pastrello/pg-dboss
- `main`: PR #5 (base DBOS/PGIntel), PR #6 (um SQL scheduler) e
  PR #7 (Smart Cache Advisor offline) já incorporados.
- Alteração deste ciclo: README de operação e visualização textual
  de `advice.json` via `dboss review`.

## Implementado
- `install.sh` único para preparação local, testes, diagnóstico e instalação
  isolada; nenhum serviço é iniciado automaticamente.
- `dboss host/postgres/probe/inspect/analyze`: coletas pontuais DBOS PG18
  e comparação offline; saída JSON sem sobrescrita.
- `dboss collect/run`: PGIntel como **único** coletor SQL periódico,
  repositório de telemetria separado e observação Linux/ZFS no mesmo processo.
- Histórico local host em JSON privado (0700 dir, 0600 arquivo), retenção
  limitada, 300s padrão.
- `dboss advise`: heurísticas offline para intervalos PG18, nunca tuning.
- `dboss review --advice advice.json`: resumo legível offline.
- CLI/config/serviço/migrações legados do PG Intelligence continuam
  compatíveis; suporte de monitoramento PG13–18 preservado.
- Rust é protótipo host separado, sem instalação automática.

## Evidências recentes (laboratório, não benchmark)
- `advice.json` fornecido pelo usuário: DBOSS 0.1.0, banco `erp`,
  um intervalo, origem não verificada, confiança `exploratory`.
- 20 candidatos mostrados: 10 `investigate`, 4 `non_scan_activity`,
  6 `observe`. Destaques: `pendfin`, `movprodc` e índice
  `rcnf_idnfe_tipodcto_idx`.
- Ainda não há evidência para prewarm automático, remoção de índices
  nem tuning de ARC/kernel. Nenhuma ação no banco modelo autorizada.

## Limitações e próximos gates
- Observações Linux/ARC ainda não estão no repositório SQL de telemetria
  e não possuem identidade de host/cluster suficientemente verificada.
- Mais intervalos representativos são necessários; amostra única não
  determina blocos quentes ou ganho de latência.
- Nenhuma troca de systemd automática; não executar `pgintel run` e
  `dboss run` ao mesmo tempo na mesma instância.
- Testes funcionais Rocky 8/9/10 + PG18 + OpenZFS, custos de coleta de
  24h e benchmarks Rust/Python continuam pendentes.
- Não copiar snapshots/dados sensíveis para repositórios públicos.
- Compatibilidade de distribuição Python permanece `pg-intelligence
  0.1.8` e CLI DBOSS `0.1.0` até migração aprovada.

## Contrato de segurança
O banco de aplicação é **somente leitura**. `dboss collect/run` gravam
no repositório separado de telemetria, além de JSON local de host.
Sem SQL de alteração ao modelo, pg_prewarm, ALTER SYSTEM, mudanças de
índices, ZFS, kernel ou serviços. Documentar todo novo procedimento
no README, evitando comandos não implementados.
