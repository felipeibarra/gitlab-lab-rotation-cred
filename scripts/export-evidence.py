#!/usr/bin/env python3
"""Export only an allowlist of non-credential fields from completed migrations."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('at', 'role', 'pipeline_id', 'status', 'sha', 'old_token_http_status',
          'old_user_blocked', 'legacy_user_id', 'native_user_id', 'ticket', 'owner')
JOBS = ('id', 'name', 'status')
WORKER = ('ok', 'checked_at', 'user_id', 'project_id', 'http_status')


def select(source, keys):
    return {key: source[key] for key in keys if key in source}


def main():
    result = []
    for role in ('reader', 'publisher', 'deployer'):
        path = ROOT / '.lab' / 'reports' / f'closed-{role}.json'
        if not path.exists():
            continue
        report = json.loads(path.read_text())
        if report.get('role') != role or report.get('status') != 'success' or report.get('old_token_http_status') not in (401, 403):
            raise SystemExit(f'Reporte de {role} no acredita cierre correcto; no se exporta.')
        item = select(report, FIELDS)
        item['jobs'] = [select(job, JOBS) for job in report.get('jobs', [])]
        item['worker'] = select(report.get('worker', {}), WORKER)
        result.append(item)
    if not result:
        raise SystemExit('No hay reportes de cuentas retiradas. Ejecuta las migraciones primero.')
    destination = ROOT / 'evidence' / 'closed-accounts.json'
    destination.parent.mkdir(exist_ok=True)
    if destination.exists():
        raise SystemExit('evidence/closed-accounts.json ya existe; revísalo y renómbralo antes de exportar nuevamente.')
    destination.write_text(json.dumps({'scope': 'local training only', 'closed_accounts': result}, indent=2) + '\n')
    print(f'Exportadas {len(result)} cuentas a evidence/closed-accounts.json. Revisa manualmente antes de publicar.')


if __name__ == '__main__':
    main()
