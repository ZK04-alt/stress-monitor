
# U.S. Infrastructure Stress Monitor

A runnable FastAPI website for the attached frozen electricity and water stress project.

## What the runtime uses

- `state_model_history.csv` — observed state history plus chronologically out-of-sample model signals
- `project_metadata.json` — normalization boundaries, projection policy, model registry and uncertainty inputs
- `evaluation_metrics.json` — frozen validation/backtest diagnostics
- `stress_score_cli.py` — the original projection, normalization and range functions
- Frozen `.cbm` and `.joblib` artifacts — retained in `models/` and verified by `/healthz`

The website intentionally labels future values as **recursive baseline scenarios**. It does not imply known future weather, demand, population or infrastructure.

## Run

```bash
python -m pip install -r requirements.txt
python main.py
```

Open `http://127.0.0.1:8000`.

For a server-free preview, open `standalone.html` directly.

Alternative:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## API

- `GET /healthz`
- `GET /api/bootstrap`
- `GET /api/project?state=CA&year=2030`
- `GET /api/docs`

## Deployment

The project can be deployed to any Python host that supports FastAPI, including Render, Railway, Fly.io, Azure App Service or a container platform. Keep the `models/` directory beside `main.py`.

## Design

The interface implements the supplied dark scientific monitoring handoff:

- near-black technical grid
- warm-white text
- deep-rose structural accents
- yellow electricity coding
- teal water coding
- squared minimal surfaces
- monospace technical labels
- responsive layouts and reduced-motion support


## Container

```bash
docker build -t stress-monitor .
docker run --rm -p 8000:8000 stress-monitor
```
