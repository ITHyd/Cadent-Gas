"""In-memory storage for graph-based workflow definitions."""
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.core.mongodb import get_database
from app.schemas.workflow_definition import (
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeType,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowRepository:
    def __init__(self) -> None:
        self._store: Dict[str, List[WorkflowDefinition]] = {}
        self._active_versions: Dict[str, int] = {}  # workflow_id -> active version number

    async def load_from_db(self) -> None:
        db = get_database()
        if db is None:
            return

        docs = await db.workflow_definitions.find({}, {"_id": 0}).sort(
            [("workflow_id", 1), ("version", 1)]
        ).to_list(None)

        self._store = {}
        self._active_versions = {}

        for doc in docs:
            is_active = bool(doc.pop("is_active", False))
            workflow = WorkflowDefinition.model_validate(doc)
            versions = self._store.setdefault(workflow.workflow_id, [])
            versions.append(workflow)
            if is_active:
                self._active_versions[workflow.workflow_id] = workflow.version

        for workflow_id, versions in self._store.items():
            versions.sort(key=lambda item: item.version)
            if workflow_id not in self._active_versions and versions:
                self._active_versions[workflow_id] = max(versions, key=lambda item: item.version).version

    async def _persist_workflow(self, workflow: WorkflowDefinition, is_active: bool) -> None:
        db = get_database()
        if db is None:
            return
        doc = workflow.model_dump(mode="json")
        doc["is_active"] = is_active
        await db.workflow_definitions.replace_one(
            {"workflow_id": workflow.workflow_id, "version": workflow.version},
            doc,
            upsert=True,
        )

    async def _persist_active_state(self, workflow_id: str) -> None:
        db = get_database()
        if db is None:
            return
        active_version = self._active_versions.get(workflow_id)
        await db.workflow_definitions.update_many(
            {"workflow_id": workflow_id},
            [{"$set": {"is_active": {"$eq": ["$version", active_version]}}}],
        )

    async def _delete_version_from_db(self, workflow_id: str, version: int) -> None:
        db = get_database()
        if db is None:
            return
        await db.workflow_definitions.delete_one({"workflow_id": workflow_id, "version": version})

    def _schedule_coro(self, coro) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            pass

    def save(self, workflow: WorkflowDefinition) -> WorkflowDefinition:
        versions = self._store.setdefault(workflow.workflow_id, [])
        if any(existing.version == workflow.version for existing in versions):
            raise ValueError(
                f"Workflow '{workflow.workflow_id}' version '{workflow.version}' already exists"
            )

        stored_workflow = workflow.model_copy(deep=True)
        stored_workflow.updated_at = _utc_now()
        versions.append(stored_workflow)
        versions.sort(key=lambda item: item.version)
        # Auto-activate the first version of a new workflow
        if workflow.workflow_id not in self._active_versions:
            self._active_versions[workflow.workflow_id] = workflow.version
        self._schedule_coro(
            self._persist_workflow(
                stored_workflow,
                is_active=self._active_versions.get(workflow.workflow_id) == stored_workflow.version,
            )
        )
        return stored_workflow.model_copy(deep=True)

    def update(
        self, workflow_id: str, updated_workflow: WorkflowDefinition
    ) -> WorkflowDefinition:
        versions = self._store.get(workflow_id)
        if not versions:
            raise KeyError(f"Workflow '{workflow_id}' not found")

        latest = max(versions, key=lambda item: item.version)
        now = _utc_now()

        new_version = updated_workflow.model_copy(
            update={
                "workflow_id": workflow_id,
                "version": latest.version + 1,
                "created_at": now,
                "updated_at": now,
            },
            deep=True,
        )
        versions.append(new_version)
        versions.sort(key=lambda item: item.version)
        # Auto-activate newly created versions
        self._active_versions[workflow_id] = new_version.version
        self._schedule_coro(self._persist_workflow(new_version, is_active=True))
        self._schedule_coro(self._persist_active_state(workflow_id))
        return new_version.model_copy(deep=True)

    def get_by_id(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        versions = self._store.get(workflow_id, [])
        if not versions:
            return None
        active_ver = self._active_versions.get(workflow_id)
        if active_ver is not None:
            for wf in versions:
                if wf.version == active_ver:
                    return wf.model_copy(deep=True)
        # Fallback to highest version if no active version set
        latest = max(versions, key=lambda item: item.version)
        return latest.model_copy(deep=True)

    def get_latest_by_tenant_use_case(
        self, tenant_id: str, use_case: str
    ) -> Optional[WorkflowDefinition]:
        # Find workflow_ids that match tenant_id + use_case
        candidates: List[WorkflowDefinition] = []
        for wf_id, versions in self._store.items():
            matching = [wf for wf in versions if wf.tenant_id == tenant_id and wf.use_case == use_case]
            if not matching:
                continue
            # Prefer the active version for this workflow_id
            active_ver = self._active_versions.get(wf_id)
            picked = None
            if active_ver is not None:
                for wf in matching:
                    if wf.version == active_ver:
                        picked = wf
                        break
            if picked is None:
                picked = max(matching, key=lambda item: item.version)
            candidates.append(picked)

        if not candidates:
            return None
        best = max(candidates, key=lambda item: item.version)
        return best.model_copy(deep=True)

    def list_by_tenant(self, tenant_id: str) -> List[WorkflowDefinition]:
        tenant_workflows: List[WorkflowDefinition] = []
        for versions in self._store.values():
            tenant_workflows.extend(
                workflow.model_copy(deep=True)
                for workflow in versions
                if workflow.tenant_id == tenant_id
            )

        return sorted(
            tenant_workflows,
            key=lambda item: (item.workflow_id, item.version),
        )

    def list_all(self) -> List[WorkflowDefinition]:
        all_workflows: List[WorkflowDefinition] = []
        for versions in self._store.values():
            all_workflows.extend(workflow.model_copy(deep=True) for workflow in versions)
        return sorted(all_workflows, key=lambda item: (item.workflow_id, item.version))

    def list_versions(self, workflow_id: str) -> List[WorkflowDefinition]:
        versions = self._store.get(workflow_id, [])
        return sorted((wf.model_copy(deep=True) for wf in versions), key=lambda item: item.version)

    def get_version(self, workflow_id: str, version: int) -> Optional[WorkflowDefinition]:
        versions = self._store.get(workflow_id, [])
        for wf in versions:
            if wf.version == version:
                return wf.model_copy(deep=True)
        return None

    def rollback_to_version(self, workflow_id: str, version: int) -> WorkflowDefinition:
        versions = self._store.get(workflow_id)
        if not versions:
            raise KeyError(f"Workflow '{workflow_id}' not found")

        target = None
        for wf in versions:
            if wf.version == version:
                target = wf
                break
        if target is None:
            raise KeyError(f"Workflow '{workflow_id}' version '{version}' not found")

        latest = max(versions, key=lambda item: item.version)
        now = _utc_now()
        new_version = target.model_copy(
            update={
                "workflow_id": workflow_id,
                "version": latest.version + 1,
                "created_at": now,
                "updated_at": now,
            },
            deep=True,
        )
        versions.append(new_version)
        versions.sort(key=lambda item: item.version)
        self._active_versions[workflow_id] = new_version.version
        self._schedule_coro(self._persist_workflow(new_version, is_active=True))
        self._schedule_coro(self._persist_active_state(workflow_id))
        return new_version.model_copy(deep=True)

    def rename_version(self, workflow_id: str, version: int, label: str) -> WorkflowDefinition:
        versions = self._store.get(workflow_id)
        if not versions:
            raise KeyError(f"Workflow '{workflow_id}' not found")
        for wf in versions:
            if wf.version == version:
                wf.version_label = label
                wf.updated_at = _utc_now()
                self._schedule_coro(
                    self._persist_workflow(
                        wf,
                        is_active=self._active_versions.get(workflow_id) == wf.version,
                    )
                )
                return wf.model_copy(deep=True)
        raise KeyError(f"Workflow '{workflow_id}' version '{version}' not found")

    def delete_version(self, workflow_id: str, version: int) -> None:
        versions = self._store.get(workflow_id)
        if not versions:
            raise KeyError(f"Workflow '{workflow_id}' not found")
        remaining = [wf for wf in versions if wf.version != version]
        if len(remaining) == len(versions):
            raise KeyError(f"Workflow '{workflow_id}' version '{version}' not found")
        if not remaining:
            self._store.pop(workflow_id, None)
            self._active_versions.pop(workflow_id, None)
        else:
            self._store[workflow_id] = remaining
            # If we deleted the active version, activate the highest remaining
            if self._active_versions.get(workflow_id) == version:
                self._active_versions[workflow_id] = max(remaining, key=lambda w: w.version).version
            self._schedule_coro(self._persist_active_state(workflow_id))
        self._schedule_coro(self._delete_version_from_db(workflow_id, version))

    def activate_version(self, workflow_id: str, version: int) -> WorkflowDefinition:
        versions = self._store.get(workflow_id)
        if not versions:
            raise KeyError(f"Workflow '{workflow_id}' not found")
        for wf in versions:
            if wf.version == version:
                self._active_versions[workflow_id] = version
                self._schedule_coro(self._persist_active_state(workflow_id))
                return wf.model_copy(deep=True)
        raise KeyError(f"Workflow '{workflow_id}' version '{version}' not found")

    def get_active_version(self, workflow_id: str) -> Optional[int]:
        return self._active_versions.get(workflow_id)


workflow_repository = WorkflowRepository()


def register_default_workflow() -> None:
    """Register default sample workflow at application startup."""
    if workflow_repository.get_by_id("gas_smell_v1") is not None:
        return

    default_workflow = WorkflowDefinition(
        workflow_id="gas_smell_v1",
        tenant_id="default_tenant",
        use_case="gas_smell",
        version=1,
        start_node="node_1",
        nodes=[
            WorkflowNode(
                id="node_1",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "How strong is the gas smell?",
                    "variable": "smell_intensity",
                },
            ),
            WorkflowNode(
                id="node_2",
                type=WorkflowNodeType.CONDITION,
                data={"expression": "smell_intensity == 'high'"},
            ),
            WorkflowNode(
                id="node_3",
                type=WorkflowNodeType.DECISION,
                data={"outcome": "emergency"},
            ),
        ],
        edges=[
            WorkflowEdge(source="node_1", target="node_2"),
            WorkflowEdge(source="node_2", target="node_3", condition="True"),
        ],
    )
    workflow_repository.save(default_workflow)
