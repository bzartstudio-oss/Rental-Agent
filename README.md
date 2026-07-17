# Rental-Agent

## Structure

- `learning/` — notes, research, and reference material gathered while building the agent
- `docs/` — project documentation
- `prompts/` — prompt templates used by the agent
- `src/` — source code
- `data/` — input data
- `output/` — generated output
- `images/` — image assets
- `tests/` — test suite

## Setup

```
python -m venv .venv
pip install -r requirements.txt
cp .env.example .env
```

## Usage

CLI (the original interface — still fully supported, unchanged):

```
python -m src.ui.cli --location "Example City"
```

Web dashboard (v2.5 Step 16 — a local, single-user Flask app over the same
platform; see [docs/32_Web_Dashboard.md](docs/32_Web_Dashboard.md)):

```
python -m flask --app "src.web.application:create_app" run
```

Then open `http://127.0.0.1:5000/` in a browser. Bound to localhost only by
default — set `WEB_ALLOW_NETWORK=1` to expose it on the network.

## Operations

```
python scripts/health_check.py         # verify the local installation
python scripts/backup.py --compress     # back up the database, reports, media
python scripts/verify_backup.py <path>   # verify a backup's integrity
python scripts/restore.py <path> --to <dest> --preview   # preview a restore
```

Full detail: [docs/35_Installation_and_Operations.md](docs/35_Installation_and_Operations.md).

## Release Status

Current version: see [VERSION](VERSION). Release candidate acceptance
results: [docs/33_Release_Candidate_Acceptance.md](docs/33_Release_Candidate_Acceptance.md),
[docs/34_Security_Acceptance.md](docs/34_Security_Acceptance.md).
