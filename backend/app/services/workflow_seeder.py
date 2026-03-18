"""
Workflow seeder - ensures default workflows exist for tenants.
Based on Cadent CO Data 2024-25 and CO Process Improvement analysis.
"""
import logging
from typing import List
from app.constants.use_cases import (
    DEFAULT_WORKFLOWS, CO_ALARM, SUSPECTED_CO_LEAK,
    CO_ORANGE_FLAMES, CO_SOOTING_SCARRING, CO_EXCESSIVE_CONDENSATION,
    CO_VISIBLE_FUMES, CO_BLOOD_TEST, CO_FATALITY, CO_SMOKE_ALARM,
    GAS_SMELL, HISSING_SOUND,
)
from app.schemas.workflow_definition import (
    WorkflowDefinition,
    WorkflowNode,
    WorkflowEdge,
    WorkflowNodeType,
)
from app.services.workflow_repository import workflow_repository
from app.services.workflow_seeder_co import (
    CO_ALARM_SUBWORKFLOW_CREATORS,
    _create_co_alarm_workflow,
    _create_suspected_co_leak_workflow,
    _create_co_orange_flames_workflow,
    _create_co_sooting_scarring_workflow,
    _create_co_excessive_condensation_workflow,
    _create_co_visible_fumes_workflow,
    _create_co_blood_test_workflow,
    _create_co_fatality_workflow,
    _create_co_smoke_alarm_workflow,
    _create_gas_smell_workflow,
    _create_hissing_sound_workflow,
)

logger = logging.getLogger(__name__)

# Map use cases to their workflow creator functions
WORKFLOW_CREATORS = {
    CO_ALARM: _create_co_alarm_workflow,
    SUSPECTED_CO_LEAK: _create_suspected_co_leak_workflow,
    CO_ORANGE_FLAMES: _create_co_orange_flames_workflow,
    CO_SOOTING_SCARRING: _create_co_sooting_scarring_workflow,
    CO_EXCESSIVE_CONDENSATION: _create_co_excessive_condensation_workflow,
    CO_VISIBLE_FUMES: _create_co_visible_fumes_workflow,
    CO_BLOOD_TEST: _create_co_blood_test_workflow,
    CO_FATALITY: _create_co_fatality_workflow,
    CO_SMOKE_ALARM: _create_co_smoke_alarm_workflow,
    GAS_SMELL: _create_gas_smell_workflow,
    HISSING_SOUND: _create_hissing_sound_workflow,
}


def seed_default_workflows_for_tenant(tenant_id: str) -> None:
    """
    Seed default workflows for a tenant if they don't exist.

    Args:
        tenant_id: Tenant identifier
    """
    logger.info(f"Seeding default workflows for tenant: {tenant_id}")

    seeded_count = 0

    for use_case in DEFAULT_WORKFLOWS:
        # Check if workflow already exists
        existing = workflow_repository.get_latest_by_tenant_use_case(tenant_id, use_case)

        if existing is not None:
            logger.info(f"  Workflow '{use_case}' already exists (version {existing.version})")
            continue

        # Look up the creator function
        creator = WORKFLOW_CREATORS.get(use_case)
        if creator is None:
            logger.warning(f"  No template for use_case: {use_case}")
            continue

        workflow = creator(tenant_id)

        try:
            workflow_repository.save(workflow)
            seeded_count += 1
            logger.info(f"  Created workflow '{use_case}' (ID: {workflow.workflow_id})")
        except ValueError as e:
            logger.error(f"  Failed to seed workflow '{use_case}': {e}")

    if seeded_count > 0:
        logger.info(f"Default workflows seeded for tenant '{tenant_id}': {seeded_count} workflows created")
    else:
        logger.info(f"All default workflows already exist for tenant '{tenant_id}'")

    manufacturer_seeded = 0
    for subflow_use_case, creator in CO_ALARM_SUBWORKFLOW_CREATORS.items():
        existing = workflow_repository.get_latest_by_tenant_use_case(tenant_id, subflow_use_case)
        if existing is not None:
            logger.info(f"  Manufacturer sub-workflow '{subflow_use_case}' already exists (version {existing.version})")
            continue

        workflow = creator(tenant_id)
        try:
            workflow_repository.save(workflow)
            manufacturer_seeded += 1
            logger.info(f"  Created manufacturer sub-workflow '{subflow_use_case}' (ID: {workflow.workflow_id})")
        except ValueError as e:
            logger.error(f"  Failed to seed manufacturer sub-workflow '{subflow_use_case}': {e}")

    if manufacturer_seeded > 0:
        logger.info(
            f"Manufacturer sub-workflows seeded for tenant '{tenant_id}': "
            f"{manufacturer_seeded} workflows created"
        )
