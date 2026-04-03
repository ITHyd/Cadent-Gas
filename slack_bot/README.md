# Slack Bot Service

This service connects Slack to the Cadent Gas backend without changing the main application.

It supports:
- slash commands
- clickable Slack buttons
- lookup modals for incident, agent jobs, and my incidents
- optional Mistral-based natural-language parsing for slash-command text and fuzzy modal input

The Slack bot runs separately from the main Gas backend.

## Current Bot Features

Main Slack entry:
- `/gas`

Quick buttons:
- `Incident Lookup`
- `Agent Jobs Lookup`
- `My Incidents Lookup`
- `Company Stats`
- `Pending Incidents`
- `Available Agents`
- `KB Stats`
- `KB True`
- `KB False`
- `KB Recent`

Direct slash-command usage still works:
- `/gas help`
- `/gas incident INC-1001`
- `/gas company-stats`
- `/gas pending-incidents`
- `/gas agent-jobs agent_001`
- `/gas my-incidents user_001`
- `/gas available-agents`
- `/gas kb-stats`
- `/gas kb-true`
- `/gas kb-false`
- `/gas kb-recent`

Optional AI usage works only when `MISTRAL_API_KEY` is configured:
- `/gas fetch the incident with id INC-1001`
- `/gas bring incidnet with id INC-1001`

## Architecture

Flow:
- Slack -> Slack bot service -> Cadent backend

Services involved:
- Slack bot service:
  - local or server process running `uvicorn`
- Cadent backend:
  - existing FastAPI backend
- Cloudflare Tunnel:
  - exposes local Slack bot service over HTTPS for Slack callbacks

Slack bot endpoints:
- `GET /health`
- `POST /slack/commands`
- `POST /slack/interactions`

## Prerequisites

You need:
- Python installed
- access to the Cadent backend
- a Slack workspace where you can create/install an app
- `cloudflared` installed if you are exposing a local bot through Cloudflare Tunnel

## Environment Variables

Create a file:
- `slack_bot/.env`

You can copy from:
- [`.env.example`](e:\ITHyd\Cadent-Gas\slack_bot\.env.example)

Example:

```env
SLACK_SIGNING_SECRET=your_slack_signing_secret
SLACK_BOT_TOKEN=xoxb-your-bot-token
BACKEND_BASE_URL=http://149.102.158.71:4445
BACKEND_USERNAME=your_backend_username
BACKEND_PASSWORD=your_backend_password
DEFAULT_TENANT_ID=tenant_demo
REQUEST_TIMEOUT_SECONDS=20.0
MISTRAL_API_KEY=
MISTRAL_MODEL=mistral-small-latest
AI_PARSE_TIMEOUT_SECONDS=2.5
```

### What each field means

`SLACK_SIGNING_SECRET`
- used to verify Slack requests
- required

`SLACK_BOT_TOKEN`
- used for Slack modals and future Slack API actions
- required for button-driven modals like `Incident Lookup`
- starts with `xoxb-`

`BACKEND_BASE_URL`
- Cadent backend base URL
- example:
  - `http://149.102.158.71:4445`

`BACKEND_USERNAME`
- existing Cadent app account username
- use an account that can access the required read endpoints

`BACKEND_PASSWORD`
- password for the above backend account

`DEFAULT_TENANT_ID`
- default tenant used when a command does not pass tenant explicitly
- current common value in this project:
  - `tenant_demo`

`REQUEST_TIMEOUT_SECONDS`
- timeout for backend requests from the Slack bot
- default:
  - `20.0`

`MISTRAL_API_KEY`
- optional
- if present, natural-language requests are enabled
- if empty or missing, normal commands/buttons still work

`MISTRAL_MODEL`
- optional model name for Mistral
- default:
  - `mistral-small-latest`

`AI_PARSE_TIMEOUT_SECONDS`
- optional
- max time to wait for Mistral parsing before falling back
- default:
  - `2.5`

## Where To Get Each Slack Value

### 1. Slack Signing Secret

Go to:
- `https://api.slack.com/apps`
- open your app
- `Basic Information`
- under `App Credentials`
- copy `Signing Secret`

Put it in:

```env
SLACK_SIGNING_SECRET=...
```

### 2. Slack Bot Token

Go to:
- `https://api.slack.com/apps`
- open your app
- `OAuth & Permissions`
- copy `Bot User OAuth Token`

It looks like:
- `xoxb-...`

Put it in:

```env
SLACK_BOT_TOKEN=xoxb-...
```

If you do not see a token yet:
- click `Install to Workspace` or `Reinstall to Workspace`

## Where To Get Backend Values

### 1. Backend Base URL

Use your running Cadent backend URL.

Example:

```env
BACKEND_BASE_URL=http://149.102.158.71:4445
```

### 2. Backend Username / Password

Use a valid Cadent application account, not a Slack account.

This is the account the bot uses to call backend APIs.

Example:

```env
BACKEND_USERNAME=admin
BACKEND_PASSWORD=your_password
```

If you are using seeded local/demo data, verify the actual deployed credentials before use.

### 3. Default Tenant ID

For the current setup, this is usually:

```env
DEFAULT_TENANT_ID=tenant_demo
```

## Install Dependencies

From repo root:

```powershell
cd E:\ITHyd\Cadent-Gas\slack_bot
pip install -r requirements.txt
```

## Run The Slack Bot

From:
- `E:\ITHyd\Cadent-Gas\slack_bot`

Run:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8090 --reload
```

Health check:
- `http://localhost:8090/health`

Expected response:

```json
{"status":"healthy"}
```

## Run With Docker Compose On Server

The repository now includes:
- [Dockerfile](e:\ITHyd\Cadent-Gas\slack_bot\Dockerfile)
- a `slack_bot` service in [docker-compose.yml](e:\ITHyd\Cadent-Gas\docker-compose.yml)

Server-side container behavior:
- `slack_bot` runs on container port `8090`
- compose publishes it as host port `8090`
- inside Docker, the bot talks to the backend using:
  - `http://backend:5020`

Add these values to your server `.env.docker`:

```env
SLACK_SIGNING_SECRET=...
SLACK_BOT_TOKEN=xoxb-...
BACKEND_USERNAME=...
BACKEND_PASSWORD=...
DEFAULT_TENANT_ID=tenant_demo
REQUEST_TIMEOUT_SECONDS=20.0
MISTRAL_API_KEY=
MISTRAL_MODEL=mistral-small-latest
AI_PARSE_TIMEOUT_SECONDS=2.5
```

Then from repo root run:

```powershell
docker compose up -d --build slack_bot
```

Or rebuild the full stack:

```powershell
docker compose up -d --build
```

Health check after deployment:
- `http://<server-ip>:8090/health`

Important:
- Slack should still point to the `slack_bot` service, not the main backend
- for production Slack callbacks, expose the bot over `https` using Nginx/IIS or another SSL-enabled reverse proxy

## Run Cloudflare Tunnel

In a separate terminal:

```powershell
cloudflared tunnel --url http://localhost:8090
```

Cloudflare will print a quick tunnel URL like:

```text
https://random-name.trycloudflare.com
```

Important:
- quick tunnel URLs change every time you restart `cloudflared`
- when the URL changes, update Slack settings again

## Slack App Setup

Go to:
- `https://api.slack.com/apps`

Create or open your app.

### 1. Install App To Workspace

Open:
- `Install App`

Then:
- click `Install to Workspace`

### 2. Create Slash Command

Open:
- `Slash Commands`

Create:
- command: `/gas`

Set request URL to:

```text
https://<your-current-cloudflare-url>/slack/commands
```

Example:

```text
https://holder-ladies-checks-org.trycloudflare.com/slack/commands
```

Suggested values:
- Short Description: `Query the Gas Incident platform`
- Usage Hint: `help`

### 3. Enable Interactivity

Open:
- `Interactivity & Shortcuts`

Turn `Interactivity` on.

Set request URL to:

```text
https://<your-current-cloudflare-url>/slack/interactions
```

Example:

```text
https://holder-ladies-checks-org.trycloudflare.com/slack/interactions
```

## Minimum Slack Fields To Paste

### In Slack App Settings

Paste this in `Slash Commands`:

```text
https://<cloudflare-url>/slack/commands
```

Paste this in `Interactivity & Shortcuts`:

```text
https://<cloudflare-url>/slack/interactions
```

### In `slack_bot/.env`

Paste:

```env
SLACK_SIGNING_SECRET=...
SLACK_BOT_TOKEN=xoxb-...
BACKEND_BASE_URL=http://149.102.158.71:4445
BACKEND_USERNAME=...
BACKEND_PASSWORD=...
DEFAULT_TENANT_ID=tenant_demo
```

Optional:

```env
REQUEST_TIMEOUT_SECONDS=20.0
MISTRAL_API_KEY=...
MISTRAL_MODEL=mistral-small-latest
AI_PARSE_TIMEOUT_SECONDS=2.5
```

## Complete Local Run Flow

Use this order:

1. Fill `slack_bot/.env`
2. Start Cadent backend
3. Start Slack bot:

```powershell
cd E:\ITHyd\Cadent-Gas\slack_bot
uvicorn app.main:app --host 0.0.0.0 --port 8090 --reload
```

4. Start Cloudflare tunnel:

```powershell
cloudflared tunnel --url http://localhost:8090
```

5. Copy the generated Cloudflare URL
6. Paste it in Slack:
   - `Slash Commands` -> `/slack/commands`
   - `Interactivity & Shortcuts` -> `/slack/interactions`
7. Save Slack settings
8. Test in Slack with:

```text
/gas
```

## Testing Checklist

### Basic

Test:

```text
/gas
/gas help
/gas company-stats
/gas pending-incidents
/gas available-agents
/gas kb-stats
/gas kb-true
/gas kb-false
/gas kb-recent
```

### Modal Buttons

Test:
- click `Incident Lookup`
  - enter `INC-1001`
  - or `1001`
  - if Mistral is configured, fuzzy text like `incident 1001` can also resolve

- click `Agent Jobs Lookup`
  - enter `agent_001`
  - or `1`
  - if Mistral is configured, fuzzy text like `agent 1` can also resolve

- click `My Incidents Lookup`
  - enter `user_001`
  - or `1`
  - if Mistral is configured, fuzzy text like `user 1` can also resolve

### Optional AI Tests

Only if `MISTRAL_API_KEY` is set:

```text
/gas fetch the incident with id INC-1001
/gas show pending incidents
/gas bring incidnet with id INC-1001
```

## Notes About Mistral

Without Mistral:
- buttons work
- modals work
- normal slash commands work
- modal ID normalization still works for simple numeric patterns:
  - `1001` -> `INC-1001`
  - `1` -> `agent_001`
  - `1` -> `user_001`

With Mistral:
- natural-language requests can also work
- modal inputs can also benefit from AI-assisted parsing when the entered value is fuzzy

Mistral is not required for:
- buttons
- modal lookups
- normal direct commands

## Common Issues

### 1. `/gas` not found

Check:
- slash command is saved in Slack
- app is installed to workspace

### 2. Slash command times out

Check:
- Slack bot is running on `8090`
- backend is reachable
- Cloudflare tunnel is active

### 3. Buttons show but clicking does nothing

Check:
- `Interactivity & Shortcuts` is enabled
- interactivity URL points to:
  - `/slack/interactions`
- Slack bot was restarted after code changes

### 4. Modal does not open

Check:
- `SLACK_BOT_TOKEN` is set
- Slack app is installed/reinstalled to workspace

### 5. Cloudflare URL changed

If you restart `cloudflared`, quick tunnel URL changes.

Update Slack again:
- Slash Commands URL
- Interactivity URL

## Recommended File To Maintain

Use this file:
- [README.md](e:\ITHyd\Cadent-Gas\slack_bot\README.md)

That is better than creating a second setup doc because:
- all Slack bot setup stays in one place
- env fields and run steps stay close to the code
- future updates are easier to keep accurate
