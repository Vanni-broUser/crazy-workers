# Crazy Workers — Piano di evoluzione verso il modello "daemon riconciliatore"

> Documento di design e piano operativo. Copre la libreria `crazy-workers` e i
> due progetti che la consumano: **lotec-be** (worker come job di backend) e
> **generic-deploy** (worker come daemon di amministrazione della macchina).
>
> Stato: proposta. Versione libreria di riferimento: **1.3.0**
> (`generic-lab/crazy-workers`). Le altre copie su disco (es. `lotec/crazy-workers`)
> sono obsolete e vanno rimosse — vedi §9.

---

## 1. Indice

1. Indice
2. Contesto e obiettivo
3. I due casi d'uso e perché divergono
4. Causa radice unica
5. Catalogo delle criticità attuali
6. Principi di design della soluzione
7. Architettura target: daemon riconciliatore (control plane / data plane)
8. Il vincolo di località dei processi (perché "un container per tutti" non basta)
9. Piano per fasi (panoramica)
10. Fase C — cablaggio coerente (quick wins)
11. Fase A — daemon riconciliatore
12. Modifiche dettagliate: libreria `crazy-workers`
13. Modifiche dettagliate: `lotec-be`
14. Modifiche dettagliate: `generic-deploy`
15. Migrazioni di schema
16. Strategia di test
17. Sequenza di rollout e rollback
18. Decisioni di design e alternative scartate
19. Checklist operativa
20. Appendice: mappa file → modifica

---

## 2. Contesto e obiettivo

`crazy-workers` è una libreria Python che gestisce processi worker in background
(script `.py`) con stato persistente, recovery automatico e una CLI. Oggi viene
usata in due contesti molto diversi:

- **lotec-be** — backend Flask/gunicorn. I worker sono job applicativi: recorder
  ffmpeg (`register`), `renamer`, `convert`, `backup`. Lo stato è **co-locato in
  PostgreSQL** (engine condiviso con `database_api`).
- **generic-deploy** — provisioning Ansible di macchine. I worker sono daemon che
  **amministrano l'host** (watcher, sync git, ecc.). Lo stato è un **SQLite
  locale** in `~/crazy-workers/.service/`.

**Obiettivo:** trovare una soluzione *trasversale* che renda il comportamento
uniforme, prevedibile e lineare in entrambi i contesti, eliminando alla radice
le incoerenze odierne anziché tamponare i singoli sintomi.

---

## 3. I due casi d'uso e perché divergono

| Aspetto | lotec-be (backend) | generic-deploy (macchina) |
|---|---|---|
| Natura del worker | job applicativo (ffmpeg, recorder) | daemon che amministra l'host |
| Dove **deve** girare il processo | nel contesto app (volume + ffmpeg) | **sull'host** |
| Store di stato | PostgreSQL condiviso | SQLite locale |
| Chi avvia | API HTTP (`/worker/...`) | CLI via Ansible |
| Chi fa recovery | gunicorn `on_starting` (`auto_recover=True`) | hook di boot systemd-user + linger |
| Numero di "supervisori" a runtime | **N** (un `WorkerManager` per worker gunicorn) | 1 (CLI episodica) + hook di boot |

La libreria viene istanziata in modo **embedded** e **indipendente** da ciascun
entry point. Ogni `WorkerManager` è insieme control plane, store e supervisore di
processi. Con più chiamanti (API + CLI + boot) si ottengono supervisori multipli e
non coordinati.

---

## 4. Causa radice unica

> **Tutte le criticità derivano dal fatto che `crazy-workers` mescola tre
> responsabilità in un singolo oggetto embedded, istanziato in modo incoerente da
> ogni chiamante.**

Le tre responsabilità:

1. **Control plane** — chi impartisce gli ordini (start/stop/list).
2. **State store** — dove vivono i record dei worker.
3. **Process supervisor** — chi possiede davvero i processi OS (li spawna, li
   sorveglia, li riavvia).

Finché "chi chiama `start_worker`" coincide con "chi possiede il processo" e con
"chi scrive lo stato", ogni entry point diventa un sistema a sé. L'unica cosa
condivisa è il DB — e infatti è lì che nascono le rotture (CLI su SQLite vs
backend su Postgres).

La cura non è sistemare i singoli cablaggi, ma **separare il control plane/stato
dal supervisore**, e fare in modo che esista **un solo supervisore per contesto**,
con il **DB come unica fonte di verità**.

---

## 5. Catalogo delle criticità attuali

Riferimenti file relativi al repo `generic-lab/crazy-workers` salvo diversa
indicazione.

### Backend (lotec-be)

- **B1 — CLI e backend usano database diversi** 🔴
  L'API costruisce `WorkerManager(engine=database_api.engine, ...)` → PostgreSQL.
  La CLI (`crazy_workers/cli/main.py`) costruisce `WorkerManager(workers_dir,
  create_dir=False, auto_recover=False)` **senza engine/db_url** → ricade su
  SQLite locale (`_initialize_storage` in `core/manager/__init__.py`). La CLI non
  vede i worker del backend e viceversa. Nessun modo (env/flag) di puntare la CLI
  al DB condiviso.

- **B2 — `auto_boot=True` attivo ma inefficace** 🔴
  `lotec-be/src/__init__.py:init_worker_manager` non passa `auto_boot=False`
  (default `True`). Ogni `start_worker` invoca `ensure_boot_restore`
  (`core/manager/starter.py:_ensure_boot_restore`), che installa un hook
  systemd-user/scheduled task il cui `ExecStart` esegue `python -m
  crazy_workers.boot` **senza engine → recupera dal DB sbagliato** (SQLite). In
  container Docker non esiste user-bus systemd: l'install fallisce e logga
  warning. Il recovery reale del backend è già garantito da `auto_recover=True` in
  `gunicorn_config.py:on_starting`.

- **B3 — I worker re-importano l'intera app Flask** 🟡
  `lotec-be/src/workers/register.py` fa `from .. import DATABASE_URL`, che esegue
  tutto `src/__init__.py` (CORS, blueprint, Swagger) solo per leggere una URL.
  Pesante e fragile.

- **B4 — `worker_key` fissi per convert/backup** 🟡
  `lotec-be/src/end_points/worker/__init__.py` usa `worker_key='convert'` e
  `'backup'`. Una seconda richiesta concorrente viene scartata silenziosamente
  ("already running").

### Macchina (generic-deploy)

- **G1 — Pin di versione errato** 🟠
  `ansible/settings/common/crazy_workers.yml` installa `crazy-workers>=1.2.0`, ma
  l'intero flusso si appoggia al boot-restore (feature 1.3.0). Rischio di
  installare una 1.2.x senza modulo `boot/`.

- **G2 — Dipendenza da systemd-user + linger** 🟡
  Il restore parte solo con linger abilitato e `/run/user/<uid>` presente; senza
  linger gira al login, non al boot.

### Trasversali

- **T1 — Due checkout divergenti di crazy-workers** 🟠 (`lotec/crazy-workers`
  vecchio vs `generic-lab/crazy-workers` 1.3.0).
- **T2 — La CLI riscrive il `.env` della cwd** 🟡 (`cli/discovery.py:save_to_env`).
- **T3 — `clear_state` non gira allo stop su Windows** 🟡
  (`lotec-be/src/services/register/recorder.py` usa `signal.SIGTERM`, non invocato
  da `TerminateProcess`). Solo in sviluppo locale Windows.

---

## 6. Principi di design della soluzione

1. **Una sola fonte di verità a runtime: il DB.** Lo stato desiderato e lo stato
   osservato vivono entrambi nel DB condiviso del contesto.
2. **Un solo supervisore per contesto.** Un unico processo possiede i worker, fa
   spawn/stop/recovery. Nessun altro tocca i processi OS.
3. **Tutti gli altri sono client.** API, CLI, script: scrivono solo *desiderio*
   nel DB; non spawnano nulla.
4. **Il packaging del supervisore varia, il codice no.** Sidecar container per
   lotec-be, systemd service per generic-deploy: stesso daemon.
5. **Retrocompatibilità.** La modalità embedded attuale resta valida per chi usa
   un singolo processo (test, script monolitici).

---

## 7. Architettura target: daemon riconciliatore (control plane / data plane)

Pattern operator/Kubernetes: **desired state vs actual state**, riconciliati da
un loop.

```
            ┌──────────────────────────────────────────────┐
            │                   DB condiviso                │
            │  tabella workers:                             │
            │   - spec:  worker_type, parameters            │
            │   - desired_status   (scritto dai CLIENT)     │
            │   - status (actual), pid (scritti dal DAEMON) │
            └──────────────────────────────────────────────┘
                 ▲ scrive desiderio        ▲ scrive stato reale
                 │                          │  + possiede i processi
   ┌─────────────┴───────────┐   ┌──────────┴───────────────────────┐
   │   CLIENT (control plane)│   │  DAEMON RICONCILIATORE (1 per     │
   │   - API HTTP lotec-be   │   │  contesto, data plane)            │
   │   - CLI crazy-workers   │   │  loop: per ogni worker            │
   │   - script Ansible      │   │    (desired vs alive) → start/stop│
   │   request_start/stop    │   │  + recovery + backoff             │
   └─────────────────────────┘   └──────────────┬───────────────────┘
                                                 │ spawn/terminate
                                          ┌──────┴───────┐
                                          │ processi OS  │
                                          │ (ffmpeg, …)  │
                                          └──────────────┘
```

**Tabella di riconciliazione** (eseguita a intervallo dal daemon):

| `desired_status` | processo vivo? | azione |
|---|---|---|
| RUNNING | no | **start** (con backoff se crash recente) |
| RUNNING | sì | noop |
| STOPPED | sì | **stop** |
| STOPPED | no | noop |

Proprietà che ne derivano:

- **B1 risolto**: la CLI scrive lo stesso DB → vede lo stesso stato. Le serve solo
  `CRAZY_WORKERS_DB_URL`.
- **B2 risolto**: "boot" = systemd avvia il daemon, che riconcilia. Niente hook
  per-utente fragili.
- **Niente duplicazione gunicorn**: i web worker non spawnano più nulla.
- **Recovery = caso particolare della riconciliazione** (desired RUNNING + pid
  morto → restart). `recover_workers()` diventa "un singolo giro di reconcile".

---

## 8. Il vincolo di località dei processi

La domanda "e se crazy-workers diventa un servizio dockerizzato separato?" è
giusta nello spirito, ma **il container è il packaging, non l'architettura**:

- I worker di **generic-deploy amministrano l'host**. Un container è isolato
  dall'host che dovrebbe gestire → containerizzarli li rompe. Devono girare come
  processi dell'host (il daemon è un **systemd service**).
- I worker di **lotec-be** sono job applicativi: il daemon può essere un
  **sidecar container** con ffmpeg + volume registrazioni + accesso a Postgres.

Quindi ciò che è uniforme è il **daemon** (stesso codice, stessa interfaccia DB);
cambia solo l'unità di deploy. Non esiste "un solo container per tutti i
contesti", ma esiste "un solo daemon per tutti i contesti".

---

## 9. Piano per fasi (panoramica)

- **Fase C — cablaggio coerente (quick wins).** Nessun daemon. Rende il DB l'unica
  fonte di verità *senza* riconciliatore: `CRAZY_WORKERS_DB_URL` per la CLI,
  `auto_boot=False` dove c'è già un supervisore, pulizia residui. Risolve i bug di
  *coerenza* (B1, B2, T1, T2). Poche ore, basso rischio. Fondamenta per A.
- **Fase A — daemon riconciliatore.** Introduce `desired_status`, il reconcile
  loop, il `WorkerClient`, il daemon entrypoint. Unifica davvero i contesti.

Si consiglia di rilasciare **C prima**, in produzione, e costruire **A** sopra.

---

## 10. Fase C — cablaggio coerente (quick wins)

### C.1 — Libreria: la CLI può puntare a un DB condiviso

`crazy_workers/cli/main.py`: leggere `CRAZY_WORKERS_DB_URL` e propagarla.

```python
import os
...
db_url = os.environ.get('CRAZY_WORKERS_DB_URL')
with WorkerManager(
  workers_dir,
  create_dir=False,
  auto_recover=False,
  auto_boot=False,
  db_url=db_url,            # se None → comportamento attuale (SQLite locale)
  create_tables=db_url is None,  # con DB condiviso/owned, non emettere DDL
) as manager:
  ...
```

`crazy_workers/cli/discovery.py`: quando `CRAZY_WORKERS_DB_URL` è impostata, la
`workers_dir` serve solo a localizzare gli script `.py` e i log; va comunque
risolta, ma il prompt interattivo non deve scrivere nel `.env` applicativo (vedi
T2). Aggiungere un branch che, in presenza di `CRAZY_WORKERS_DB_URL`, **non**
chiama `save_to_env`.

### C.2 — lotec-be: disattivare auto_boot e (opzionale) abilitare la CLI

`lotec-be/src/__init__.py:init_worker_manager`:

```python
worker_manager = WorkerManager(
  WORKERS_DIR,
  engine=database_api.engine,
  worker_env={'DATABASE_URL': database_url or DATABASE_URL},
  create_tables=create_tables,
  auto_boot=False,   # il recovery è già garantito da auto_recover in gunicorn
)
```

Per usare la CLI sul box di deploy:
`CRAZY_WORKERS_DB_URL=postgresql://…/lotec_be crazy-workers --workers-dir
/app/src/workers status`.

### C.3 — lotec-be: pulizia residui

- Rimuovere la cartella `workers/` nella root del repo (vuota, con `.service`
  scollegato) e aggiungerla a `.gitignore` insieme a `**/.service/`.

### C.4 — generic-deploy: pin di versione

`ansible/settings/common/crazy_workers.yml`: `crazy-workers>=1.3.0`.

### C.5 — T2: CLI e `.env`

Vedi C.1: non riscrivere il `.env` quando si opera con `CRAZY_WORKERS_DB_URL`.

---

## 11. Fase A — daemon riconciliatore

### A.1 — Modello di stato

Separare nettamente **desiderio** (scritto dai client) da **osservato** (scritto
dal daemon):

- `desired_status` ∈ {RUNNING, STOPPED} — **client-owned**.
- `status` (actual) ∈ {STARTING, RUNNING, STOPPED, CRASHED} — **daemon-owned**.
- `pid`, `last_started_at`, `last_stopped_at` — **daemon-owned**.
- Campi di backoff: `restart_count`, `last_exit_at` — **daemon-owned**.

`worker_type` e `parameters` restano la "spec": il client li imposta insieme a
`desired_status=RUNNING`.

### A.2 — Reconcile loop

Un loop a intervallo (`interval` configurabile, default ~2s) che per ogni worker
applica la tabella di riconciliazione del §7, con backoff esponenziale sui crash
per evitare hot-restart.

### A.3 — Single-instance

Un solo daemon per `workers_dir`/DB, garantito con lo stesso meccanismo di
`RecoveryLock` (`core/recovery.py`) ma su un file `.service/daemon.lock`, oppure
con un advisory lock applicativo sul DB.

### A.4 — Client

I chiamanti usano un `WorkerClient` che tocca **solo** il DB:

```python
client = WorkerClient(engine=...)          # o db_url=...
client.request_start('register', worker_key='42', parameters={'device_id': 42})
client.request_stop('42')
client.list()
```

`request_start` fa un upsert del record con `desired_status=RUNNING` + spec;
`request_stop` imposta `desired_status=STOPPED`. Nessun processo spawnato.

---

## 12. Modifiche dettagliate: libreria `crazy-workers`

### 12.1 — Schema (`crazy_workers/database/schema.py`)

```python
class WorkerStatus(enum.Enum):
  NEVER_STARTED = 'NEVER_STARTED'
  STARTING = 'STARTING'
  RUNNING = 'RUNNING'
  STOPPED = 'STOPPED'
  CRASHED = 'CRASHED'


class DesiredStatus(enum.Enum):
  RUNNING = 'RUNNING'
  STOPPED = 'STOPPED'


class Worker(Base):
  __tablename__ = 'workers'

  id = Column(Integer, primary_key=True)
  worker_key = Column(String(255), unique=True, nullable=False)
  worker_type = Column(String(255), nullable=False)
  parameters = Column(JSON, nullable=False, default={})

  # Desiderio (client-owned)
  desired_status = Column(Enum(DesiredStatus), nullable=False, default=DesiredStatus.STOPPED)

  # Osservato (daemon-owned)
  pid = Column(Integer, nullable=True)
  status = Column(Enum(WorkerStatus), default=WorkerStatus.STOPPED)
  restart_count = Column(Integer, nullable=False, default=0)
  last_exit_at = Column(DateTime, nullable=True)
  last_started_at: datetime = Column(DateTime, nullable=True)
  last_stopped_at: datetime = Column(DateTime, nullable=True)
  created_at = Column(DateTime, server_default=func.now())
  updated_at = Column(DateTime, onupdate=func.now())
```

> Per i consumatori che **possiedono lo schema** (lotec-be con `create_tables=False`)
> le colonne vanno aggiunte tramite migrazione del progetto (vedi §15). Per la
> modalità self-contained (SQLite) `create_all` le crea da sé.

### 12.2 — Nuovo modulo daemon (`crazy_workers/daemon/`)

`crazy_workers/daemon/reconciler.py`:

```python
import logging
import time
from datetime import datetime, timedelta, timezone

from ..database.schema import DesiredStatus, Worker, WorkerStatus


logger = logging.getLogger('crazy_workers')

_BACKOFF_BASE_SECONDS = 1
_BACKOFF_MAX_SECONDS = 60


class Reconciler:
  """Single-owner loop: drives actual worker state toward desired state.

  Owns every worker process for one workers_dir/DB. Clients never spawn; they
  only set desired_status in the shared DB and this loop makes it so.
  """

  def __init__(self, manager, interval=2.0):
    self.manager = manager
    self.interval = interval
    self._stop = False

  def run_forever(self):
    logger.info('Reconciler started (interval=%ss)', self.interval)
    while not self._stop:
      try:
        self.reconcile_once()
      except Exception:
        logger.exception('Reconcile pass failed; continuing.')
      time.sleep(self.interval)

  def stop(self):
    self._stop = True

  def reconcile_once(self):
    snapshot = self._load_snapshot()
    for row in snapshot:
      self._reconcile_worker(row)

  def _load_snapshot(self):
    with self.manager.storage.session_scope() as session:
      workers = session.query(Worker).all()
      return [
        {
          'worker_key': w.worker_key,
          'worker_type': w.worker_type,
          'parameters': w.parameters,
          'pid': w.pid,
          'desired': w.desired_status,
          'status': w.status,
          'restart_count': w.restart_count,
          'last_exit_at': w.last_exit_at,
        }
        for w in workers
      ]

  def _reconcile_worker(self, row):
    alive = self.manager.backend.is_alive(pid=row['pid'], worker_key=row['worker_key'])

    if row['desired'] == DesiredStatus.RUNNING and not alive:
      if self._in_backoff(row):
        return
      logger.info('Reconcile: starting %s', row['worker_key'])
      self.manager.start_worker(row['worker_type'], row['worker_key'], row['parameters'])
    elif row['desired'] == DesiredStatus.STOPPED and alive:
      logger.info('Reconcile: stopping %s', row['worker_key'])
      self.manager.stop_worker(row['worker_key'])
    elif row['desired'] == DesiredStatus.RUNNING and alive and row['status'] != WorkerStatus.RUNNING:
      self._mark_running(row['worker_key'])

  def _in_backoff(self, row):
    if not row['last_exit_at'] or row['status'] != WorkerStatus.CRASHED:
      return False
    delay = min(_BACKOFF_BASE_SECONDS * (2 ** row['restart_count']), _BACKOFF_MAX_SECONDS)
    return datetime.now(timezone.utc) < row['last_exit_at'] + timedelta(seconds=delay)

  def _mark_running(self, worker_key):
    with self.manager.storage.session_scope() as session:
      worker = session.query(Worker).filter_by(worker_key=worker_key).first()
      if worker:
        worker.status = WorkerStatus.RUNNING
```

`crazy_workers/daemon/__main__.py`:

```python
import argparse
import os
import signal

from ..core.manager import WorkerManager
from .reconciler import Reconciler


def main(argv=None):
  parser = argparse.ArgumentParser(prog='crazy_workers.daemon', description='Run the reconcile loop.')
  parser.add_argument('--workers-dir', required=True)
  parser.add_argument('--db-url', default=os.environ.get('CRAZY_WORKERS_DB_URL'))
  parser.add_argument('--interval', type=float, default=2.0)
  args = parser.parse_args(argv)

  manager = WorkerManager(
    args.workers_dir,
    create_dir=False,
    auto_boot=False,
    auto_recover=False,          # la riconciliazione sostituisce il recovery one-shot
    db_url=args.db_url,
    create_tables=args.db_url is None,
  )
  reconciler = Reconciler(manager, interval=args.interval)

  signal.signal(signal.SIGTERM, lambda *_: reconciler.stop())
  try:
    reconciler.run_forever()
  finally:
    manager.dispose()


if __name__ == '__main__':
  main()
```

### 12.3 — Nuovo `WorkerClient` (`crazy_workers/client.py`)

```python
from sqlalchemy import func

from .database.schema import DesiredStatus, Worker, WorkerStatus
from .database.storage import Storage


class WorkerClient:
  """Control-plane client: writes desired state only, never spawns processes.

  Used by anything that is NOT the daemon (HTTP API, CLI, scripts). It shares
  the daemon's database; the daemon reconciles desired -> actual.
  """

  def __init__(self, db_url=None, engine=None, create_tables=False):
    self.storage = Storage(db_url=db_url, engine=engine, create_tables=create_tables)

  def request_start(self, worker_type, worker_key=None, parameters=None):
    worker_key = worker_key or worker_type
    with self.storage.session_scope() as session:
      worker = session.query(Worker).filter_by(worker_key=worker_key).first()
      if not worker:
        worker = Worker(worker_key=worker_key, worker_type=worker_type)
        session.add(worker)
      worker.worker_type = worker_type
      worker.parameters = parameters or {}
      worker.desired_status = DesiredStatus.RUNNING
    return worker_key

  def request_stop(self, worker_key):
    with self.storage.session_scope() as session:
      worker = session.query(Worker).filter_by(worker_key=worker_key).first()
      if not worker:
        return False
      worker.desired_status = DesiredStatus.STOPPED
      worker.last_stopped_at = func.now()
    return True

  def list(self):
    with self.storage.session_scope() as session:
      return [w.to_dict() for w in session.query(Worker).all()]

  def dispose(self):
    self.storage.dispose()
```

Esportare in `crazy_workers/__init__.py`:

```python
from .client import WorkerClient
from .core.manager import WorkerManager
from .database.schema import DesiredStatus, WorkerStatus

__all__ = ['WorkerManager', 'WorkerClient', 'WorkerStatus', 'DesiredStatus']
```

### 12.4 — CLI come client (`crazy_workers/cli/`)

- `start`/`stop` → `WorkerClient.request_start` / `request_stop` (richiesta, non
  spawn). Output: "richiesta inviata; il daemon riconcilierà".
- `status` → legge dal DB e mostra **desired vs actual** affiancati.
- Nuovo subcomando `daemon` → avvia il reconcile loop (equivalente a
  `python -m crazy_workers.daemon`), comodo per dev e per le unit systemd.
- `CRAZY_WORKERS_DB_URL` selezziona il DB condiviso (default: SQLite locale →
  modalità self-contained, in cui la CLI è anche daemon su richiesta).

### 12.5 — Deprecare l'auto_boot embedded

- `WorkerManager.__init__`: default `auto_boot=False`.
- `core/manager/starter.py:_ensure_boot_restore`: mantenuto ma invocato solo se
  `auto_boot=True` esplicito (retrocompat). In ottica daemon, l'avvio al boot è
  responsabilità del **deployment** (systemd unit che lancia il daemon), non di un
  hook per-worker. Il modulo `boot/` può essere riusato per installare l'unit del
  *daemon* invece dell'one-shot `crazy_workers.boot` (opzionale).

### 12.6 — `start_worker` e backoff

In `core/manager/starter.py:_spawn_worker_process`, quando lo spawn fallisce o il
processo muore, valorizzare `last_exit_at` e incrementare `restart_count`; al
primo avvio riuscito azzerare `restart_count`. Serve al `_in_backoff` del
reconciler.

---

## 13. Modifiche dettagliate: `lotec-be`

### Fase C (immediata)

1. `src/__init__.py:init_worker_manager` → aggiungere `auto_boot=False` (B2).
2. Rimuovere la cartella `workers/` di root; `.gitignore`: `workers/` e
   `**/.service/` (C.3, T1-locale).
3. (Opzionale) documentare l'uso CLI con `CRAZY_WORKERS_DB_URL` puntato a Postgres.

### Fase A (daemon)

1. **Endpoint diventano client.** `src/end_points/worker/__init__.py`: sostituire
   `worker_manager.start_worker(...)` con `worker_client.request_start(...)` e
   `worker_manager.stop_worker(...)` con `worker_client.request_stop(...)`. Le
   risposte HTTP non restituiscono più un `pid` immediato (il daemon avvia in modo
   asincrono): restituire `{'status': 'ok', 'message': 'avvio richiesto',
   'worker_key': ...}`; un eventuale `GET /worker/status` legge lo stato reale.

   ```python
   from src import get_worker_client
   ...
   worker_client = get_worker_client()
   worker_client.request_start('register', worker_key=str(device_id),
                               parameters={'device_id': device_id})
   worker_client.request_start('renamer', worker_key=f'renamer_{device_id}',
                               parameters={'output_dir': output_dir})
   return jsonify({'status': 'ok', 'message': 'Registrazione richiesta'})
   ```

   La logica "se il renamer fallisce ferma il recorder" si sposta: con il modello
   desired-state, basta impostare `desired_status` coerente; il daemon non avvia
   un recorder orfano se il renamer non è desiderato. In pratica si richiedono
   entrambi RUNNING e, allo stop, si richiede STOPPED per entrambi (`device_id` e
   `renamer_<device_id>`).

2. **`src/__init__.py`.** Sostituire `init_worker_manager()` con
   `init_worker_client()` (costruisce `WorkerClient(engine=database_api.engine)`).
   `gunicorn_config.py:on_starting` non costruisce più un supervisore né fa
   recovery (lo fa il daemon). Eliminare la duplicazione su 4 worker gunicorn.

3. **Il daemon come servizio separato.** Nuovo processo/container che esegue:

   ```
   python -m crazy_workers.daemon --workers-dir /app/src/workers --db-url $DATABASE_URL
   ```

   Requisiti del container daemon: `ffmpeg`, il volume delle registrazioni
   (stessa path montata del backend), accesso a Postgres. Riusa la stessa image
   del backend (ha già ffmpeg e il codice worker). In `docker-compose`:

   ```yaml
   services:
     api:
       command: gunicorn -w 4 -b 0.0.0.0:8080 --config gunicorn_config.py src.__main__:app
     worker-daemon:
       image: lotec-be:latest          # stessa image
       command: python -m crazy_workers.daemon --workers-dir /app/src/workers --db-url ${DATABASE_URL}
       volumes:
         - recordings:/app/recordings   # stesso volume dell'api
       depends_on: [db]
   ```

4. **Worker script.** `src/workers/register.py` e `renamer.py`: leggere
   `os.environ['DATABASE_URL']` direttamente (iniettata via `worker_env` dal
   daemon) invece di `from .. import DATABASE_URL`, eliminando l'import dell'app
   Flask (B3).

5. **Migrazione schema** per le nuove colonne (vedi §15): nuova revisione Alembic
   `008_worker_desired_status` che aggiunge `desired_status`, `restart_count`,
   `last_exit_at` alla tabella `workers`.

6. **convert/backup** (B4): usare chiavi per-richiesta (es.
   `convert_<device_id>`), così il daemon può eseguire istanze multiple.

### Recovery e riavvii

Con il daemon, riavviare l'API non tocca i worker (non li possiede più). Riavviare
il container daemon non uccide i worker (sono processi figli che sopravvivono); al
riavvio il reconcile li ri-adotta via PID + token cmdline
(`engine.is_worker_process`). I worker rimasti RUNNING con PID morto vengono
riavviati dal primo giro di reconcile.

---

## 14. Modifiche dettagliate: `generic-deploy`

Questo contesto è già coerente (CLI, boot, recovery sullo stesso SQLite). Con il
daemon diventa ancora più lineare.

### Fase C

1. `ansible/settings/common/crazy_workers.yml`: `crazy-workers>=1.3.0` (G1).

### Fase A

1. **Installare il daemon come systemd service** (al posto dell'attuale
   affidamento all'hook di boot per-worker). Nuovo task/template unit:

   ```ini
   [Unit]
   Description=Crazy Workers reconcile daemon ({{ cw_root }})
   After=default.target

   [Service]
   Type=simple
   ExecStart={{ cw_venv }}/bin/python -m crazy_workers.daemon --workers-dir {{ cw_root }}
   Restart=always

   [Install]
   WantedBy=default.target
   ```

   Installata come unit **user** con linger già abilitato (il playbook fa già
   `loginctl enable-linger` e attende `/run/user/<uid>`), oppure come unit di
   sistema se i worker non hanno bisogno della sessione utente.

2. **`crazy_workers_start.yml` diventa "request".** Invece di `crazy-workers start`
   (che oggi spawna e installa l'hook), la CLI imposta il desiderio:

   ```yaml
   - name: "Request worker {{ cw_worker_key }} to run"
     become: true
     become_user: "{{ cw_user }}"
     ansible.builtin.command:
       argv:
         - "{{ cw_cli }}"
         - "--workers-dir"
         - "{{ cw_root }}"
         - "start"
         - "{{ cw_worker_script }}"
         - "--key"
         - "{{ cw_worker_key }}"
         - "--params"
         - "{{ cw_worker_params | to_json }}"
     changed_when: "'requested' in cw_start.stdout"
   ```

   Il daemon (systemd) riconcilia e avvia. Il task di init che crea lo SQLite
   resta invariato (stesso DB usato dal daemon e dalla CLI).

3. **Il boot-restore per-worker non serve più**: lo rimpiazza il daemon che parte
   con la sessione/linger. Si può rimuovere la dipendenza concettuale dall'hook
   (T-G2 mitigato: c'è un solo punto, il daemon).

---

## 15. Migrazioni di schema

### Self-contained (SQLite, generic-deploy)
`create_all` aggiunge la tabella; per DB già esistenti senza le nuove colonne
serve una micro-migrazione (o ricreare lo `.service` in ambienti effimeri). Dato
che generic-deploy ricrea spesso lo stato, è accettabile documentare il drop del
vecchio `workers.db` al primo deploy della nuova versione.

### Owned (PostgreSQL, lotec-be)
Nuova revisione Alembic (es. `src/database/alembic/versions/008_worker_desired_status.py`):

```python
def upgrade():
  op.add_column('workers', sa.Column('desired_status', sa.Enum('RUNNING', 'STOPPED', name='desiredstatus'),
                nullable=False, server_default='STOPPED'))
  op.add_column('workers', sa.Column('restart_count', sa.Integer(), nullable=False, server_default='0'))
  op.add_column('workers', sa.Column('last_exit_at', sa.DateTime(), nullable=True))


def downgrade():
  op.drop_column('workers', 'last_exit_at')
  op.drop_column('workers', 'restart_count')
  op.drop_column('workers', 'desired_status')
```

> Backfill: per i worker già RUNNING al momento della migrazione, impostare
> `desired_status=RUNNING` così il daemon non li spegne al primo giro.

---

## 16. Strategia di test

### Libreria
- **Tabella di riconciliazione**: test unitari di `Reconciler._reconcile_worker`
  con `FakeBackend` (`crazy_workers/testing`) per ognuna delle 4 combinazioni
  desired×alive, più il caso backoff.
- **WorkerClient**: scrive desired_status corretto; non spawna nulla
  (verificare che `FakeBackend.started_types` resti vuoto).
- **End-to-end in-process**: un client imposta RUNNING → un `reconcile_once()`
  avvia il worker (fake) → client imposta STOPPED → secondo `reconcile_once()` lo
  ferma.
- **Single-instance**: due daemon, solo uno acquisisce il lock.
- **Re-adozione**: worker RUNNING con handle perso → reconcile lo riconosce vivo
  via token cmdline e non lo riavvia.

### lotec-be
- Riusare la fixture `tests/conftest.py` basata su `FakeBackend`; aggiungere una
  fixture `WorkerClient` sullo stesso DB di test.
- Test endpoint: `/worker/register` scrive desired_status=RUNNING per `register` e
  `renamer_<id>`; `/worker/stop/<pid>` imposta STOPPED.
- Test `slow` (reali, con ffmpeg) invariati ma orchestrati dal daemon.

### generic-deploy
- Test Ansible/molecule (se presenti) che verificano: unit del daemon installata e
  attiva; `start` imposta il desiderio; il worker risulta RUNNING entro N secondi.

---

## 17. Sequenza di rollout e rollback

1. **Libreria**: implementare schema + reconciler + client + CLI dietro versione
   `1.4.0`. Mantenere la modalità embedded (retrocompat) per non rompere chi non
   migra.
2. **Fase C** su lotec-be e generic-deploy (rilasciabile subito, indipendente da
   A): `auto_boot=False`, `CRAZY_WORKERS_DB_URL`, pin `>=1.3.0`, pulizia residui.
3. **Fase A — lotec-be**: migrazione 008 → deploy daemon container → switch
   endpoint a client → rimozione `init_worker_manager` supervisore. Rollback:
   ripristinare `init_worker_manager` (embedded) e fermare il daemon; lo schema
   con colonne extra è retrocompatibile (le colonne in più non danno fastidio
   all'embedded).
4. **Fase A — generic-deploy**: unit daemon + `start`=request. Rollback: tornare a
   `crazy-workers start` embedded con boot-hook.

Criterio di "fatto": su entrambi i contesti, `crazy-workers status` (con il DB
giusto) mostra lo **stesso** stato che osserva il supervisore, e un reboot/redeploy
ripristina i worker senza intervento manuale.

---

## 18. Decisioni di design e alternative scartate

- **A — Daemon riconciliatore (DB-driven).** ✅ Scelta. Zero protocollo nuovo (il
  DB è già condiviso), unifica i contesti, costruisce sulla co-locazione di stato
  già fatta in lotec-be. La CLI funziona "gratis".
- **B — Daemon + RPC esplicita (HTTP/socket).** Risposte sincrone (PID immediato)
  ma aggiunge superficie: protocollo, auth, networking. Tenuta come opzione futura
  se servirà feedback sincrono; per ora il DB basta.
- **C — Nessun daemon, solo cablaggio.** Risolve i bug di coerenza ma lascia la
  proprietà dei processi embedded (più supervisori). Adottata come **tappa
  intermedia**, non come destinazione.
- **"Un container per tutti i contesti".** ❌ Scartata: i worker di generic-deploy
  devono girare sull'host (vedi §8). Il container è una delle due forme del
  daemon, non la soluzione.

**Decisione cardine:** *chi possiede i processi worker.* Finché è "chiunque chiami
start", si resta nel mondo embedded con le sue divergenze. Quando diventa "un
unico daemon per contesto", le criticità collassano insieme.

---

## 19. Checklist operativa

### crazy-workers (libreria, v1.4.0)
- [ ] `schema.py`: `DesiredStatus` + colonne `desired_status`, `restart_count`, `last_exit_at`.
- [ ] `daemon/reconciler.py` + `daemon/__main__.py`.
- [ ] `client.py` (`WorkerClient`); export in `__init__.py`.
- [ ] CLI: `start`/`stop` come request, `status` desired vs actual, subcomando `daemon`, `CRAZY_WORKERS_DB_URL`.
- [ ] `WorkerManager`: default `auto_boot=False`.
- [ ] `starter.py`: backoff (`restart_count`/`last_exit_at`).
- [ ] Test: tabella di riconciliazione, client, single-instance, re-adozione.
- [ ] `discovery.py`: non scrivere `.env` in modalità DB condiviso (T2).

### lotec-be
- [ ] **C**: `auto_boot=False`; rimuovere `workers/` di root; `.gitignore`.
- [ ] **A**: migrazione Alembic 008; endpoint → `WorkerClient`; daemon container in compose; worker script senza import dell'app (B3); chiavi per-richiesta convert/backup (B4).

### generic-deploy
- [ ] **C**: pin `crazy-workers>=1.3.0`.
- [ ] **A**: unit systemd del daemon; `crazy_workers_start.yml` → request; rimuovere affidamento all'hook per-worker.

### Igiene
- [ ] **T1**: rimuovere/riallineare il checkout obsoleto `lotec/crazy-workers`.

---

## 20. Appendice: mappa file → modifica

| Progetto | File | Modifica |
|---|---|---|
| crazy-workers | `crazy_workers/database/schema.py` | `DesiredStatus` + colonne desiderio/osservato |
| crazy-workers | `crazy_workers/daemon/reconciler.py` | nuovo: reconcile loop |
| crazy-workers | `crazy_workers/daemon/__main__.py` | nuovo: entrypoint daemon |
| crazy-workers | `crazy_workers/client.py` | nuovo: `WorkerClient` |
| crazy-workers | `crazy_workers/__init__.py` | export `WorkerClient`, `DesiredStatus` |
| crazy-workers | `crazy_workers/cli/main.py` | client mode, `CRAZY_WORKERS_DB_URL`, subcomando `daemon` |
| crazy-workers | `crazy_workers/cli/discovery.py` | no `.env` write con DB condiviso |
| crazy-workers | `crazy_workers/core/manager/__init__.py` | default `auto_boot=False` |
| crazy-workers | `crazy_workers/core/manager/starter.py` | backoff fields |
| lotec-be | `src/__init__.py` | `auto_boot=False` (C) → `init_worker_client` (A) |
| lotec-be | `gunicorn_config.py` | niente supervisore/recovery (A) |
| lotec-be | `src/end_points/worker/__init__.py` | endpoint → client; chiavi per-richiesta |
| lotec-be | `src/workers/register.py`, `renamer.py` | leggere `os.environ['DATABASE_URL']` |
| lotec-be | `src/database/alembic/versions/008_*.py` | migrazione colonne |
| lotec-be | `docker-compose.yml` / deploy | servizio `worker-daemon` |
| lotec-be | `.gitignore` | `workers/`, `**/.service/` |
| generic-deploy | `ansible/settings/common/crazy_workers.yml` | pin `>=1.3.0`; unit daemon |
| generic-deploy | `ansible/settings/common/crazy_workers_start.yml` | `start` come request |

---

*Fine del piano. Da rivedere insieme prima di aprire le issue di implementazione.*
