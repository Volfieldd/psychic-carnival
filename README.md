# Energy Pattern Analyzer (MVP)

MVP complet dockerisé (API FastAPI + UI React + stockage SQLite/Postgres) pour ingestion de séries temporelles multi-device et génération de règles interprétables (DSL JSON).

## Démarrage rapide

```bash
docker compose up --build
```

- API: http://localhost:8000/docs
- UI: http://localhost:5173

## Exécuter les tests

```bash
docker compose run --rm api pytest
```

## Configuration

Le fichier `config/app.yaml` est chargé au démarrage.

Variables d'environnement utiles:
- `DB_URL` (défaut SQLite local: `sqlite:////app/data/app.db`)
- `CONFIG_PATH` (défaut `/app/config/app.yaml`)
- `LOG_LEVEL`

### Option Postgres

```bash
docker compose --profile postgres up --build
```

Exemple `DB_URL` Postgres:
`postgresql+psycopg2://energy:energy@db:5432/energy`

## API principales

- `/devices` CRUD
- `/sources` CRUD (`csv`, `shelly`, `generic_http_pull`)
- `/ingest/csv` upload CSV + mapping colonnes
- `/ingest/shelly/pull` MVP simulé compatible flux Shelly
- `/ingest/push` webhook points temps réel
- `/series` lecture + downsampling
- `/rules` CRUD règles DSL
- `/simulate` applique DSL -> states/events
- `/analyze/oneshot` propose règle + explication + score
- `/analyze/auto` consolidation simple sur période
- `/status/current` état glissant
- `/config/effective` YAML effectif

## DSL JSON (extrait)

```json
{
  "metric": "watts",
  "states": [
    {
      "name": "RUNNING",
      "entry": {"type": "threshold", "op": "gte", "value": 1200, "for_sec": 60},
      "exit": {"type": "threshold", "op": "lte", "value": 80, "for_sec": 60}
    }
  ],
  "patterns": {
    "oscillation": {"enabled": true},
    "plateau": {"enabled": true},
    "duty_cycle": {"enabled": true},
    "drops_to_zero": {"enabled": true}
  },
  "events": ["START", "STOP"]
}
```

## Exemples fournis

- `examples/dryer_watts.csv`
- `examples/light_onoff.csv`
- `examples/kettle_watts.csv`
- `examples/rules/*.json`

## Notes MVP

- Module `scenes` multi-device déclaratif présent dans `config/app.yaml`, désactivé par défaut.
- Moteur commun multi-métriques (watts, onoff, lux...) avec preprocess, segmentation, features et simulation.
