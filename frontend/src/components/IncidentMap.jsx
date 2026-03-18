import { useEffect, useMemo, useState } from "react";
import {
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  useMap,
  ZoomControl,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// Fix default Leaflet icon paths.
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl:
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png",
  iconUrl:
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png",
  shadowUrl:
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png",
});

const riskStyles = {
  critical: { color: "#b91c1c", bg: "#fee2e2" },
  high: { color: "#b45309", bg: "#fef3c7" },
  medium: { color: "#a16207", bg: "#fef9c3" },
  low: { color: "#047857", bg: "#dcfce7" },
};

const getRiskLevel = (score = 0) => {
  if (score >= 0.8) return "critical";
  if (score >= 0.5) return "high";
  if (score >= 0.3) return "medium";
  return "low";
};

const createIncidentIcon = (riskScore = 0) => {
  const level = getRiskLevel(riskScore);
  const dotColor =
    level === "critical"
      ? "#dc2626"
      : level === "high"
        ? "#d97706"
        : level === "medium"
          ? "#ca8a04"
          : "#059669";

  return L.divIcon({
    className: "incident-marker-icon",
    html: `
      <div style="display:flex;align-items:center;justify-content:center;">
        <div style="
          width: 30px;
          height: 30px;
          border-radius: 999px;
          border: 3px solid #fff;
          background: ${dotColor};
          box-shadow: 0 10px 20px rgba(15,31,51,0.32);
          color: #fff;
          font-size: 10px;
          font-weight: 800;
          font-family: 'Nunito', 'Calibri', sans-serif;
          display:flex;
          align-items:center;
          justify-content:center;
          animation: incidentPulse 2s ease-in-out infinite;
        ">INC</div>
      </div>
    `,
    iconSize: [30, 30],
    iconAnchor: [15, 30],
    popupAnchor: [0, -30],
  });
};

const createAgentIcon = (name = "Agent") => {
  const initials = name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return L.divIcon({
    className: "agent-marker-icon",
    html: `
      <div style="display:flex;flex-direction:column;align-items:center;">
        <div style="
          width: 40px;
          height: 40px;
          border-radius: 999px;
          border: 3px solid #fff;
          background: #030304;
          box-shadow: 0 10px 20px rgba(3,3,4,0.4);
          color: #fff;
          font-size: 13px;
          font-weight: 800;
          font-family: 'Nunito', 'Calibri', sans-serif;
          display:flex;
          align-items:center;
          justify-content:center;
          animation: agentPulse 2s ease-in-out infinite;
        ">${initials}</div>
        <div style="
          margin-top: 5px;
          border-radius: 999px;
          padding: 2px 9px;
          background: #030304;
          color: #fff;
          font-size: 10px;
          font-weight: 700;
          font-family: 'Nunito', 'Calibri', sans-serif;
          white-space: nowrap;
          box-shadow: 0 8px 16px -10px rgba(3,3,4,0.7);
        ">${name}</div>
      </div>
    `,
    iconSize: [86, 62],
    iconAnchor: [43, 31],
    popupAnchor: [0, -28],
  });
};

const AgentTracker = ({ trackedAgent }) => {
  const map = useMap();

  useEffect(() => {
    if (!trackedAgent?.geo_coordinates) return;
    map.flyTo(
      [trackedAgent.geo_coordinates.lat, trackedAgent.geo_coordinates.lng],
      16,
      { duration: 1.2, easeLinearity: 0.25 },
    );
  }, [trackedAgent, map]);

  return null;
};

const MapController = ({ selectedIncident }) => {
  const map = useMap();

  useEffect(() => {
    if (!selectedIncident?.latitude || !selectedIncident?.longitude) return;
    map.flyTo([selectedIncident.latitude, selectedIncident.longitude], 15, {
      duration: 1.2,
      easeLinearity: 0.25,
    });
  }, [selectedIncident, map]);

  return null;
};

const IncidentMap = ({
  incidents = [],
  onAssignAgent,
  onIncidentClick,
  selectedIncident,
  trackedAgent,
}) => {
  const [center, setCenter] = useState([28.6139, 77.209]);
  const [zoom, setZoom] = useState(6);

  const incidentsWithLocation = useMemo(
    () =>
      incidents.filter((incident) => incident.latitude && incident.longitude),
    [incidents],
  );

  useEffect(() => {
    if (incidentsWithLocation.length === 0) return;

    const avgLat =
      incidentsWithLocation.reduce(
        (sum, incident) => sum + incident.latitude,
        0,
      ) / incidentsWithLocation.length;
    const avgLng =
      incidentsWithLocation.reduce(
        (sum, incident) => sum + incident.longitude,
        0,
      ) / incidentsWithLocation.length;

    setCenter([avgLat, avgLng]);
    setZoom(incidentsWithLocation.length === 1 ? 13 : 8);
  }, [incidentsWithLocation]);

  return (
    <div style={{ position: "relative", height: "100%" }}>
      <MapContainer
        center={center}
        zoom={zoom}
        zoomControl={false}
        attributionControl={false}
        style={{
          height: "100%",
          width: "100%",
          borderRadius: "16px",
          overflow: "hidden",
        }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        <ZoomControl position="bottomright" />

        <MapController selectedIncident={selectedIncident} />

        {incidentsWithLocation.map((incident) => {
          const riskScore = incident.risk_score || 0;
          const riskLevel = getRiskLevel(riskScore);
          const riskStyle = riskStyles[riskLevel];

          return (
            <Marker
              key={incident.incident_id}
              position={[incident.latitude, incident.longitude]}
              icon={createIncidentIcon(riskScore)}
              eventHandlers={{
                click: () => onIncidentClick?.(incident),
              }}
            >
              <Popup>
                <div style={{ minWidth: "220px", padding: "10px" }}>
                  <div
                    style={{
                      fontSize: "14px",
                      fontWeight: 700,
                      color: "#11253b",
                      marginBottom: "9px",
                    }}
                  >
                    {incident.incident_type || "Gas Incident"}
                  </div>

                  <div
                    style={{
                      fontSize: "12px",
                      color: "#5f738a",
                      marginBottom: "4px",
                    }}
                  >
                    <strong>ID:</strong> {incident.incident_id}
                  </div>

                  <div
                    style={{
                      fontSize: "12px",
                      color: "#5f738a",
                      marginBottom: "4px",
                    }}
                  >
                    <strong>Location:</strong> {incident.location || "N/A"}
                  </div>

                  <div
                    style={{
                      fontSize: "12px",
                      color: "#5f738a",
                      marginBottom: "8px",
                    }}
                  >
                    <strong>Status:</strong> {incident.status || "N/A"}
                  </div>

                  <div style={{ marginBottom: "11px" }}>
                    <span
                      style={{
                        display: "inline-flex",
                        padding: "3px 8px",
                        borderRadius: "999px",
                        fontSize: "11px",
                        fontWeight: 700,
                        color: riskStyle.color,
                        background: riskStyle.bg,
                        border: `1px solid ${riskStyle.color}33`,
                      }}
                    >
                      {riskLevel.toUpperCase()} RISK{" "}
                      {(riskScore * 100).toFixed(0)}%
                    </span>
                  </div>

                  <div style={{ display: "grid", gap: "6px" }}>
                    <button
                      type="button"
                      onClick={() => onIncidentClick?.(incident)}
                      style={{
                        width: "100%",
                        borderRadius: "10px",
                        border: "1px solid #cbd5e1",
                        padding: "9px 12px",
                        background: "#fff",
                        color: "#0f172a",
                        fontSize: "12px",
                        fontWeight: 700,
                        cursor: "pointer",
                      }}
                    >
                      View Details
                    </button>
                    <button
                      type="button"
                      onClick={() => onAssignAgent?.(incident.incident_id)}
                      style={{
                        width: "100%",
                        borderRadius: "10px",
                        border: "none",
                        padding: "9px 12px",
                        background: "#8DE971",
                        color: "#030304",
                        fontSize: "12px",
                        fontWeight: 700,
                        cursor: "pointer",
                      }}
                    >
                      Assign Agent
                    </button>
                  </div>
                </div>
              </Popup>
            </Marker>
          );
        })}

        <AgentTracker trackedAgent={trackedAgent} />

        {trackedAgent?.geo_coordinates && (
          <Marker
            key={`agent-${trackedAgent.agent_id}`}
            position={[
              trackedAgent.geo_coordinates.lat,
              trackedAgent.geo_coordinates.lng,
            ]}
            icon={createAgentIcon(trackedAgent.full_name || "Agent")}
          >
            <Popup>
              <div style={{ minWidth: "220px", padding: "10px" }}>
                <div
                  style={{
                    fontSize: "14px",
                    fontWeight: 700,
                    color: "#11253b",
                    marginBottom: "4px",
                  }}
                >
                  {trackedAgent.full_name}
                </div>
                <div
                  style={{
                    fontSize: "12px",
                    color: "#5f738a",
                    marginBottom: "6px",
                  }}
                >
                  {trackedAgent.specialization || "Field Engineer"}
                </div>

                {trackedAgent.phone && (
                  <div
                    style={{
                      fontSize: "12px",
                      color: "#5f738a",
                      marginBottom: "4px",
                    }}
                  >
                    <strong>Phone:</strong> {trackedAgent.phone}
                  </div>
                )}

                {trackedAgent.location && (
                  <div
                    style={{
                      fontSize: "12px",
                      color: "#5f738a",
                      marginBottom: "4px",
                    }}
                  >
                    <strong>Location:</strong> {trackedAgent.location}
                  </div>
                )}

                {trackedAgent.vehicle_type && (
                  <div
                    style={{
                      fontSize: "12px",
                      color: "#5f738a",
                      marginBottom: "8px",
                    }}
                  >
                    <strong>Vehicle:</strong> {trackedAgent.vehicle_type}
                  </div>
                )}

                <div
                  style={{
                    border: "1px solid #cde0ef",
                    background: "#eef6fd",
                    color: "#030304",
                    borderRadius: "8px",
                    textAlign: "center",
                    fontSize: "11px",
                    fontWeight: 700,
                    padding: "6px 8px",
                  }}
                >
                  Live Agent Tracking
                </div>
              </div>
            </Popup>
          </Marker>
        )}
      </MapContainer>

      <style>
        {`
          @keyframes incidentPulse {
            0%, 100% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.08); opacity: 0.86; }
          }

          @keyframes agentPulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.08); }
          }

          .leaflet-popup-content-wrapper {
            border-radius: 12px !important;
            box-shadow: 0 16px 28px -20px rgba(15,31,51,0.42) !important;
            border: 1px solid rgba(188, 206, 224, 0.8) !important;
            padding: 0 !important;
          }

          .leaflet-popup-tip {
            display: none !important;
          }

          .leaflet-popup-content {
            margin: 0 !important;
          }

          .leaflet-control-zoom {
            border: none !important;
            box-shadow: 0 14px 20px -16px rgba(15,31,51,0.46) !important;
            border-radius: 10px !important;
            overflow: hidden !important;
          }

          .leaflet-control-zoom a {
            width: 36px !important;
            height: 36px !important;
            line-height: 36px !important;
            font-size: 20px !important;
            font-weight: 700 !important;
            color: #102842 !important;
            background: rgba(255, 255, 255, 0.94) !important;
            border: 0 !important;
            border-bottom: 1px solid rgba(154, 179, 203, 0.5) !important;
            transition: all 0.2s ease !important;
          }

          .leaflet-control-zoom a:last-child {
            border-bottom: 0 !important;
          }

          .leaflet-control-zoom a:hover {
            background: #edf5fc !important;
            color: #030304 !important;
          }

          .leaflet-control-attribution {
            display: none !important;
          }

          .leaflet-container {
            border-radius: 16px;
            border: 1px solid #cfe0ee;
          }
        `}
      </style>
    </div>
  );
};

export default IncidentMap;
