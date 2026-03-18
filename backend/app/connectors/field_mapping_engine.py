"""FieldMappingEngine — declarative field mapping between external systems and CanonicalTicket.

Applies FieldMapping rules (from connector.py models) to transform data
bidirectionally without hardcoded field-by-field logic.  Supports five
transform types: DIRECT, ENUM_MAP, SCALE, TEMPLATE, CUSTOM.

Usage:
    from app.connectors.field_mapping_engine import mapping_engine
    mapping_engine.register_mapping(get_default_sn_mapping())

    # Inbound: external dict -> CanonicalTicket
    ticket = mapping_engine.external_to_canonical_ticket(sn_data, ConnectorType.SERVICENOW)

    # Outbound: CanonicalTicket -> external dict
    payload = mapping_engine.canonical_ticket_to_external(ticket, ConnectorType.SERVICENOW)
"""
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.models.connector import (
    CanonicalPriority,
    CanonicalStatus,
    CanonicalTicket,
    ConnectorType,
    FieldMapDirection,
    FieldMapEntry,
    FieldMapping,
    FieldTransformType,
)

logger = logging.getLogger(__name__)


class FieldMappingEngine:
    """Applies FieldMapping rules to transform data between external systems and canonical format.

    Mapping lookup order: tenant-specific -> global default (tenant_id=None).
    """

    def __init__(self) -> None:
        # Mapping store: (connector_type, tenant_id) -> FieldMapping
        # tenant_id=None is the global default
        self._mappings: Dict[Tuple[ConnectorType, Optional[str]], FieldMapping] = {}
        # Custom transform handlers: name -> callable(value, full_data) -> transformed_value
        self._custom_handlers: Dict[str, Callable] = {}

    # ── Registration ───────────────────────────────────────────────────────

    def register_mapping(self, mapping: FieldMapping) -> None:
        """Register a field mapping (global default or per-tenant override)."""
        key = (mapping.connector_type, mapping.tenant_id)
        self._mappings[key] = mapping
        scope = f"tenant={mapping.tenant_id}" if mapping.tenant_id else "global"
        logger.info(
            "Registered %s field mapping for %s (v%d, %d entries)",
            scope, mapping.connector_type.value, mapping.version, len(mapping.field_maps),
        )

    def get_mapping(
        self, connector_type: ConnectorType, tenant_id: Optional[str] = None
    ) -> Optional[FieldMapping]:
        """Look up a mapping with fallback: tenant-specific -> global default."""
        if tenant_id:
            tenant_mapping = self._mappings.get((connector_type, tenant_id))
            if tenant_mapping and tenant_mapping.is_active:
                return tenant_mapping
        return self._mappings.get((connector_type, None))

    def register_custom_handler(self, name: str, fn: Callable) -> None:
        """Register a named custom transform function.

        Signature: fn(value: Any, full_data: Dict[str, Any]) -> Any
        """
        self._custom_handlers[name] = fn
        logger.info("Registered custom transform handler: %s", name)

    # ── Inbound: External -> Canonical ─────────────────────────────────────

    def to_canonical(
        self,
        external_data: Dict[str, Any],
        connector_type: ConnectorType,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Apply inbound field mappings: external data -> canonical field dict.

        Iterates FieldMapEntry entries where direction is INBOUND or BOTH.
        Returns a flat dict of canonical_field -> transformed_value.
        """
        mapping = self.get_mapping(connector_type, tenant_id)
        if not mapping:
            logger.warning("No mapping found for %s (tenant=%s)", connector_type.value, tenant_id)
            return {}

        result: Dict[str, Any] = {}
        missing_required: List[str] = []

        for entry in mapping.field_maps:
            if entry.direction not in (FieldMapDirection.INBOUND, FieldMapDirection.BOTH):
                continue

            raw_value = self._resolve_external_value(external_data, entry.external_field)

            if raw_value is None or raw_value == "":
                if entry.is_required:
                    missing_required.append(entry.external_field)
                continue

            transformed = self._apply_transform_inbound(raw_value, entry, external_data)
            if transformed is not None:
                result[entry.canonical_field] = transformed

        if missing_required:
            logger.warning("Missing required inbound fields: %s", missing_required)

        return result

    # ── Outbound: Canonical -> External ────────────────────────────────────

    def to_external(
        self,
        canonical_data: Dict[str, Any],
        connector_type: ConnectorType,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Apply outbound field mappings: canonical data -> external field dict.

        Iterates FieldMapEntry entries where direction is OUTBOUND or BOTH.
        Returns a flat dict of external_field -> transformed_value.
        """
        mapping = self.get_mapping(connector_type, tenant_id)
        if not mapping:
            logger.warning("No mapping found for %s (tenant=%s)", connector_type.value, tenant_id)
            return {}

        result: Dict[str, Any] = {}

        for entry in mapping.field_maps:
            if entry.direction not in (FieldMapDirection.OUTBOUND, FieldMapDirection.BOTH):
                continue

            value = canonical_data.get(entry.canonical_field)

            if value is None or value == "":
                continue

            # Resolve enum values to their string representation
            if hasattr(value, "value"):
                value = value.value

            transformed = self._apply_transform_outbound(value, entry, canonical_data)
            if transformed is not None:
                result[entry.external_field] = transformed

        return result

    # ── Convenience Wrappers ───────────────────────────────────────────────

    def external_to_canonical_ticket(
        self,
        external_data: Dict[str, Any],
        connector_type: ConnectorType,
        tenant_id: Optional[str] = None,
    ) -> CanonicalTicket:
        """Transform external data into a CanonicalTicket instance.

        Calls to_canonical(), then handles datetime parsing, enum coercion,
        and risk_score derivation from the mapping's priority_to_risk table.
        """
        canonical_dict = self.to_canonical(external_data, connector_type, tenant_id)
        mapping = self.get_mapping(connector_type, tenant_id)

        # Parse datetime fields from strings
        for field in ("created_at", "updated_at", "resolved_at", "closed_at", "sla_due_at"):
            if field in canonical_dict and isinstance(canonical_dict[field], str):
                canonical_dict[field] = self._parse_datetime(canonical_dict[field])

        # Coerce status to CanonicalStatus enum
        if "status" in canonical_dict:
            try:
                canonical_dict["status"] = CanonicalStatus(canonical_dict["status"])
            except ValueError:
                canonical_dict["status"] = CanonicalStatus.NEW

        # Coerce priority to CanonicalPriority enum
        if "priority" in canonical_dict:
            try:
                canonical_dict["priority"] = CanonicalPriority(canonical_dict["priority"])
            except ValueError:
                canonical_dict["priority"] = CanonicalPriority.MEDIUM

        # Derive risk_score from priority using the mapping's priority_to_risk table
        if "risk_score" not in canonical_dict and mapping and mapping.priority_to_risk:
            pri_val = canonical_dict.get("priority")
            if pri_val:
                pri_str = pri_val.value if hasattr(pri_val, "value") else str(pri_val)
                canonical_dict["risk_score"] = mapping.priority_to_risk.get(pri_str, 0.5)

        # Defaults
        canonical_dict.setdefault("source_system", connector_type.value)
        if "ticket_id" not in canonical_dict and "external_id" in canonical_dict:
            canonical_dict["ticket_id"] = canonical_dict["external_id"]

        return CanonicalTicket(**canonical_dict)

    def canonical_ticket_to_external(
        self,
        ticket: CanonicalTicket,
        connector_type: ConnectorType,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Transform a CanonicalTicket into an external system payload dict.

        Serializes ticket to a dict then applies outbound field mappings.
        """
        ticket_dict = ticket.model_dump()
        return self.to_external(ticket_dict, connector_type, tenant_id)

    # ── Transform Application ──────────────────────────────────────────────

    def _apply_transform_inbound(
        self, value: Any, entry: FieldMapEntry, full_data: Dict[str, Any]
    ) -> Any:
        """Apply a single inbound transform based on the entry's transform_type."""
        config = entry.transform_config
        tt = entry.transform_type

        if tt == FieldTransformType.DIRECT:
            return self._resolve_display_value(value)

        if tt == FieldTransformType.ENUM_MAP:
            enum_map = config.get("map", {})
            # For enum lookups, use the machine value (e.g., "6") not display_value ("Resolved")
            resolved = str(self._resolve_machine_value(value))
            return enum_map.get(resolved, resolved)

        if tt == FieldTransformType.SCALE:
            return self._apply_scale(value, config, reverse=False)

        if tt == FieldTransformType.TEMPLATE:
            template = config.get("template", "{value}")
            try:
                return template.format(value=value, **full_data)
            except (KeyError, IndexError):
                return str(value)

        if tt == FieldTransformType.CUSTOM:
            handler_name = config.get("handler")
            if handler_name and handler_name in self._custom_handlers:
                return self._custom_handlers[handler_name](value, full_data)
            logger.warning("Custom handler '%s' not registered", handler_name)
            return value

        return value

    def _apply_transform_outbound(
        self, value: Any, entry: FieldMapEntry, full_data: Dict[str, Any]
    ) -> Any:
        """Apply a single outbound (reverse) transform based on the entry's transform_type."""
        config = entry.transform_config
        tt = entry.transform_type

        if tt == FieldTransformType.DIRECT:
            return value

        if tt == FieldTransformType.ENUM_MAP:
            reverse_map = config.get("reverse_map")
            if not reverse_map:
                # Auto-invert the forward map
                forward_map = config.get("map", {})
                reverse_map = {v: k for k, v in forward_map.items()}
            return reverse_map.get(str(value), str(value))

        if tt == FieldTransformType.SCALE:
            return self._apply_scale(value, config, reverse=True)

        if tt == FieldTransformType.TEMPLATE:
            reverse_template = config.get("reverse_template")
            if reverse_template:
                try:
                    return reverse_template.format(value=value, **full_data)
                except (KeyError, IndexError):
                    return str(value)
            return value

        if tt == FieldTransformType.CUSTOM:
            handler_name = config.get("reverse_handler")
            if handler_name and handler_name in self._custom_handlers:
                return self._custom_handlers[handler_name](value, full_data)
            logger.warning("Custom reverse handler '%s' not registered", handler_name)
            return value

        return value

    # ── Utility Methods ────────────────────────────────────────────────────

    @staticmethod
    def _resolve_display_value(value: Any) -> Any:
        """Resolve ServiceNow-style display_value dict to a human-readable value.

        SN returns reference fields as {"value": "sys_id", "display_value": "Name"}.
        Prefers display_value (human-readable). Used by DIRECT transforms.
        """
        if isinstance(value, dict):
            return value.get("display_value") or value.get("value") or ""
        return value

    @staticmethod
    def _resolve_machine_value(value: Any) -> Any:
        """Resolve ServiceNow-style dict to the machine value (code/ID).

        Prefers "value" (e.g., "6") over "display_value" (e.g., "Resolved").
        Used by ENUM_MAP transforms where lookup keys are codes, not labels.
        """
        if isinstance(value, dict):
            return value.get("value") or value.get("display_value") or ""
        return value

    @staticmethod
    def _resolve_external_value(data: Dict[str, Any], field_name: str) -> Any:
        """Get a value from external data, handling dotted field names.

        Supports:
        - Flat keys: data["field_name"]
        - Dotted paths: data["parent"]["child"] or data["parent"]["display_value"]
        """
        # Exact key match (SN Table API can return "caller_id.name" as a flat key)
        if field_name in data:
            return data[field_name]
        # Dotted path resolution
        if "." in field_name:
            parts = field_name.split(".", 1)
            parent = data.get(parts[0])
            if isinstance(parent, dict):
                return parent.get(parts[1]) or parent.get("display_value")
        return None

    @staticmethod
    def _apply_scale(
        value: Any, config: Dict[str, Any], reverse: bool = False
    ) -> Optional[float]:
        """Apply linear scale transform (or its reverse).

        Config: {"input_min", "input_max", "output_min", "output_max", "invert": bool}
        Forward:  output_min + normalized * (output_max - output_min)
        Reverse:  swaps input/output ranges, keeps invert flag.
        """
        try:
            val = float(value)
        except (TypeError, ValueError):
            return None

        input_min = config.get("input_min", 0)
        input_max = config.get("input_max", 1)
        output_min = config.get("output_min", 0)
        output_max = config.get("output_max", 1)
        invert = config.get("invert", False)

        if reverse:
            # Swap ranges to reverse the mapping direction
            input_min, output_min = output_min, input_min
            input_max, output_max = output_max, input_max

        input_range = input_max - input_min
        if input_range == 0:
            return output_min

        normalized = (val - input_min) / input_range
        if invert:
            normalized = 1.0 - normalized

        result = output_min + normalized * (output_max - output_min)
        return round(result, 4)

    @staticmethod
    def _parse_datetime(value: str) -> Optional[datetime]:
        """Parse a datetime string (ISO format or SN format YYYY-MM-DD HH:MM:SS)."""
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None


# ── Module-level singleton ─────────────────────────────────────────────────
mapping_engine = FieldMappingEngine()
