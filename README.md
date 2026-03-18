# Gas Incident Intelligence Platform

AI-powered multimodal incident management platform for gas utility companies. Built with FastAPI, React, Mistral AI, and WebSocket real-time communication.

## Features

- **Multimodal Input** - Text, audio (Whisper), video, and image (OCR/CV) support
- **AI-Powered Classification** - Mistral AI classifies incidents into use cases automatically
- **Dynamic Workflow Engine** - Graph-based workflows with condition branching, risk calculation, and decision nodes
- **Visual Workflow Builder** - Drag-and-drop workflow editor using React Flow
- **Knowledge Base** - True/false incident KB with auto-learning from resolved incidents
- **Risk Assessment** - Multi-factor risk scoring with KB confidence adjustment and commercial property multiplier
- **Field Agent Management** - Live GPS tracking, milestone logging, assistance/item requests
- **Multi-Tenant Architecture** - Tenant isolation with role-based access control
- **Real-Time Communication** - WebSocket-based chat with AI agent
- **Text Validation** - Structural heuristic validation rejects gibberish in resolution fields
- **Manual Report Fallback** - Graceful handling when no workflow matches an incident type
- **SLA Tracking** - Automatic SLA calculation based on outcome and location type
- **Connector Framework** - Bidirectional sync with SAP, ServiceNow, and Jira connectors via CanonicalTicket model
- **RBAC Admin Groups** - Connector-scoped admin groups with JWT-embedded permissions
- **Security Hardened** - Rate limiting, security headers, JWT auth on all endpoints, global exception handler

---

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [User Roles](#user-roles)
- [Frontend Pages](#frontend-pages)
- [Backend API Reference](#backend-api-reference)
- [Data Models](#data-models)
- [Workflow System](#workflow-system)
- [Knowledge Base System](#knowledge-base-system)
- [Risk Assessment](#risk-assessment)
- [Incident Lifecycle](#incident-lifecycle)
- [Field Agent Operations](#field-agent-operations)
- [Authentication](#authentication)
- [Configuration](#configuration)
- [Documentation](#documentation)

---

## Quick Start

### Prerequisites

- Python 3.7+ (3.11+ recommended)
- Node.js 16+
- MongoDB
- FFmpeg (for audio/video processing)

### Installation

```bash
# Backend
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

### Configuration

Copy `backend/.env.example` to `backend/.env` and fill in required values:

```bash
cd backend
cp .env.example .env
# Generate a strong secret key:
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

At minimum, set:
```env
SECRET_KEY=<generated-key>
MISTRAL_API_KEY=your-mistral-api-key
MISTRAL_AGENT_ID=your-mistral-agent-id
MONGODB_URI=mongodb://localhost:27017
```

### Run

```bash
# Terminal 1 - Backend
cd backend
python -m uvicorn main:app --reload

# Terminal 2 - Frontend
cd frontend
npm run dev
```

Or use the convenience scripts:

```bash
start_dev.bat       # Start both backend and frontend
start_backend.bat   # Backend only
start_frontend.bat  # Frontend only
```

Open: http://localhost:3000

---

## Architecture

```
User Input --> Classifier --> Workflow Selection --> Workflow Engine --> Agent Orchestrator --> Response
    |                                                    |                       |
Multimodal                                          State Machine          AI Enhancement
Processing                                          Execution              (Mistral)
(Whisper, OCR, CV)                                       |
                                                    KB Verification
                                                    Risk Scoring
```

### Request Flow

1. **User** submits incident via chat (WebSocket) or form (REST)
2. **Classifier** determines use case (gas_smell, weak_flame, etc.) using Mistral AI
3. **Workflow Repository** loads the matching workflow for tenant + use case
4. **Workflow Engine** executes the graph-based workflow (questions, conditions, calculations)
5. **Agent Orchestrator** coordinates the conversation, enhances responses with AI
6. **Risk Calculator** scores the incident with KB confidence adjustment
7. **Incident Service** persists the result, triggers notifications and SLA tracking
8. **KB Service** learns from resolved incidents automatically

---

## Tech Stack

### Backend

| Component | Technology |
|-----------|------------|
| Framework | FastAPI 0.115 |
| AI/LLM | Mistral AI (mistral-large-latest) |
| Speech-to-Text | OpenAI Whisper |
| OCR | EasyOCR |
| Audio Analysis | LibROSA |
| Computer Vision | OpenCV, PyTorch |
| Database | MongoDB (primary), SQLite (dev fallback) |
| Cache | Redis |
| Auth | JWT (python-jose, bcrypt) |
| Rate Limiting | slowapi |
| Real-Time | WebSocket (native FastAPI) |

### Frontend

| Component | Technology |
|-----------|------------|
| UI Framework | React 18 |
| Build Tool | Vite 5 |
| Routing | React Router DOM 6 |
| Workflow Editor | React Flow 11 |
| Maps | Leaflet + React Leaflet |
| Diagrams | Mermaid |
| State | Zustand |
| Styling | Tailwind CSS 3 |

---

## Project Structure

```
├── backend/
│   ├── main.py                          # FastAPI entry point + security middleware
│   ├── requirements.txt                 # Python dependencies
│   ├── .env                             # Environment variables
│   ├── .env.example                     # Production-ready template
│   ├── app/
│   │   ├── api/                         # REST & WebSocket endpoints
│   │   │   ├── auth.py                  #   Authentication (OTP, JWT, rate-limited)
│   │   │   ├── incidents.py             #   Incident CRUD, agent ops, notifications
│   │   │   ├── agents.py               #   WebSocket chat, voice, session management
│   │   │   ├── knowledge_base.py        #   KB CRUD, search, verification
│   │   │   ├── workflows.py             #   Workflow CRUD
│   │   │   ├── super_user.py            #   Admin: workflows, risk config, executions
│   │   │   ├── connectors.py            #   Connector config, sync, backfill, retention
│   │   │   ├── tenants.py               #   Tenant CRUD, admin groups, mappings
│   │   │   └── webhooks.py              #   Webhook receivers (ServiceNow, SAP)
│   │   ├── services/                    # Business logic
│   │   │   ├── agent_orchestrator.py    #   Central conversation coordinator
│   │   │   ├── incident_service.py      #   Incident lifecycle, agents, SLA
│   │   │   ├── kb_service.py            #   Knowledge base (30 true + 30 false)
│   │   │   ├── workflow_engine.py       #   Graph-based state machine
│   │   │   ├── workflow_repository.py   #   Workflow storage & versioning
│   │   │   ├── workflow_seeder.py       #   Default workflow templates
│   │   │   ├── workflow_seeder_advanced.py  # Advanced workflow templates
│   │   │   ├── classifier.py            #   LLM use-case classification
│   │   │   ├── risk_calculator.py       #   Multi-factor risk scoring
│   │   │   ├── text_validator.py        #   English text validation (heuristic)
│   │   │   ├── mistral_client.py        #   Mistral API client
│   │   │   ├── multimodal_processor.py  #   Audio/video/image processing
│   │   │   ├── ocr_service.py           #   OCR processing
│   │   │   ├── intent_detector.py       #   User intent understanding
│   │   │   ├── tts_service.py           #   Text-to-speech
│   │   │   ├── vad_service.py           #   Voice activity detection
│   │   │   ├── auth_service.py          #   Auth logic (OTP, JWT, bcrypt)
│   │   │   ├── connector_sync_service.py #  Bidirectional connector sync
│   │   │   ├── admin_audit_service.py   #   Admin action audit logging
│   │   │   ├── data_retention_service.py #  TTL and cleanup policies
│   │   │   └── mapping_service.py       #   Field mapping loading
│   │   ├── connectors/                  # Connector framework
│   │   │   ├── base_connector.py        #   Abstract connector interface
│   │   │   ├── connector_manager.py     #   Lifecycle orchestrator
│   │   │   ├── connector_registry.py    #   Auto-registration registry
│   │   │   ├── credential_vault.py      #   AES-256 credential encryption
│   │   │   ├── field_mapping_engine.py  #   Field transformation engine
│   │   │   ├── sync_event_bus.py        #   In-memory event queue + retry
│   │   │   ├── sap_default_mapping.py   #   SAP field mappings
│   │   │   ├── sn_default_mapping.py    #   ServiceNow field mappings
│   │   │   └── implementations/         #   Connector implementations
│   │   │       ├── servicenow/          #     ServiceNow connector
│   │   │       └── sap/                 #     SAP connector
│   │   ├── models/                      # Data models
│   │   │   ├── incident.py              #   Incident, Agent, IncidentStatus
│   │   │   ├── user.py                  #   User, UserRole
│   │   │   ├── knowledge_base.py        #   TrueIncidentKB, FalseIncidentKB
│   │   │   ├── workflow.py              #   Workflow, WorkflowNode
│   │   │   ├── connector.py             #   CanonicalTicket, SyncEvent, ExternalTicketLink
│   │   │   ├── tenant.py               #   Tenant, AdminGroup, TenantBranding
│   │   │   ├── admin_audit.py           #   AdminAuditLog
│   │   │   ├── risk_config.py           #   Risk configuration
│   │   │   ├── execution_log.py         #   Execution audit log
│   │   │   └── session_mode.py          #   Session state management
│   │   ├── core/                        # App configuration
│   │   │   ├── config.py                #   Settings (env vars)
│   │   │   ├── auth_dependencies.py     #   Auth middleware & role guards
│   │   │   ├── rate_limit.py            #   Rate limiter (slowapi)
│   │   │   ├── database.py              #   SQLite/PostgreSQL setup
│   │   │   └── mongodb.py               #   MongoDB connection
│   │   ├── schemas/                     # Pydantic request/response schemas
│   │   │   └── workflow_definition.py
│   │   └── constants/
│   │       └── use_cases.py             #   Supported use case definitions
│   └── scripts/
│       └── seed_users.py                # Database seeding (SKIP_SEED=true to disable)
│
├── frontend/
│   ├── package.json
│   ├── vite.config.js                   # Dev server (port 3000, proxy to 8000)
│   ├── tailwind.config.js
│   ├── index.html
│   ├── src/
│   │   ├── App.jsx                      # Route definitions & role guards
│   │   ├── main.jsx                     # React entry point
│   │   ├── index.css                    # Tailwind + custom styles
│   │   ├── contexts/
│   │   │   └── AuthContext.jsx          # JWT auth context (login, logout, refresh)
│   │   ├── services/
│   │   │   ├── api.js                   # All REST API functions
│   │   │   └── websocket.js             # WebSocket connection helper
│   │   ├── pages/
│   │   │   ├── LoginPage.jsx            #   Phone OTP + admin password login
│   │   │   ├── ProfessionalDashboard.jsx #  Main dashboard with AI chat
│   │   │   ├── IncidentReport.jsx       #   Incident report form
│   │   │   ├── AgentChat.jsx            #   WebSocket chat with AI agent
│   │   │   ├── MyReports.jsx            #   User incident history
│   │   │   ├── IncidentDetail.jsx       #   Incident detail + timeline
│   │   │   ├── FieldAgentDashboard.jsx  #   Agent's assigned incidents
│   │   │   ├── AgentIncidentWorkspace.jsx # Field workspace + resolution
│   │   │   ├── AdminDashboard.jsx       #   Company operations center
│   │   │   ├── SuperUserDashboard.jsx   #   Platform overview
│   │   │   ├── WorkflowManagement.jsx   #   Visual workflow builder
│   │   │   ├── KnowledgeBase.jsx        #   KB viewer + CRUD
│   │   │   ├── TenantManagement.jsx     #   Multi-tenant config
│   │   │   ├── ClientOnboarding.jsx     #   Tenant onboarding wizard
│   │   │   ├── ConnectorStatus.jsx      #   Connector health + sync logs
│   │   │   ├── ConnectorSetup.jsx       #   Connector configuration
│   │   │   └── TenantMappingEditor.jsx  #   Field mapping editor
│   │   └── components/
│   │       ├── ProtectedRoute.jsx       #   Role-based route guard
│   │       ├── SuperUserLayout.jsx      #   Admin sidebar layout
│   │       ├── FloatingChatWidget.jsx   #   Embedded AI chat widget
│   │       ├── HeroSection.jsx          #   Dashboard hero section
│   │       ├── ChatMessage.jsx          #   Chat message renderer
│   │       ├── ProfileDropdown.jsx      #   User profile menu
│   │       ├── NotificationBell.jsx     #   In-app notifications
│   │       ├── SyncStatusBadge.jsx      #   Connector sync status
│   │       ├── QuestionInput.jsx        #   Dynamic workflow question input
│   │       ├── UploadInput.jsx          #   File upload UI
│   │       ├── AudioRecorder.jsx        #   Mic recording
│   │       ├── VideoRecorder.jsx        #   Video recording
│   │       ├── ImageUploader.jsx        #   Camera/file image input
│   │       ├── LiveVoiceChat.jsx        #   Real-time voice chat
│   │       ├── IncidentMap.jsx          #   Leaflet map
│   │       ├── WorkflowVisualization.jsx #  Workflow diagram
│   │       ├── WorkflowBuilderVisual.jsx #  React Flow workflow editor
│   │       ├── OTPDisplay.jsx           #   Dev OTP display
│   │       └── workflow/                #   Workflow node components
│   │           ├── QuestionNode.jsx
│   │           ├── ConditionNode.jsx
│   │           ├── CalculateNode.jsx
│   │           ├── DecisionNode.jsx
│   │           ├── MLModelNode.jsx
│   │           └── NodePropertiesForm.jsx
│
├── README.md                            # This file
├── start_dev.bat                        # Start both backend + frontend
├── start_backend.bat                    # Start backend only
└── start_frontend.bat                   # Start frontend only
```

---

## User Roles

| Role | Access | Description |
|------|--------|-------------|
| **user** | Dashboard, Report, Chat, My Reports | End-user reporting gas incidents |
| **agent** | Agent Dashboard, Incident Workspace | Field engineer handling dispatched incidents |
| **company** | Admin Dashboard | Company admin managing incidents, assigning agents, handling ops requests |
| **super_user** | Super Dashboard, Workflows, KB, Tenants | Platform admin managing workflows, knowledge base, tenants |
| **admin** | All super_user permissions + system admin | Full system access |

---

## Frontend Pages

| Route | Page | Roles | Description |
|-------|------|-------|-------------|
| `/login` | LoginPage | Public | Phone + OTP login and admin credential login (unified) |
| `/` | ProfessionalDashboard | All authenticated | Main dashboard with AI chat, multimodal input, incident history |
| `/report` | IncidentReport | user | Incident report form (normal mode + manual report mode) |
| `/chat/:incidentId` | AgentChat | user | Real-time WebSocket chat with AI workflow agent |
| `/my-reports` | MyReports | user | User's incident history with status tracking, filtering, search |
| `/my-reports/:incidentId` | IncidentDetail | user | Incident detail view with timeline, agent tracking |
| `/agent/dashboard` | FieldAgentDashboard | agent | Agent's assigned incidents with status progression |
| `/agent/incidents/:incidentId` | AgentIncidentWorkspace | agent | Field workspace: GPS tracking, milestones, resolution checklist |
| `/company` | AdminDashboard | company, super_user, admin | Operations center: incidents, agent assignment, ops requests |
| `/super` | SuperUserDashboard | super_user, admin | Platform overview with tenant/KB/workflow stats |
| `/super/workflows` | WorkflowManagement | super_user, admin | Visual workflow builder and management |
| `/super/kb` | KnowledgeBase | super_user, admin | KB viewer: true/false incidents, search, CRUD |
| `/super/tenants` | TenantManagement | super_user, admin | Multi-tenant configuration |
| `/super/tenants/onboard` | ClientOnboarding | super_user, admin | Tenant onboarding wizard |
| `/super/tenants/:id/mappings` | TenantMappingEditor | super_user, admin | Field mapping editor with versioning |
| `/super/connectors` | ConnectorStatus | super_user, admin | Connector health, sync logs, dead letter queue |
| `/super/connectors/setup` | ConnectorSetup | super_user, admin | Connector configuration and activation |

---

## Backend API Reference

Base URL: `http://localhost:8000/api/v1`

### Authentication (`/auth`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/auth/send-otp` | Generate OTP for phone login |
| POST | `/auth/verify-otp` | Verify OTP, return JWT tokens |
| GET | `/auth/me` | Get current user profile |
| POST | `/auth/refresh` | Refresh access token |
| POST | `/auth/admin-login` | Admin/company credential login |

### Incidents (`/incidents`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/incidents/` | Create incident with auto-classification |
| GET | `/incidents/{id}` | Get incident detail with timeline & SLA |
| POST | `/incidents/manual-report` | Submit manual report (no-workflow fallback) |
| POST | `/incidents/{id}/assign` | Assign field agent |
| POST | `/incidents/{id}/resolve` | Mark resolved with checklist + text validation |
| PUT | `/incidents/{id}/agent-status` | Update agent status (ASSIGNED/EN_ROUTE/ON_SITE/IN_PROGRESS/COMPLETED) |
| POST | `/incidents/{id}/agent-location` | Update agent live GPS |
| POST | `/incidents/{id}/milestones` | Add field operation milestone |
| POST | `/incidents/{id}/assistance-requests` | Create assistance request |
| PATCH | `/incidents/{id}/assistance-requests/{rid}` | Update assistance request |
| POST | `/incidents/{id}/assistance-requests/{rid}/assign-backup` | Assign backup engineer |
| POST | `/incidents/{id}/item-requests` | Create item/equipment request |
| PATCH | `/incidents/{id}/item-requests/{rid}` | Update item request |
| POST | `/incidents/{id}/notifications` | Add customer notification |
| GET | `/incidents/{id}/notifications` | Get incident notifications |
| POST | `/incidents/{id}/user-notes` | Add user note |
| PUT | `/incidents/{id}/sms-preference` | Update SMS preference |
| GET | `/incidents/user/{userId}` | Get user's incidents |
| GET | `/incidents/company/{tenantId}` | Get company incidents |
| GET | `/incidents/company/{tenantId}/stats` | Get incident statistics |
| GET | `/incidents/company/{tenantId}/ops-requests` | Get operations request queue |
| GET | `/incidents/agent/{agentId}/incidents` | Get agent's assigned incidents |
| GET | `/incidents/agents/available` | Get available agents |
| GET | `/incidents/agents/all` | Get all agents |
| GET | `/incidents/notifications/{userId}` | Get user notifications |
| POST | `/incidents/notifications/{userId}/mark-read/{nid}` | Mark notification read |
| POST | `/incidents/notifications/{userId}/mark-all-read` | Mark all notifications read |

### Agents / WebSocket (`/agents`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| WS | `/agents/ws/{sessionId}` | Main chat WebSocket (text, workflow, classification) |
| WS | `/agents/ws/voice/{sessionId}` | Voice chat WebSocket (audio chunks, VAD, TTS) |
| GET | `/agents/session/{sessionId}/history` | Get conversation history |

**WebSocket Message Types (client to server):**

| Type | Purpose | Key Fields |
|------|---------|------------|
| `start` | Begin incident workflow | `incident_id, tenant_id, user_id, use_case, initial_data` |
| `user_input` | Send user response | `session_id, input` |
| `get_paused` | Get resumable incidents | `user_id, tenant_id` |
| `resume` | Resume paused incident | `session_id, incident_id` |

**WebSocket Message Types (server to client):**

| Type | Action | Purpose |
|------|--------|---------|
| `agent_message` | `awaiting_incident_report` | Initial prompt |
| `agent_message` | `question` | Workflow question with options |
| `agent_message` | `upload` | Request file upload |
| `agent_message` | `complete` | Workflow finished, outcome determined |
| `agent_message` | `no_workflow` | No matching workflow, redirect to manual report |
| `error` | - | Error message |

### Knowledge Base (`/kb`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/kb/stats` | KB entry counts and statistics |
| GET | `/kb/true` | Paginated true incident entries |
| GET | `/kb/false` | Paginated false incident entries |
| GET | `/kb/recent` | Recent entries (both types) |
| POST | `/kb/true` | Add true incident entry |
| POST | `/kb/false` | Add false incident entry |
| PUT | `/kb/{type}/{id}` | Update KB entry |
| DELETE | `/kb/{type}/{id}` | Delete KB entry |
| GET | `/kb/search` | Full-text search across KB |
| POST | `/kb/verify` | Verify incident against KB |

### Workflows (`/workflows`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/workflows/tenant/{tenantId}` | Get all workflows for tenant |
| GET | `/workflows/{id}` | Get workflow definition |
| POST | `/workflows/` | Create workflow |
| PUT | `/workflows/{id}` | Update workflow |
| GET | `/workflows/{id}/mermaid` | Get Mermaid diagram |

### Super User (`/super`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/super/tenants` | List all tenants with stats |
| GET | `/super/tenants/{id}` | Get tenant detail |
| GET | `/super/workflows` | List workflows with filters |
| POST | `/super/workflows` | Create workflow |
| GET | `/super/workflows/{id}` | Get workflow details |
| PUT | `/super/workflows/{id}` | Update workflow |
| DELETE | `/super/workflows/{id}` | Soft delete workflow |
| POST | `/super/workflows/{id}/publish` | Publish to production |
| POST | `/super/workflows/{id}/duplicate` | Duplicate workflow |
| POST | `/super/workflows/{id}/validate` | Validate structure |
| GET | `/super/workflows/{id}/versions` | List versions |
| POST | `/super/workflows/{id}/versions` | Create new version |
| POST | `/super/workflows/{id}/rollback/{v}` | Rollback to version |
| GET | `/super/workflows/{id}/compare/{v1}/{v2}` | Compare versions |
| GET | `/super/workflows/{id}/mermaid` | Mermaid diagram |
| GET | `/super/workflows/{id}/graph` | React Flow graph data |
| POST | `/super/workflows/{id}/preview` | Preview with test data |
| GET | `/super/risk-config/{tenantId}` | Get risk configuration |
| PUT | `/super/risk-config/{tenantId}` | Update risk configuration |
| GET | `/super/kb/true-incidents` | List true KB entries |
| POST | `/super/kb/true-incidents` | Add true KB entry |
| GET | `/super/kb/false-incidents` | List false KB entries |
| POST | `/super/kb/false-incidents` | Add false KB entry |
| GET | `/super/executions` | List workflow executions |
| GET | `/super/executions/{id}` | Get execution details |
| GET | `/super/executions/{id}/logs` | Get execution logs |
| GET | `/super/executions/stats` | Execution statistics |
| POST | `/super/executions/{id}/override` | Override workflow decision |

### Connectors (`/connectors`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/connectors/available` | List available connector types |
| GET | `/connectors/tenant/{tenantId}` | Get tenant's configured connectors |
| POST | `/connectors/configure` | Create connector configuration |
| PUT | `/connectors/{configId}` | Update connector config |
| POST | `/connectors/{configId}/credentials` | Store encrypted credentials |
| POST | `/connectors/{configId}/test` | Test connector connectivity |
| POST | `/connectors/{configId}/activate` | Activate connector |
| POST | `/connectors/{configId}/deactivate` | Deactivate connector |
| DELETE | `/connectors/{configId}` | Delete connector |
| GET | `/connectors/{configId}/health` | Connector health check |
| GET | `/connectors/sync/{tenantId}/status` | Get sync status |
| GET | `/connectors/sync/{tenantId}/logs` | Get sync event logs |
| GET | `/connectors/sync/{tenantId}/dead-letter` | Get dead-letter events |
| POST | `/connectors/sync/{tenantId}/dead-letter/{eventId}/replay` | Replay dead-letter event |
| POST | `/connectors/sync/{tenantId}/dead-letter/replay-all` | Replay all dead-letter events |
| GET | `/connectors/sync/{tenantId}/events/{eventId}/trace` | Get event trace |
| POST | `/connectors/backfill/{tenantId}` | Run connector backfill |
| POST | `/connectors/reconcile/{tenantId}` | Reconcile connector data |
| GET | `/connectors/retention/{tenantId}` | Get data retention policy |
| PUT | `/connectors/retention/{tenantId}` | Update retention policy |
| POST | `/connectors/retention/{tenantId}/cleanup` | Run retention cleanup |

### Tenants (`/tenants`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/tenants/` | Create new tenant |
| GET | `/tenants/` | List all tenants |
| GET | `/tenants/{tenantId}` | Get tenant details |
| PUT | `/tenants/{tenantId}` | Update tenant |
| PUT | `/tenants/{tenantId}/config` | Update tenant configuration |
| PUT | `/tenants/{tenantId}/status` | Update tenant status |
| DELETE | `/tenants/{tenantId}` | Delete tenant |
| POST | `/tenants/{tenantId}/users` | Create user for tenant |
| GET | `/tenants/{tenantId}/mappings/{connectorType}` | Get field mappings |
| PUT | `/tenants/{tenantId}/mappings/{connectorType}` | Update field mappings |
| GET | `/tenants/{tenantId}/mappings/{connectorType}/versions` | List mapping versions |
| POST | `/tenants/{tenantId}/mappings/{connectorType}/rollback/{v}` | Rollback mapping |
| GET | `/tenants/{tenantId}/admin-groups` | List admin groups |
| POST | `/tenants/{tenantId}/admin-groups` | Create admin group |
| PUT | `/tenants/{tenantId}/admin-groups/{groupId}` | Update admin group |
| DELETE | `/tenants/{tenantId}/admin-groups/{groupId}` | Delete admin group |
| PUT | `/tenants/{tenantId}/users/{userId}/admin-group` | Assign user to group |

### Webhooks (`/webhooks`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/webhooks/servicenow/{tenantId}` | ServiceNow inbound webhook |
| POST | `/webhooks/sap/{tenantId}` | SAP inbound webhook |

---

## Data Models

### Incident

```
incident_id            - Unique identifier (UUID)
tenant_id              - Tenant this incident belongs to
user_id                - Reporting user
description            - User's incident description
status                 - Current lifecycle status (see Incident Lifecycle)
outcome                - Final determination (emergency_dispatch, schedule_engineer, etc.)
risk_score             - Calculated risk score (0.0 - 1.0)
confidence_score       - Classification confidence
classified_use_case    - AI-classified incident type
structured_data        - Variables collected during workflow execution
workflow_execution_id  - Linked workflow execution
assigned_agent_id      - Assigned field agent
agent_status           - Agent progression (ASSIGNED → EN_ROUTE → ON_SITE → IN_PROGRESS → COMPLETED)
resolution_notes       - Agent's resolution notes
resolution_checklist   - Detailed resolution data (root_cause, actions_taken, verification, etc.)
items_used             - Equipment used during resolution
field_activity         - Milestone log with timestamps
assistance_requests    - Backup agent / help requests
item_requests          - Equipment/supply requests
customer_notifications - Notifications sent to the customer
agent_live_location    - Agent's current GPS coordinates
agent_location_history - GPS history trail
sla_hours              - SLA deadline in hours
kb_similarity_score    - KB match score
kb_match_type          - "true" | "false" | "unknown"
```

### User

```
user_id       - Unique identifier
phone         - Phone number (login via OTP)
full_name     - Display name
role          - user | agent | company | super_user | admin
tenant_id     - Associated tenant
is_active     - Account status
username      - For admin credential login
password_hash - bcrypt hash for admin login
```

### Workflow

```
workflow_id         - Unique identifier (e.g., "tenant_001_gas_smell_v1")
tenant_id           - Owning tenant
use_case            - Incident type this workflow handles
version             - Version number
start_node          - Entry point node ID
nodes               - List of WorkflowNode (QUESTION, CONDITION, CALCULATE, DECISION, etc.)
edges               - Connections between nodes with optional conditions
risk_factors        - Risk scoring weights
safety_overrides    - Override rules for safety-critical scenarios
decision_thresholds - Score thresholds for each outcome
```

### Knowledge Base

```
TrueIncidentKB:
  kb_id, tenant_id, incident_id, use_case, description,
  key_indicators, risk_factors, outcome, tags,
  resolution_summary, resolution_notes, root_cause, actions_taken,
  verified_by, verified_at

FalseIncidentKB:
  kb_id, tenant_id, incident_id, reported_as, actual_issue,
  false_positive_reason, key_indicators, tags,
  verified_by, verified_at
```

---

## Workflow System

### Node Types

| Type | Purpose | User Interaction |
|------|---------|-----------------|
| **QUESTION** | Ask user for information | Yes - waits for response |
| **CONDITION** | Evaluate expression, branch True/False | No - auto-advances |
| **CALCULATE** | Execute formula, store result | No - auto-advances |
| **DECISION** | Terminal node, determines outcome | No - ends workflow |
| **UPLOAD** | Request file upload from user | Yes - waits for file |
| **ML_MODEL** | Run ML model on inputs | No - auto-advances |
| **WAIT** | Pause for external event | Yes - waits |
| **PARALLEL** | Execute multiple branches | No - auto-advances |
| **HUMAN_OVERRIDE** | Allow manual intervention | Yes - waits |

### Execution Flow

```
1. User describes incident
2. Classifier determines use_case (gas_smell, weak_flame, etc.)
3. Workflow loaded for tenant + use_case
4. Engine starts at start_node
5. QUESTION nodes → ask user, store answer in variables
6. CONDITION nodes → evaluate expression, follow True/False branch
7. CALCULATE nodes → execute formula, store result
8. DECISION node → workflow complete, outcome determined
```

### Supported Use Cases

- `gas_smell` - Gas smell inside property
- `weak_flame` - Weak/yellow flame on stove
- `hissing_sound` - Hissing sound near gas line
- `suspected_co_leak` - CO leak with symptoms
- `meter_running_fast` - Unusually fast meter
- `meter_tampering` - Suspected meter fraud
- `smart_home_alert` - Smart sensor alert
- `underground_gas_leak` - Underground infrastructure leak
- `post_earthquake_gas_check` - Post-earthquake gas inspection
- `frozen_pipe_gas_interruption` - Frozen gas pipes
- And more...

### No-Workflow Fallback

When no workflow matches the classified use case:
1. Agent orchestrator catches the `ValueError`
2. Creates incident with status `PENDING_COMPANY_ACTION`
3. Sends `action: "no_workflow"` to frontend
4. Frontend redirects to `/report` in manual mode
5. User fills out detailed manual report form
6. Company receives notification for manual review

---

## Knowledge Base System

### How It Works

The KB system stores verified true and false incident patterns to improve future classification accuracy.

### Pre-Loaded Data

- **30 true incidents** - Gas emergencies (gas smell with symptoms, hissing sounds, CO alarms, corrosion, post-earthquake, frozen pipes, underground failures)
- **30 false incidents** - Common false alarms (cooking smells, pilot light issues, sewer gas, paint fumes, skunk spray, bleach fumes, asphalt, refrigerant)

### KB Verification (During Incident Workflow)

When a user completes a workflow:
1. `kb_service.verify_incident()` compares `structured_data` against all KB entries
2. Returns `true_kb_match` score, `false_kb_match` score, and `best_match_type`
3. Confidence adjustment (-0.3 to +0.3) is applied to the risk score
4. Result stored in `incident.kb_validation_details`

### KB Auto-Learning (On Resolution)

When a field agent resolves an incident:
1. `kb_service.add_from_incident()` is called automatically
2. High risk (>0.7) → added to **True KB** with resolution details
3. Low risk (<0.3) → added to **False KB** with false-positive reason
4. Medium risk (0.3-0.7) → not added automatically
5. Builds `resolution_summary`: *"This was a [confirmed/false] incident of type '[X]'. Root cause: [Y]. Resolution: [Z]."*
6. If a KB entry for the same use_case + tenant already exists, it updates the existing entry instead of creating a duplicate

### KB Entry Fields (Enhanced)

After resolution, KB entries include:
- `resolution_summary` - Human-readable summary
- `resolution_notes` - Agent's notes
- `root_cause` - Identified root cause
- `actions_taken` - Steps taken to resolve
- `verification_result` - True/false incident verification
- `incident_verified_as` - Whether confirmed or false alarm

### KB Management (Frontend)

- **Stats dashboard** - Total true, false, combined count, recent additions
- **Tabbed browsing** - True incidents / False incidents with pagination
- **Search** - Full-text search across descriptions and tags
- **CRUD** - Add manual entries, edit, delete with confirmation
- **Source badges** - Green for auto-learned from incident, gray for manually added

### Multi-Tenant KB

- Global entries (`tenant_id=null`) available to all tenants
- Tenant-specific entries only visible to that tenant
- Pagination and stats respect tenant filtering

---

## Risk Assessment

### Scoring Factors (UK Gas Safety Aligned)

| Factor | Points | Severity |
|--------|--------|----------|
| Safety symptoms (dizziness, nausea, headache) | 30 | Critical |
| CO alarm triggered | 30 | Critical |
| Strong gas smell | 20 | High |
| Meter running abnormally | 15 | High |
| Hissing sound detected | 15 | High |
| Audio leak confidence (ML) | 10 | Medium |
| Visual damage detected (CV) | 10 | Medium |
| Consumption anomaly | 10 | Medium |
| Nearby incident reports | 5 | Low |

Score normalized to 0-1 range.

### KB Confidence Adjustment

- Strong true KB match → +0.3 confidence boost
- Strong false KB match → -0.3 confidence penalty
- Unknown match → no adjustment

### Commercial Property Multiplier

- Commercial properties get **1.5x risk multiplier**
- Lower decision thresholds: Emergency >= 0.70, Schedule >= 0.40

### Decision Thresholds (Residential)

| Score Range | Outcome |
|-------------|---------|
| >= 0.80 | Emergency Dispatch |
| >= 0.50 | Schedule Engineer |
| >= 0.30 | Monitor |
| < 0.30 | Close With Guidance |

---

## Incident Lifecycle

### Status Flow

```
NEW → SUBMITTED → CLASSIFYING → IN_PROGRESS → (workflow execution) → COMPLETED
                                     ↓                                    ↓
                                   PAUSED                            DISPATCHED
                                (resumable)                          (agent assigned)
                                                                        ↓
                                                                     RESOLVED
                                                                        ↓
                                                                      CLOSED
```

### Special Statuses

- `PENDING_COMPANY_ACTION` - Manual report awaiting company review
- `EMERGENCY` - Immediate emergency dispatch
- `FALSE_REPORT` - Determined false alarm
- `WAITING_INPUT` - Waiting for user response
- `ANALYZING` - Processing multimodal input

### Outcomes

| Outcome | Description |
|---------|-------------|
| `emergency_dispatch` | Emergency services dispatched immediately |
| `schedule_engineer` | Field engineer visit scheduled |
| `monitor` | Situation monitored, no immediate action |
| `close_with_guidance` | Closed with safety guidance provided |
| `false_report` | Confirmed false alarm |

### SLA Configuration

| Outcome | Base Hours |
|---------|-----------|
| Emergency | 1 hour |
| Schedule Engineer | 4 hours |
| Monitor | 24 hours |
| Guidance/False | No SLA |

**Location multipliers:** Urban 1.0x, Suburban 1.5x, Rural 2.0x, Remote 3.0x

---

## Field Agent Operations

### Agent Status Progression

```
ASSIGNED → EN_ROUTE → ON_SITE → IN_PROGRESS → COMPLETED
```

### Resolution Workflow

1. Agent receives assignment notification
2. Agent marks **EN_ROUTE** (GPS tracking begins)
3. Agent arrives, marks **ON_SITE**
4. Agent clicks **Diagnosis Started** milestone → status becomes **IN_PROGRESS**
5. Resolution form unlocks (fields disabled until IN_PROGRESS)
6. Agent fills resolution checklist:
   - Resolution notes (English text validated)
   - Root cause analysis (English text validated)
   - Actions taken (English text validated)
   - Safety checks completed
   - Verification result (confirmed/false alarm)
7. Agent submits → **RESOLVED**
8. KB auto-learns from resolution

### Text Validation on Resolution

Resolution fields are validated using structural heuristics to reject gibberish:
- Vowel/consonant pattern analysis
- Consecutive character limits (max 4 consonants, max 3 vowels)
- Common English bigram frequency (>= 25% for words >= 5 chars)
- Rare bigram detection (impossible letter combinations)
- Minimum 3 words per field, >= 50% structurally plausible

Accepts: "Everything is fixed under guidance" (valid English)
Rejects: "anaogna aaknga skjfn" (gibberish)

### Field Features

- **Live GPS tracking** with location history
- **Milestone logging** with timestamps and notes
- **Assistance requests** - request backup engineers with priority levels
- **Item requests** - request equipment/supplies with delivery ETA
- **Customer notifications** - send updates to the reporting user
- **Camera input** - capture photos/video from field

---

## Authentication

### User/Agent Login (OTP)

1. `POST /auth/send-otp` with phone number (rate-limited: 5/minute)
2. Server generates 6-digit cryptographic OTP (5-minute TTL, max 5 attempts)
3. `POST /auth/verify-otp` with phone + OTP (rate-limited: 10/minute)
4. Returns `access_token` (30 min) + `refresh_token` (7 days)

### Admin/Company Login (Credentials)

1. `POST /auth/admin-login` with username + password (rate-limited: 10/minute)
2. Role must be `company`, `super_user`, or `admin`
3. Password verified with bcrypt
4. Returns same JWT token pair
5. Company admins get `connector_scope` embedded in JWT for RBAC

### JWT Configuration

- Algorithm: HS256
- Access token: 30 minutes
- Refresh token: 7 days (sent via JSON body, not URL)
- Payload: `user_id, email, role, tenant_id, connector_scope, type`

### Security

- All API endpoints require JWT authentication
- Rate limiting on auth endpoints (slowapi)
- Security headers: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy, Permissions-Policy, HSTS
- Global exception handler sanitizes error responses (no stack traces)
- SECRET_KEY validated at startup (minimum 32 characters)
- OTPs generated with `secrets` module (cryptographically secure)
- Source maps disabled in production builds

### Role-Based Access Control

Routes are protected with `require_role()` dependency:
```python
@router.get("/admin", dependencies=[Depends(require_role(UserRole.ADMIN))])
```

Frontend uses `<ProtectedRoute allowedRoles={['admin']}>` wrapper.

---

## Configuration

### Backend Environment Variables

```env
# Security — generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
SECRET_KEY=            # REQUIRED, min 32 chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS — comma-separated origins
ALLOWED_ORIGINS=https://your-domain.com

# Database
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_NAME=gas_incident_platform
DATABASE_URL=sqlite:///./gas_incidents.db
REDIS_URL=redis://localhost:6379

# AI/ML
MISTRAL_API_KEY=your-mistral-api-key
MISTRAL_AGENT_ID=your-agent-id
LLM_MODEL=mistral-large-latest
OPENAI_API_KEY=       # For Whisper transcription

# Connectors — generate separately from SECRET_KEY
CONNECTOR_ENCRYPTION_KEY=
CONNECTOR_SYNC_ENABLED=true

# Upload
MAX_UPLOAD_SIZE_MB=10
UPLOAD_DIR=./uploads

# Seeding — set true in production to skip demo data
SKIP_SEED=false
```

### Frontend Configuration

```env
VITE_API_URL=http://localhost:8000
```

Vite dev server runs on port 3000 with `/api` proxy to `localhost:8000`.

---

## Seeded Demo Data

The platform seeds demo users on startup for testing (disable with `SKIP_SEED=true`):
- Users, agents, company admins, and super users for the Cadent demo tenant

### Default Field Agents (5)

| Name | Specialization | Location |
|------|---------------|----------|
| John Smith | Gas Safety Engineer | Westminster, London |
| David Mitchell | Emergency Response Specialist | Canary Wharf, London |
| Robert Taylor | Senior Gas Inspector | Deansgate, Manchester |
| Thomas Brown | Leak Detection Technician | Headingley, Leeds |
| Daniel Wright | Pipeline Integrity Engineer | Clifton, Bristol |

### Default Workflows

On startup, workflows are seeded for each tenant covering all supported use cases (gas_smell, weak_flame, hissing_sound, etc.).

### Default KB Entries

30 true + 30 false incident entries covering common gas safety scenarios.

---

## Storage

**In-memory** (suitable for demo/prototype):
- Incidents, Agents, Sessions, Notifications
- KB entries (True/False)
- Workflows (in-memory repository)

**MongoDB** (persistent):
- User accounts and authentication
- OTP storage (5-min TTL)
- Tenant configuration
- Connector configs, credentials (AES-256 encrypted), field mappings
- Sync events, external ticket links
- Admin audit logs, admin groups

For production, migrate in-memory stores to MongoDB/PostgreSQL + Redis caching.

---

## License

MIT
