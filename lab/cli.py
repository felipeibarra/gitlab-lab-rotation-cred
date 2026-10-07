"""Hands-on LOCAL GitLab migration CLI. Not a production migration framework."""
from __future__ import annotations
import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlencode
from lab.api import APIError, Client
from lab.storage import atomic_write, read_json, write_json
from services.app import DEFAULT_CATALOG

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / '.lab'
BASE = 'http://127.0.0.1:8929'
ROLES = ('reader', 'publisher', 'deployer')
MARKER = 'LOCAL MIGRATION LAB ONLY'
SCOPES = {'reader': ['read_api'], 'publisher': ['api'], 'deployer': ['api']}
TERMINAL = {'success', 'failed', 'canceled', 'skipped'}
VARIABLE_FIELDS = ('value', 'variable_type', 'protected', 'masked', 'raw', 'environment_scope', 'description')

def require(condition, message):
    if not condition:
        raise ValueError(message)

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def expires(days=30):
    return (dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=days)).isoformat()

def load():
    require((WORK / 'state.json').exists(), 'Ejecuta primero init, auth y seed.')
    return read_json(WORK / 'state.json')

def save(state):
    write_json(WORK / 'state.json', state)

def creds():
    return read_json(WORK / 'secrets.json') if (WORK / 'secrets.json').exists() else {}

def save_creds(value):
    write_json(WORK / 'secrets.json', value)

def admin():
    require((WORK / 'admin.token').exists(), 'Ejecuta scripts/labctl auth.')
    return Client(BASE, (WORK / 'admin.token').read_text().strip())

def token_for(role, side):
    return creds()[role][side]

def active_side(info):
    return 'native' if info['phase'] in ('switched', 'validated', 'retiring', 'retired') else 'legacy'

def event(kind, **details):
    # Only call with explicitly selected non-secret fields.
    path = WORK / 'events.jsonl'
    with path.open('a', encoding='utf-8') as stream:
        os.chmod(path, 0o600)
        stream.write(json.dumps({'at': now(), 'event': kind, **details}) + '\n')

def docker(*args, capture=False):
    # Refuse remote Docker daemons: this lab has privileged bootstrap operations.
    context = subprocess.run(['docker', 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}'],
                             capture_output=True, text=True, check=True).stdout.strip()
    endpoint = os.environ.get('DOCKER_HOST', context)
    require(endpoint.startswith(('unix://', 'npipe://')), 'Solo Docker local; no se admiten daemons TCP/SSH.')
    return subprocess.run(['docker', 'compose', *args], cwd=ROOT, check=True,
                          text=True, capture_output=capture)

def cmd_init(args):
    WORK.mkdir(exist_ok=True, mode=0o700)
    os.chmod(WORK, 0o700)
    for name in ('runtime', 'worker', 'runner', 'reports', 'backups'):
        (WORK / name).mkdir(exist_ok=True, mode=0o700)
    if not (WORK / 'root_password').exists():
        atomic_write(WORK / 'root_password', secrets.token_urlsafe(32))
    if not (ROOT / '.env').exists():
        atomic_write(ROOT / '.env', (ROOT / '.env.example').read_text() + f'\nLAB_UID={os.getuid()}\nLAB_GID={os.getgid()}\n')
    print('Inicializado. Credenciales locales excluidas de Git; no se imprimen.')
    print("Entrada requerida en /etc/hosts: 127.0.0.1 gitlab.lab")

def cmd_doctor(args):
    require(sys.version_info >= (3, 10), 'Se requiere Python >=3.10.')
    require(shutil.which('docker'), 'Falta Docker con Compose v2.')
    docker('version')
    docker('config', '--quiet')
    require(socket.gethostbyname('gitlab.lab') == '127.0.0.1', 'Agrega 127.0.0.1 gitlab.lab a /etc/hosts.')
    print('Doctor OK. Revisa recursos de Docker: recomendación del lab, 10-12 GB RAM, 4 CPU, 35 GB libres.')

def cmd_wait(args):
    client = Client(BASE, api=False)
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        try:
            client.get('/-/readiness')
            print('GitLab respondió readiness.')
            return
        except (APIError, ValueError):
            time.sleep(5)
    raise ValueError('GitLab no está listo; revisa docker compose logs gitlab. No se modificaron cuentas.')

def cmd_auth(args):
    require((WORK / 'root_password').exists(), 'Ejecuta init primero.')
    if (WORK / 'admin.token').exists():
        require(admin().get('/user')['is_admin'], 'El PAT local no tiene privilegios de administración.')
        print('PAT administrativo local válido.')
        return
    # Capture, never print. This bootstraps only the disposable local instance.
    ruby = '''u = User.find_by_username!("root")
t = u.personal_access_tokens.create!(name: "migration-lab-bootstrap", scopes: ["api", "create_runner"], expires_at: 30.days.from_now)
puts "LAB_ADMIN_TOKEN:" + t.token
'''
    result = docker('exec', '-T', 'gitlab', 'gitlab-rails', 'runner', ruby, capture=True)
    match = re.search(r'^LAB_ADMIN_TOKEN:(\S+)$', result.stdout, re.M)
    require(match is not None, 'Bootstrap no devolvió PAT; revisar Rails sin publicar logs sensibles.')
    atomic_write(WORK / 'admin.token', match.group(1))
    print('PAT de administración guardado localmente con permisos 0600; caduca en 30 días.')

def get_or_none(client, path):
    try:
        return client.get(path)
    except APIError as exc:
        if exc.status == 404:
            return None
        raise

def grant(client, item, uid):
    endpoint = f"/{item['kind']}/{item['id']}/members"
    existing = get_or_none(client, f'{endpoint}/{uid}')
    data = {k: item[k] for k in ('access_level', 'expires_at') if k in item}
    if existing:
        client.request('PUT', f'{endpoint}/{uid}', data)
    else:
        client.request('POST', endpoint, {'user_id': uid, **data})

def variable_path(pid, key, scope='*'):
    return f'/projects/{pid}/variables/{quote(key, safe="")}?{urlencode({"filter[environment_scope]": scope})}'

def put_variable(client, pid, key, value, masked=False):
    existing = get_or_none(client, variable_path(pid, key))
    if existing:
        client.request('PUT', variable_path(pid, key), {'value': str(value)})
    else:
        client.request('POST', f'/projects/{pid}/variables', {'key': key, 'value': str(value), 'masked': masked,
                       'protected': False, 'raw': True, 'environment_scope': '*', 'variable_type': 'env_var'})

def issue_token(client, uid, name, scopes, group_id=None):
    endpoint = f'/users/{uid}/personal_access_tokens' if group_id is None else f'/groups/{group_id}/service_accounts/{uid}/personal_access_tokens'
    return client.request('POST', endpoint, {'name': name, 'scopes': scopes, 'expires_at': expires()})

def cmd_seed(args):
    a = admin()
    version = a.get('/version')['version']
    match = re.match(r'(\d+)\.(\d+)', version)
    require(match and tuple(map(int, match.groups())) >= (18, 11), 'Se requiere GitLab >=18.11 para cuentas nativas Free.')
    state = load() if (WORK / 'state.json').exists() else {'groups': {}, 'projects': {}, 'roles': {}, 'gitlab_version': version}
    require(not state.get('seed_complete'), 'Seed ya completado. No se reescriben identidades migradas. Usa status o sync-code.')
    for key, path, parent in [('root', 'migration-lab', None), ('artifacts', 'migration-lab/artifacts', 'root')]:
        if key in state['groups']:
            continue
        found = get_or_none(a, '/groups/' + quote(path, safe=''))
        if found:
            require(found['description'] == MARKER, 'Namespace existente fuera del laboratorio; operación detenida.')
        else:
            data = {'name': path.split('/')[-1], 'path': path.split('/')[-1], 'visibility': 'private', 'description': MARKER}
            if parent:
                data['parent_id'] = state['groups'][parent]
            found = a.request('POST', '/groups', data)
        state['groups'][key] = found['id']
        save(state)
    for key in ('automation', 'config', 'packages', 'deployment'):
        if key in state['projects']:
            continue
        group = 'artifacts' if key == 'packages' else 'root'
        path = f'migration-lab/{"artifacts/" if group == "artifacts" else ""}{key}'
        found = get_or_none(a, '/projects/' + quote(path, safe=''))
        if found:
            require(found['description'] == MARKER, 'Proyecto existente fuera del laboratorio; operación detenida.')
        else:
            found = a.request('POST', '/projects', {'name': key, 'path': key, 'namespace_id': state['groups'][group],
                              'visibility': 'private', 'description': MARKER, 'initialize_with_readme': True, 'default_branch': 'main'})
        state['projects'][key] = found['id']
        save(state)
    p = state['projects']
    grants = {'reader': [{'kind': 'projects', 'id': p['config'], 'access_level': 20}],
              'publisher': [{'kind': 'groups', 'id': state['groups']['artifacts'], 'access_level': 30},
                            {'kind': 'projects', 'id': p['automation'], 'access_level': 40}],
              'deployer': [{'kind': 'projects', 'id': p['deployment'], 'access_level': 40}]}
    for role in ROLES:
        info = state['roles'].setdefault(role, {'phase': 'seeded', 'grants': grants[role]})
        if 'legacy' not in info:
            username = f'lab-legacy-{role}'
            existing = a.pages('/users?' + urlencode({'username': username}))
            require(not existing, f'{username} ya existe sin estado local. Revisar antes de adoptar una identidad.')
            user = a.request('POST', '/users', {'username': username, 'name': f'{MARKER} {role}',
                          'email': username + '@example.invalid', 'password': secrets.token_urlsafe(32),
                          'skip_confirmation': True, 'projects_limit': 0})
            info['legacy'] = {'user_id': user['id'], 'username': user['username']}
            save(state)
        uid = info['legacy']['user_id']
        for item in grants[role]:
            grant(a, item, uid)
        if not creds().get(role, {}).get('legacy'):
            pat = issue_token(a, uid, f'migration-lab-{role}-legacy', SCOPES[role])
            values = creds()
            values.setdefault(role, {})['legacy'] = pat['token']
            save_creds(values)
            info['legacy']['token_id'] = pat['id']
            save(state)
        put_variable(a, p['automation'], role.upper() + '_TOKEN', token_for(role, 'legacy'), True)
        put_variable(a, p['automation'], 'EXPECTED_' + role.upper() + '_ID', uid)
    for key, val in [('CONFIG_PROJECT_ID', p['config']), ('PACKAGES_PROJECT_ID', p['packages'])]:
        put_variable(a, p['automation'], key, val)
    # An unprotected main is deliberate for the protected-variable fault exercise.
    protected = get_or_none(a, f"/projects/{p['automation']}/protected_branches/main")
    if protected:
        a.request('DELETE', f"/projects/{p['automation']}/protected_branches/main")
    file_endpoint = f"/projects/{p['config']}/repository/files/catalog.json"
    if get_or_none(a, file_endpoint + '?ref=main') is None:
        a.request('POST', file_endpoint, {'branch': 'main', 'content': json.dumps(DEFAULT_CATALOG), 'commit_message': 'Seed private catalog configuration'})
    if 'schedule_id' not in state:
        schedule = Client(BASE, token_for('publisher', 'legacy')).request('POST', f"/projects/{p['automation']}/pipeline_schedules", {
            'description': 'LAB ONLY - weekly validation (initially paused)', 'ref': 'main', 'cron': '0 6 * * 1',
            'cron_timezone': 'UTC', 'active': False})
        state['schedule_id'] = schedule['id']
        save(state)
    write_json(WORK / 'runtime/topology.json', {'deployment_project_id': p['deployment']})
    set_worker(state, token_for('reader', 'legacy'))
    state['seed_complete'] = True
    save(state)
    cmd_sync_code(args)
    event('seed_complete', gitlab_version=version)
    print('Creadas 3 identidades legacy, 4 proyectos, 2 grupos y un schedule pausado.')

def cmd_sync_code(args):
    state = load()
    pid = state['projects']['automation']
    a = admin()
    files = [ROOT / '.gitlab-ci.yml']
    for folder in ('lab', 'services', 'ci', 'tests'):
        files += sorted((ROOT / folder).rglob('*.py'))
    actions = []
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        existing = get_or_none(a, f'/projects/{pid}/repository/files/{quote(relative, safe="")}?ref=main')
        actions.append({'action': 'update' if existing else 'create', 'file_path': relative, 'content': path.read_text()})
    commit = a.request('POST', f'/projects/{pid}/repository/commits', {
        'branch': 'main', 'commit_message': 'Sync local migration lab source [skip ci]', 'actions': actions})
    state['source_commit'] = commit['id']
    state.pop('baseline', None)
    for info in state['roles'].values():
        if info['phase'] == 'validated':
            info['phase'] = 'switched'
        info.pop('validation', None)
    save(state)
    print('Código sincronizado al GitLab local; no es integración premium con GitHub.')

def set_worker(state, token):
    write_json(WORK / 'worker/config.json', {'project_id': state['projects']['config'], 'token': token})

def cmd_runner(args):
    state = load()
    path = WORK / 'runner/config.toml'
    if path.exists():
        print('Runner ya configurado. Usa docker compose --profile ci up -d runner.')
        return
    require(not state.get('runner_id'), 'Runner creado sin config local. Revísalo antes de crear otro.')
    result = admin().request('POST', '/user/runners', {'runner_type': 'project_type',
          'project_id': state['projects']['automation'], 'description': 'LOCAL migration lab',
          'tag_list': 'migration-lab', 'run_untagged': False, 'locked': True, 'access_level': 'not_protected'})
    configuration = f'''concurrent = 1
check_interval = 3
[[runners]]
  name = "migration-lab"
  url = "http://gitlab.lab:8929"
  token = {json.dumps(result['token'])}
  executor = "docker"
  [runners.docker]
    image = "python:3.12-slim"
    privileged = false
    network_mode = "gitlab-migration-lab-net"
    volumes = ["/cache"]
    pull_policy = "if-not-present"
    allowed_pull_policies = ["if-not-present"]
'''
    atomic_write(path, configuration)
    state['runner_id'] = result['id']
    save(state)
    print('Runner configurado con authentication token. No se usa registration token legado.')

def inventory(state, uid):
    a = admin()
    direct = []
    effective = []
    for kind in ('groups', 'projects'):
        for name, rid in state[kind].items():
            membership = get_or_none(a, f'/{kind}/{rid}/members/{uid}')
            if membership:
                require(not membership.get('member_role_id'), 'Rol personalizado fuera de alcance; requiere revisión manual.')
                direct.append({'kind': kind, 'id': rid, 'name': name, 'access_level': membership['access_level'], 'expires_at': membership.get('expires_at')})
            member = get_or_none(a, f'/{kind}/{rid}/members/all/{uid}')
            effective.append({'kind': kind, 'id': rid, 'name': name, 'access_level': member['access_level'] if member else 0,
                              'expires_at': member.get('expires_at') if member else None})
    pats = a.pages('/personal_access_tokens?' + urlencode({'user_id': uid}))
    return {'direct': direct, 'effective': effective,
            'tokens': [{k: t.get(k) for k in ('id', 'name', 'scopes', 'expires_at', 'active', 'revoked', 'last_used_at')} for t in pats]}

def cmd_inventory(args):
    state = load()
    data = {'at': now(), 'scope': 'Only the seeded lab namespace, NOT an instance-wide discovery', 'roles': {}}
    for role, info in state['roles'].items():
        side = active_side(info)
        data['roles'][role] = {'side': side, 'user_id': info[side]['user_id'], **inventory(state, info[side]['user_id'])}
    write_json(WORK / 'reports/inventory.json', data)
    print(json.dumps(data, indent=2))


def ensure_idle(state, allow_fault=False):
    a = admin()
    pid = state['projects']['automation']
    pipelines = a.pages(f'/projects/{pid}/pipelines')
    require(all(p['status'] in TERMINAL for p in pipelines), 'Hay pipelines no terminados: espera o resuélvelos antes de cambiar credenciales.')
    schedules = a.pages(f'/projects/{pid}/pipeline_schedules')
    require(all(not s['active'] for s in schedules), 'Pausa los schedules durante la ventana de migración.')
    require(allow_fault or not (WORK / 'fault.json').exists(), 'Repara el fallo inyectado antes de migrar.')


def ensure_exclusive(state, role):
    for other, info in state['roles'].items():
        if other != role:
            require(info['phase'] in ('seeded', 'retired'), f'Completa o revierte primero {other}. Se migra una cuenta a la vez.')


def worker_check(state, timeout=30):
    deadline = time.monotonic() + timeout
    expected = state['roles']['reader'][active_side(state['roles']['reader'])]['user_id']
    while time.monotonic() < deadline:
        path = WORK / 'runtime/worker-status.json'
        if path.exists():
            status = read_json(path)
            if status.get('ok') and status.get('user_id') == expected and 0 <= time.time() - status.get('checked_at', 0) < 15:
                return status
        time.sleep(2)
    raise ValueError('Worker no válido: revisa config-sync, token externo, identidad efectiva y frescura.')


def run_pipeline(state):
    a = admin()
    pid = state['projects']['automation']
    pipeline = a.request('POST', f'/projects/{pid}/pipeline', {'ref': 'main'})
    print(f'Pipeline local {pipeline["id"]}: iniciado.', flush=True)
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        detail = a.get(f'/projects/{pid}/pipelines/{pipeline["id"]}')
        if detail['status'] in TERMINAL:
            report = {'at': now(), 'pipeline_id': detail['id'], 'status': detail['status'], 'sha': detail['sha'],
                      'jobs': [{k: j.get(k) for k in ('id', 'name', 'status')} for j in a.pages(f'/projects/{pid}/pipelines/{detail["id"]}/jobs')]}
            write_json(WORK / f'reports/pipeline-{detail["id"]}.json', report)
            require(detail['status'] == 'success', f'Pipeline {detail["id"]} terminó {detail["status"]}. Revisa jobs en GitLab; no se retiró acceso.')
            return report
        time.sleep(4)
    raise ValueError('Timeout esperando pipeline; inspecciona runner/jobs. No se canceló ni se retiró acceso automáticamente.')


def cmd_baseline(args):
    state = load()
    ensure_idle(state, allow_fault=True)
    report = run_pipeline(state)
    report['worker'] = worker_check(state)
    state['baseline'] = report
    save(state)
    print('Baseline correcta: pipeline y automatización externa.')


def cmd_prepare(args):
    state = load()
    role = args.role
    info = state['roles'][role]
    ensure_idle(state)
    ensure_exclusive(state, role)
    require(info['phase'] in ('seeded', 'prepared'), 'Prepare solo se admite antes del cutover.')
    require(state.get('baseline', {}).get('status') == 'success', 'Ejecuta baseline primero.')
    a = admin()
    if info['phase'] == 'seeded':
        info['before'] = inventory(state, info['legacy']['user_id'])
        save(state)
    if 'native' not in info:
        user = a.request('POST', f"/groups/{state['groups']['root']}/service_accounts", {
                  'name': f'LAB native {role}', 'username': f'lab-native-{role}'})
        info['native'] = {'user_id': user['id'], 'username': user['username']}
        save(state)
    uid = info['native']['user_id']
    # A genuine native service account must be returned by this endpoint.
    a.get(f"/groups/{state['groups']['root']}/service_accounts/{uid}")
    for item in info['before']['direct']:
        grant(a, item, uid)
    if not creds().get(role, {}).get('native'):
        pat = issue_token(a, uid, f'migration-lab-{role}-native', SCOPES[role], state['groups']['root'])
        values = creds()
        values[role]['native'] = pat['token']
        save_creds(values)
        info['native']['token_id'] = pat['id']
        save(state)
    after = inventory(state, uid)
    require(after['direct'] == info['before']['direct'] and after['effective'] == info['before']['effective'],
            'Diferencia de permisos; revisar membresías directas, heredadas y expiración.')
    info['phase'] = 'prepared'
    save(state)
    event('prepared', role=role, native_user_id=uid)
    print(f'{role}: cuenta nativa preparada; consumidores siguen usando legacy.')


def snapshot_variables(a, pid, role):
    return {key: a.get(variable_path(pid, key)) for key in (role.upper() + '_TOKEN', 'EXPECTED_' + role.upper() + '_ID')}


def cmd_cutover(args):
    state = load()
    role = args.role
    info = state['roles'][role]
    ensure_exclusive(state, role)
    ensure_idle(state)
    require(info['phase'] == 'prepared', 'Ejecuta prepare, o rollback si un cutover anterior quedó parcial.')
    require(args.owner.strip() and args.ticket.strip(), 'Se requiere owner y ticket para dejar trazabilidad de la práctica.')
    pid = state['projects']['automation']
    a = admin()
    backup = {'variables': snapshot_variables(a, pid, role), 'role': role}
    write_json(WORK / f'backups/{role}.json', backup)
    info.update(phase='switching', ticket=args.ticket, owner=args.owner, cutover_at=now())
    info.pop('validation', None)
    save(state)  # Durable checkpoint BEFORE the first credential swap.
    put_variable(a, pid, role.upper() + '_TOKEN', token_for(role, 'native'), True)
    put_variable(a, pid, 'EXPECTED_' + role.upper() + '_ID', info['native']['user_id'])
    if role == 'reader':
        set_worker(state, token_for(role, 'native'))
    if role == 'publisher':
        Client(BASE, token_for(role, 'native')).request('POST', f'/projects/{pid}/pipeline_schedules/{state["schedule_id"]}/take_ownership')
    info['phase'] = 'switched'
    save(state)
    event('cutover', role=role, ticket=args.ticket, owner=args.owner)
    print(f'{role}: cutover realizado. Token legacy aún válido; ejecuta validate o rollback.')


def verify_permissions_and_schedule(state, role):
    info = state['roles'][role]
    actual = inventory(state, info['native']['user_id'])
    require(actual['direct'] == info['before']['direct'] and actual['effective'] == info['before']['effective'],
            'Los permisos actuales no coinciden con el inventario aprobado.')
    if role == 'publisher':
        schedule = admin().get(f"/projects/{state['projects']['automation']}/pipeline_schedules/{state['schedule_id']}")
        require(schedule['owner']['id'] == info['native']['user_id'], 'El schedule aún pertenece a otra identidad.')


def cmd_validate(args):
    state = load()
    role = args.role
    info = state['roles'][role]
    require(info['phase'] in ('switched', 'validated'), 'Validate requiere un cutover completado.')
    ensure_idle(state)
    verify_permissions_and_schedule(state, role)
    report = run_pipeline(state)
    report['worker'] = worker_check(state)
    info.update(phase='validated', validation=report)
    save(state)
    event('validated', role=role, pipeline_id=report['pipeline_id'])
    print(f'{role}: validación positiva; pipeline, permisos, worker y ownership aplicable.')


def restore_variables(a, pid, snapshot):
    for key, var in snapshot.items():
        payload = {field: var[field] for field in VARIABLE_FIELDS if field in var}
        a.request('PUT', variable_path(pid, key), payload)


def cmd_rollback(args):
    state = load()
    role = args.role
    info = state['roles'][role]
    require(info['phase'] in ('switching', 'switched', 'validated', 'rolling_back'), 'No hay cutover reversible; después de retirar acceso usa recuperación hacia adelante.')
    ensure_idle(state)
    a = admin()
    Client(BASE, token_for(role, 'legacy')).get('/user')
    pid = state['projects']['automation']
    info['phase'] = 'rolling_back'
    save(state)
    restore_variables(a, pid, read_json(WORK / f'backups/{role}.json')['variables'])
    if role == 'reader':
        set_worker(state, token_for(role, 'legacy'))
    if role == 'publisher':
        Client(BASE, token_for(role, 'legacy')).request('POST', f'/projects/{pid}/pipeline_schedules/{state["schedule_id"]}/take_ownership')
    run_pipeline(state)
    worker_check(state)
    revoke(a, info['native']['token_id'])
    for item in info['before']['direct']:
        delete_membership(a, item, info['native']['user_id'])
    values = creds()
    values[role].pop('native', None)
    save_creds(values)
    info['native'].pop('token_id', None)
    info.pop('validation', None)
    info['phase'] = 'seeded'
    save(state)
    (WORK / f'backups/{role}.json').unlink(missing_ok=True)
    event('rolled_back', role=role)
    print('Legacy restaurado y validado; nuevo PAT revocado. Cuenta nativa conservada sin permisos.')


def revoke(a, token_id):
    value = a.get(f'/personal_access_tokens/{token_id}')
    if not value['revoked']:
        a.request('DELETE', f'/personal_access_tokens/{token_id}')


def delete_membership(a, item, uid):
    endpoint = f"/{item['kind']}/{item['id']}/members/{uid}"
    if get_or_none(a, endpoint):
        a.request('DELETE', endpoint)


def cmd_retire(args):
    state = load()
    role = args.role
    info = state['roles'][role]
    require(info['phase'] in ('validated', 'retiring'), 'Retire exige validación completa previa.')
    require(args.confirm == role, f'Confirmación irreversible: --confirm {role}')
    ensure_idle(state)
    a = admin()
    uid = info['legacy']['user_id']
    user = a.get(f'/users/{uid}')
    require(uid != 1 and user['username'] == f'lab-legacy-{role}', 'Identidad fuera del laboratorio; retiro bloqueado.')
    if info['phase'] == 'validated':
        verify_permissions_and_schedule(state, role)
        pre = run_pipeline(state)
        worker_check(state)
        tokens = a.pages('/personal_access_tokens?' + urlencode({'user_id': uid}))
        require(all(t['id'] == info['legacy']['token_id'] or not t['active'] for t in tokens),
                'Hay PAT adicionales no inventariados: revisa su ownership antes de retirarlos.')
        require(not a.pages(f'/users/{uid}/keys'), 'Hay SSH keys no incluidas en el plan; amplía inventario.')
        impersonation = a.pages(f'/users/{uid}/impersonation_tokens')
        require(not any(t.get('active', not t.get('revoked', True)) for t in impersonation), 'Hay impersonation tokens fuera del plan.')
        info.update(phase='retiring', retirement_started_at=now(), pre_retirement_pipeline=pre['pipeline_id'])
        save(state)
    # No automatic rollback past this boundary: revocation is irreversible.
    revoke(a, info['legacy']['token_id'])
    if user['state'] != 'blocked':
        a.request('POST', f'/users/{uid}/block')
    for item in info['before']['direct']:
        delete_membership(a, item, uid)
    try:
        Client(BASE, token_for(role, 'legacy')).get('/user')
    except APIError as exc:
        require(exc.status in (401, 403), 'La prueba negativa no demuestra revocación: revisar conectividad.')
        denied_status = exc.status
    else:
        raise ValueError('El token legacy sigue autenticando. No cerrar la migración.')
    remaining = inventory(state, uid)
    require(not remaining['direct'] and all(item['access_level'] == 0 for item in remaining['effective']), 'Quedan accesos legacy en el namespace.')
    report = run_pipeline(state)
    report['worker'] = worker_check(state)
    report.update(role=role, old_token_http_status=denied_status, old_user_blocked=True,
                  legacy_user_id=uid, native_user_id=info['native']['user_id'], ticket=info['ticket'], owner=info['owner'])
    info.update(phase='retired', closed_at=now(), retirement_report=report)
    save(state)
    values = creds()
    values[role].pop('legacy', None)
    save_creds(values)
    (WORK / f'backups/{role}.json').unlink(missing_ok=True)
    write_json(WORK / f'reports/closed-{role}.json', report)
    event('retired', role=role, denied_status=denied_status, pipeline_id=report['pipeline_id'])
    print(f'{role}: retirado. PAT antiguo rechazado, usuario bloqueado, permisos removidos y pipeline nuevo correcto.')


def cmd_status(args):
    state = load()
    print('GitLab:', state['gitlab_version'])
    for role, info in state['roles'].items():
        print(f"{role:12} {info['phase']:14} legacy={info['legacy']['user_id']} native={info.get('native', {}).get('user_id', '-')}")
    print('Fallo inyectado pendiente:', (WORK / 'fault.json').exists())


def cmd_probe(args):
    state = load()
    info = state['roles'][args.role]
    side = args.side if args.side != 'active' else active_side(info)
    require(side in creds().get(args.role, {}), 'Esta credencial no existe localmente o ya fue retirada.')
    c = Client(BASE, token_for(args.role, side))
    user = c.get('/user')
    project = state['projects'][{'reader': 'config', 'publisher': 'packages', 'deployer': 'deployment'}[args.role]]
    c.get(f'/projects/{project}')
    print(json.dumps({'user_id': user['id'], 'project_id': project, 'authentication': 'ok', 'read_project': 'ok'}))
    print('Esto NO prueba publicar/desplegar; validate ejecuta esas operaciones reales.')


def cmd_fault(args):
    state = load()
    ensure_idle(state)
    role = args.role
    info = state['roles'][role]
    require(info['phase'] not in ('switching', 'rolling_back', 'retiring'), 'Resuelve primero la operación parcial.')
    side = active_side(info)
    a = admin()
    pid = state['projects']['automation']
    key = role.upper() + '_TOKEN'
    fault = {'role': role, 'kind': args.kind, 'side': side, 'uid': info[side]['user_id'],
             'variable': a.get(variable_path(pid, key))}
    if args.kind == 'missing-membership':
        fault['grant'] = inventory(state, fault['uid'])['direct'][0]
    if args.kind == 'stale-worker':
        require(role == 'reader', 'stale-worker solo aplica a reader.')
        fault['worker'] = read_json(WORK / 'worker/config.json')
    write_json(WORK / 'fault.json', fault)  # Recovery record BEFORE mutation.
    if info['phase'] == 'validated':
        info['phase'] = 'switched'
    info.pop('validation', None)
    save(state)
    if args.kind == 'invalid-token':
        put_variable(a, pid, key, 'LAB-INVALID-CREDENTIAL-DO-NOT-USE', True)
    elif args.kind == 'protected-variable':
        a.request('PUT', variable_path(pid, key), {'protected': True})
    elif args.kind == 'wrong-scope':
        pat = issue_token(a, fault['uid'], 'LAB-fault-read-user-only', ['read_user'])
        fault['temporary_token_id'] = pat['id']
        write_json(WORK / 'fault.json', fault)
        put_variable(a, pid, key, pat['token'], True)
    elif args.kind == 'missing-membership':
        delete_membership(a, fault['grant'], fault['uid'])
    elif args.kind == 'stale-worker':
        set_worker(state, 'LAB-INVALID-CREDENTIAL-DO-NOT-USE')
    event('fault_injected', role=role, kind=args.kind)
    print('Fallo inyectado. Ejecuta baseline para observar el fallo; repair revierte solo esta inyección.')


def cmd_repair(args):
    require((WORK / 'fault.json').exists(), 'No hay una inyección pendiente.')
    state = load()
    fault = read_json(WORK / 'fault.json')
    a = admin()
    pid = state['projects']['automation']
    # Existing pipelines keep their old environment. Do not cancel them silently.
    require(all(p['status'] in TERMINAL for p in a.pages(f'/projects/{pid}/pipelines')), 'Espera que terminen los pipelines del ejercicio.')
    if fault['kind'] == 'missing-membership':
        grant(a, fault['grant'], fault['uid'])
    elif fault['kind'] == 'stale-worker':
        write_json(WORK / 'worker/config.json', fault['worker'])
    else:
        restore_variables(a, pid, {fault['role'].upper() + '_TOKEN': fault['variable']})
    if fault.get('temporary_token_id'):
        revoke(a, fault['temporary_token_id'])
    (WORK / 'fault.json').unlink()
    event('fault_repaired', role=fault['role'], kind=fault['kind'])
    print('Inyección revertida. Ejecuta baseline/validate nuevamente; no se asume recuperación sin probar.')


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    for command in ('init', 'doctor', 'auth', 'seed', 'sync-code', 'runner', 'inventory', 'baseline', 'status', 'repair'):
        sub.add_parser(command)
    wait = sub.add_parser('wait')
    wait.add_argument('--timeout', type=int, default=1200)
    for command in ('prepare', 'cutover', 'validate', 'rollback', 'retire', 'probe'):
        item = sub.add_parser(command)
        item.add_argument('role', choices=ROLES)
        if command == 'cutover':
            item.add_argument('--ticket', required=True)
            item.add_argument('--owner', required=True)
        if command == 'retire':
            item.add_argument('--confirm', required=True)
        if command == 'probe':
            item.add_argument('--side', choices=('active', 'legacy', 'native'), default='active')
    fault = sub.add_parser('fault')
    fault.add_argument('kind', choices=('invalid-token', 'wrong-scope', 'missing-membership', 'stale-worker', 'protected-variable'))
    fault.add_argument('--role', choices=ROLES, required=True)
    return p


def main():
    args = parser().parse_args()
    os.umask(0o077)
    WORK.mkdir(exist_ok=True, mode=0o700)
    with (WORK / 'operation.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Otra operación local está en curso; no se inició ninguna modificación.')
        try:
            globals()['cmd_' + args.command.replace('-', '_')](args)
        except (APIError, ValueError, KeyError, FileNotFoundError) as exc:
            print(f'ERROR: {exc}', file=sys.stderr)
            raise SystemExit(1)
        except subprocess.CalledProcessError:
            print('ERROR: comando Docker falló. No se imprime su salida capturada para evitar revelar credenciales.', file=sys.stderr)
            raise SystemExit(1)

if __name__ == '__main__':
    main()
