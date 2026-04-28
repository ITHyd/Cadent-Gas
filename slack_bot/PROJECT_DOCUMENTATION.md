# Slack Bot Project Documentation

## Overview

This Slack bot is a standalone integration layer for the Cadent Gas platform.

It does not replace the main backend. Instead, it sits between Slack and the existing Cadent backend and translates Slack interactions into backend API calls.

Main idea:
- Slack is the user interface
- `slack_bot` is the adapter
- the Cadent backend remains the source of truth

The project currently focuses on read-oriented operational actions:
- incident lookup
- company stats
- pending incidents
- agent listings
- KB lookups
- user incident lookups

It also supports:
- clickable buttons
- Slack modals for ID-based lookups
- optional Mistral-based natural-language parsing

## High-Level Architecture

Flow:

1. User interacts in Slack
2. Slack sends a request to the Slack bot service
3. The Slack bot verifies the request signature
4. The Slack bot decides what command to run
5. The Slack bot calls the Cadent backend API
6. The backend returns JSON
7. The Slack bot formats the response for Slack
8. Slack shows the result to the user

The Slack bot does not own business data.

## Project Structure

Main project folder:
- [slack_bot](e:\ITHyd\Cadent-Gas\slack_bot)

Important files:

- [main.py](e:\ITHyd\Cadent-Gas\slack_bot\app\main.py)
  - FastAPI entrypoint
  - receives Slack commands and interactions
  - opens modals
  - posts responses back to Slack

- [command_router.py](e:\ITHyd\Cadent-Gas\slack_bot\app\command_router.py)
  - central command dispatcher
  - maps Slack requests to backend API calls
  - defines current command set and button set

- [backend_client.py](e:\ITHyd\Cadent-Gas\slack_bot\app\backend_client.py)
  - logs in to the Cadent backend
  - caches backend access token
  - performs authenticated backend GET requests

- [formatters.py](e:\ITHyd\Cadent-Gas\slack_bot\app\formatters.py)
  - turns backend JSON into user-readable Slack text
  - contains list, stats, incident, and lookup formatting helpers

- [ai_parser.py](e:\ITHyd\Cadent-Gas\slack_bot\app\ai_parser.py)
  - optional AI-assisted interpretation
  - supports free-text slash commands and fuzzy modal input
  - performs direct ID normalization first, then optional AI fallback

- [mistral_client.py](e:\ITHyd\Cadent-Gas\slack_bot\app\mistral_client.py)
  - talks to the Mistral API
  - asks Mistral to return strict JSON command intents

- [slack_security.py](e:\ITHyd\Cadent-Gas\slack_bot\app\slack_security.py)
  - verifies Slack signatures using signing secret
  - protects the service from unauthenticated requests

- [config.py](e:\ITHyd\Cadent-Gas\slack_bot\app\config.py)
  - application settings
  - loads `.env` values through `pydantic-settings`

- [README.md](e:\ITHyd\Cadent-Gas\slack_bot\README.md)
  - setup and run guide

- [.env.example](e:\ITHyd\Cadent-Gas\slack_bot\.env.example)
  - sample configuration values

## Dependencies

From [requirements.txt](e:\ITHyd\Cadent-Gas\slack_bot\requirements.txt):

- `fastapi`
- `uvicorn[standard]`
- `httpx`
- `pydantic`
- `pydantic-settings`
- `python-dotenv`

Notably, this project does **not** use:
- `slack_sdk`
- `slack_bolt`

Slack integration is implemented manually using:
- raw Slack HTTP payloads
- custom signature verification
- direct HTTP calls to Slack APIs like `views.open`

## Configuration

Environment is loaded from:
- [`.env`](e:\ITHyd\Cadent-Gas\slack_bot\.env)

Settings are defined in:
- [config.py](e:\ITHyd\Cadent-Gas\slack_bot\app\config.py)

Current settings:

- `SLACK_SIGNING_SECRET`
  - required
  - used to verify Slack requests

- `SLACK_BOT_TOKEN`
  - optional in pure slash-command mode
  - required for Slack modal support

- `BACKEND_BASE_URL`
  - Cadent backend base URL

- `BACKEND_USERNAME`
  - backend application username

- `BACKEND_PASSWORD`
  - backend application password

- `DEFAULT_TENANT_ID`
  - fallback tenant when not explicitly provided

- `REQUEST_TIMEOUT_SECONDS`
  - backend request timeout

- `MISTRAL_API_KEY`
  - optional
  - enables AI-assisted parsing

- `MISTRAL_MODEL`
  - Mistral model name

- `MISTRAL_BASE_URL`
  - Mistral API base URL

- `AI_PARSE_TIMEOUT_SECONDS`
  - max time allowed for AI parsing before falling back

## Slack Endpoints

Defined in [main.py](e:\ITHyd\Cadent-Gas\slack_bot\app\main.py):

- `GET /health`
  - health check for local verification

- `POST /slack/commands`
  - receives slash commands from Slack

- `POST /slack/interactions`
  - receives button clicks and modal submissions from Slack

## Security Model

Slack request verification is handled in:
- [slack_security.py](e:\ITHyd\Cadent-Gas\slack_bot\app\slack_security.py)

Verification steps:
- confirm signing secret exists
- confirm timestamp exists
- reject stale requests older than configured age
- build Slack signature base string
- compute HMAC SHA256 signature
- compare with `x-slack-signature`

If verification fails:
- request is rejected with `401`

## Backend Authentication Model

The Slack bot authenticates to the Cadent backend using:
- `POST /api/v1/auth/admin-login`

This is handled by:
- [backend_client.py](e:\ITHyd\Cadent-Gas\slack_bot\app\backend_client.py)

Behavior:
- logs in once
- caches access token
- reuses token for about 25 minutes
- re-authenticates when token expires

Current backend operations are read-oriented and use authenticated GET requests.

## Supported Slack UX Patterns

### 1. Slash Command

Example:
- `/gas company-stats`

Flow:
- Slack sends to `/slack/commands`
- `route_command()` decides what to do
- backend is called
- response is formatted
- Slack displays the result

### 2. Help Menu With Buttons

Example:
- `/gas`

Flow:
- empty slash-command text is routed to help
- bot returns a Slack button card
- user clicks buttons to trigger lookups

### 3. Modal-Based Input

Current modal buttons:
- `Incident Lookup`
- `Agent Jobs Lookup`
- `My Incidents Lookup`

Flow:
- user clicks a lookup button
- bot opens Slack modal with `views.open`
- user enters a value
- Slack sends `view_submission`
- bot resolves the input
- bot runs the matching command
- bot posts the result back into Slack

## Current Command Set

Defined through [command_router.py](e:\ITHyd\Cadent-Gas\slack_bot\app\command_router.py) and [ai_parser.py](e:\ITHyd\Cadent-Gas\slack_bot\app\ai_parser.py).

Supported commands:

- `help`
- `incident <incident_id>`
- `company-stats`
- `pending-incidents`
- `agent-jobs <agent_id>`
- `my-incidents <user_id>`
- `available-agents`
- `all-agents`
- `kb-stats`
- `kb-true`
- `kb-false`
- `kb-recent`

## Slack Buttons Currently Available

Current quick actions:

- `Incident Lookup`
- `Agent Jobs Lookup`
- `My Incidents Lookup`
- `Company Stats`
- `Pending Incidents`
- `Available Agents`
- `All Agents`
- `KB Stats`
- `KB True`
- `KB False`
- `KB Recent`

These are rendered by `_help_blocks()` in [command_router.py](e:\ITHyd\Cadent-Gas\slack_bot\app\command_router.py).

## Backend Routes Used By The Bot

Current Cadent backend routes used:

- `GET /api/v1/incidents/{incident_id}`
- `GET /api/v1/incidents/company/{tenant_id}/stats`
- `GET /api/v1/incidents/company/{tenant_id}?status=pending_company_action`
- `GET /api/v1/incidents/agent/{agent_id}/incidents`
- `GET /api/v1/incidents/user/{user_id}`
- `GET /api/v1/incidents/agents/available`
- `GET /api/v1/incidents/agents/all`
- `GET /api/v1/kb/stats`
- `GET /api/v1/kb/true`
- `GET /api/v1/kb/false`
- `GET /api/v1/kb/recent`

## AI Behavior

AI parsing is optional.

If `MISTRAL_API_KEY` is not configured:
- buttons work
- modals work
- slash commands work
- direct numeric normalization still works for modal inputs

If `MISTRAL_API_KEY` is configured:
- free-text slash-command requests can be interpreted
- fuzzy modal input can also be interpreted when direct normalization fails

### Direct Normalization Before AI

Implemented in [ai_parser.py](e:\ITHyd\Cadent-Gas\slack_bot\app\ai_parser.py).

Examples:
- `1001` -> `INC-1001`
- `1` -> `agent_001`
- `1` -> `user_001`

This means modal lookup does not depend on AI for common numeric input patterns.

### AI Intent Parsing

When direct parsing fails, the bot may ask Mistral to map user text into one of the approved commands only.

Guardrails:
- only allowed commands are accepted
- unsupported write actions are rejected
- IDs must come from user input
- parser returns strict JSON

## Formatting Behavior

Formatting is centralized in:
- [formatters.py](e:\ITHyd\Cadent-Gas\slack_bot\app\formatters.py)

Current formatters include:
- help formatter
- single incident formatter
- incident list formatter
- detailed incident list formatter
- agent list formatter
- company stats formatter
- KB stats formatter
- KB entries formatter
- empty lookup formatter

Special behavior:
- incident `404` is converted into a lookup-style response
- empty agent/user results are shown as simple “No records found” lookups

Examples:
- `Incident ID: 1`
  - `Incident not found.`

- `Agent ID: 001`
  - `No records found.`

## Error Handling

Handled in [main.py](e:\ITHyd\Cadent-Gas\slack_bot\app\main.py).

Current categories:

- command validation errors
- backend HTTP errors
- unexpected runtime errors
- async interaction errors

Current backend/unexpected errors are shown in neat text format, for example:

- `Request failed`
- `Status: 404`
- `Details: {"detail":"Incident not found"}`

## Modal Behavior

Modals are opened using Slack API:
- `https://slack.com/api/views.open`

This requires:
- `SLACK_BOT_TOKEN`

Current modal handlers:
- incident lookup submit
- agent jobs submit
- my incidents submit

To avoid Slack popup timeout issues:
- modal closes immediately
- backend command execution happens in a background task
- result is posted afterward through Slack response flow

## Current Limitations

Current project limitations:

- no write actions are implemented in Slack yet
- no threaded Slack reply model yet
- no persistent Slack user-to-backend identity mapping
- no Slack SDK usage
- quick Cloudflare URLs change on restart
- no Teams support in this codebase
- AI is optional and only used in bounded parsing scenarios

## How The System Works End To End

### Slash Command Example

User types:
- `/gas company-stats`

System behavior:
- Slack sends request to `/slack/commands`
- request is verified
- command router matches `company-stats`
- backend client calls company stats endpoint
- formatter builds Slack text
- Slack displays result

### Button Example

User types:
- `/gas`

Then:
- clicks `Available Agents`

System behavior:
- Slack sends `block_actions` payload to `/slack/interactions`
- button value is extracted
- command router runs `available-agents`
- backend is queried
- response is posted back to Slack

### Modal Example

User:
- clicks `Incident Lookup`
- enters `1001`

System behavior:
- modal opens
- user submits `1001`
- input is normalized to `INC-1001`
- backend incident route is called
- formatted result is posted back to Slack

## Suggested Future Extensions

Possible next additions:

- threaded Slack replies
- write actions such as assign/approve/resolve
- richer Block Kit cards for results
- Slack notifications pushed into channels
- Teams adapter built on the same command/backend layers

## Recommended Maintenance Strategy

Keep these files in sync when features change:

- [main.py](e:\ITHyd\Cadent-Gas\slack_bot\app\main.py)
- [command_router.py](e:\ITHyd\Cadent-Gas\slack_bot\app\command_router.py)
- [ai_parser.py](e:\ITHyd\Cadent-Gas\slack_bot\app\ai_parser.py)
- [formatters.py](e:\ITHyd\Cadent-Gas\slack_bot\app\formatters.py)
- [config.py](e:\ITHyd\Cadent-Gas\slack_bot\app\config.py)
- [README.md](e:\ITHyd\Cadent-Gas\slack_bot\README.md)

Best rule:
- `README.md` for setup and run instructions
- `PROJECT_DOCUMENTATION.md` for architecture and behavior documentation
