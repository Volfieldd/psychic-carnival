# Energy Pattern Analyzer (MVP pragmatique)

## Lancer
```bash
docker compose up --build
```
- UI: http://localhost:5173
- API: http://localhost:8000/docs

Volumes:
- `./data` -> SQLite (`/data/app.db`)
- `./config` -> config YAML (`/config/app.yaml`)

Variables utiles:
- `TIMEZONE=Europe/Paris`
- `DB_PATH=/data/app.db`
- `CONFIG_PATH=/config/app.yaml`

## CSV “Shelly-like” (format FIXE)
Colonnes attendues (header insensible casse):
- `timestamp` (ISO8601, epoch sec, epoch ms)
- `watts` pour type `power`
- `on` (0/1) pour type `light`
- `lux` pour type `lux`

Séparateur accepté: `,` ou `;`.

Exemple:
```csv
timestamp;watts;on;lux
2026-01-04T10:00:00+01:00;0;0;24
2026-01-04T10:00:30+01:00;1800;1;40
1735981230000;1500;1;42
```

## Scénarios
1. **Sèche-linge (watts)**: créer device `power` + `main_metric=watts`, importer `examples/dryer_watts.csv`, analyze/simulate/activate.
2. **Lumière (on/off)**: créer device `light` + `main_metric=on`, importer `examples/light_onoff.csv`.
3. **Capteur lux**: créer device `lux` + `main_metric=lux`, importer un CSV avec `timestamp,lux`.

## Endpoints principaux
1. `POST /devices` création device
```json
{"name":"Dryer","type":"power","source_type":"csv","main_metric":"watts"}
```
2. `POST /devices/{id}/ingest/csv` upload fichier
3. `POST /devices/{id}/analyze/oneshot` proposition de règle
4. `POST /devices/{id}/simulate` simulation (`rule_json` ou `rule_id`)
5. `GET /devices/{id}/status/current?window_sec=600` état courant + dernier event

API complète attendue aussi disponible:
- Devices CRUD
- `POST /devices/{id}/ingest/shelly_pull`
- `GET /devices/{id}/stats`
- `GET /devices/{id}/series`
- rules list/create/update/activate
