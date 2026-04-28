"""
FastAPI Backend - Gas Incident Intelligence Platform
Main application entry point
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
import logging
import os

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import incidents, workflows, agents, super_user, knowledge_base, auth, connectors, webhooks, tenants
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.database import init_db
from app.core.mongodb import connect_to_mongo, close_mongo_connection, get_database
from app.services.workflow_repository import register_default_workflow, workflow_repository
from app.services.workflow_seeder import seed_default_workflows_for_tenant
from app.scripts.seed_users import seed_users

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Security headers middleware ──────────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"
        # HSTS only when behind HTTPS reverse proxy
        if request.headers.get("x-forwarded-proto") == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


async def _init_connector_subsystem():
    """Initialize the connector framework: vault, manager, event bus, sync service.

    Called during startup. Wires the ServiceNow connector into the incident
    lifecycle so finalized incidents are automatically pushed to external systems.
    """
    from app.connectors.credential_vault import CredentialVault
    from app.connectors.connector_manager import ConnectorManager
    from app.connectors.sync_event_bus import SyncEventBus
    from app.services.connector_sync_service import ConnectorSyncService
    from app.services.mapping_service import load_active_mappings

    # Import connectors to trigger auto-registration
    import app.connectors.implementations.servicenow  # noqa: F401
    import app.connectors.implementations.sap  # noqa: F401

    # Initialize field mapping engine with default mappings
    from app.connectors.field_mapping_engine import mapping_engine
    from app.connectors.sn_default_mapping import get_default_sn_mapping
    from app.connectors.sap_default_mapping import get_default_sap_mapping
    default_sn_mapping = get_default_sn_mapping()
    default_sap_mapping = get_default_sap_mapping()
    mapping_engine.register_mapping(default_sn_mapping)
    mapping_engine.register_mapping(default_sap_mapping)
    logger.info("Field mapping engine initialized with SN + SAP default mappings")

    # Get incident_service from the agent orchestrator singleton
    from app.api.agents import agent_orchestrator
    incident_service = agent_orchestrator.incident_service

    # Create framework instances
    vault = CredentialVault(secret_key=settings.connector_encryption_key)
    manager = ConnectorManager(credential_vault=vault)
    bus = SyncEventBus()

    # Hydrate persisted state
    await vault.bootstrap_cache()
    await manager.load_from_db()
    await bus.hydrate_from_db()

    # Persist default global mappings once, then load active mappings.
    db = get_database()
    existing_sn_mapping = await db.field_mappings.find_one(
        {"tenant_id": None, "connector_type": "servicenow", "version": 1},
        {"_id": 1},
    )
    if not existing_sn_mapping:
        await db.field_mappings.insert_one(default_sn_mapping.model_dump())

    existing_sap_mapping = await db.field_mappings.find_one(
        {"tenant_id": None, "connector_type": "sap", "version": 1},
        {"_id": 1},
    )
    if not existing_sap_mapping:
        await db.field_mappings.insert_one(default_sap_mapping.model_dump())

    await load_active_mappings()

    # Create sync service and wire it into incident service
    sync_service = ConnectorSyncService(
        connector_manager=manager,
        sync_event_bus=bus,
        incident_service=incident_service,
        db=db,
    )
    sync_service.initialize()

    if settings.CONNECTOR_SYNC_ENABLED:
        incident_service.set_sync_service(sync_service)
        logger.info("Connector sync enabled — outbound hooks active")
    else:
        logger.info("Connector sync disabled (CONNECTOR_SYNC_ENABLED=false)")

    # Inject into API routers
    connectors.init_connector_api(manager, bus, sync_service)
    webhooks.init_webhook_api(manager, bus, sync_service)

    # Rehydrate active connectors
    await manager.hydrate_active_connectors()

    logger.info("Connector subsystem initialized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Fail fast if SECRET_KEY is weak or missing
    if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
        raise RuntimeError(
            "SECRET_KEY is missing or too short (min 32 chars). "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )

    logger.info("Starting Gas Incident Intelligence Platform")
    await init_db()

    # Connect to MongoDB and seed users/tenants
    await connect_to_mongo()
    db = get_database()
    await seed_users(db)

    # Seed default tenant configuration
    from app.api.tenants import seed_tenants
    await seed_tenants()

    # Load persisted workflows and incidents before seeding defaults
    await workflow_repository.load_from_db()

    # Load tenant user cache for notification routing
    from app.api.agents import agent_orchestrator
    await agent_orchestrator.incident_service.load_from_db(db)
    await agent_orchestrator.incident_service.load_tenant_users(db)
    await agent_orchestrator.load_sessions_from_db()

    # Seed default workflows for demo tenant
    logger.info("Seeding default workflows...")
    seed_default_workflows_for_tenant("tenant_demo")

    # Keep legacy registration for backward compatibility
    register_default_workflow()

    # Load Knowledge Base from MongoDB (persists manual/auto entries across restarts)
    await agent_orchestrator.kb_service.load_from_db()

    # Initialize connector subsystem (ServiceNow outbound, etc.)
    await _init_connector_subsystem()

    yield
    await close_mongo_connection()
    logger.info("Shutting down")


app = FastAPI(
    title="Gas Incident Intelligence API",
    version="1.0.0",
    lifespan=lifespan
)

# ── Rate limiter ─────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Security headers ─────────────────────────────────────────────────────
app.add_middleware(SecurityHeadersMiddleware)

# ── CORS middleware ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


# ── Global exception handler — sanitize error responses ──────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

# Include routers
app.include_router(incidents.router, prefix="/api/v1/incidents", tags=["incidents"])
app.include_router(workflows.router, prefix="/api/v1/workflows", tags=["workflows"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
app.include_router(super_user.router, prefix="/api/v1/super", tags=["super-user"])
app.include_router(knowledge_base.router, prefix="/api/v1/kb", tags=["knowledge-base"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["authentication"])
app.include_router(connectors.router, prefix="/api/v1/connectors", tags=["connectors"])
app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["webhooks"])
app.include_router(tenants.router, prefix="/api/v1/tenants", tags=["tenants"])

# Static file serving for tenant uploads (logos, avatars, etc.)
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


@app.get("/")
async def root():
    return {"message": "Gas Incident Intelligence API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
