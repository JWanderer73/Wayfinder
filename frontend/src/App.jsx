import { useState, useEffect, useRef } from "react";

// ── Day colors ────────────────────────────────────────────────────
const DAY_COLORS = ["#E07B39", "#7B5EA7", "#3A7BBF", "#3B9E6E", "#C0956D", "#D94F70"];

const CAT_EMOJI = {
  landmark: "🏛️", museum: "🎨", food: "🍽️",
  park: "🌿", viewpoint: "🔭", hotel: "🏨",
  attraction: "📍", restaurant: "🍽️", default: "📍",
};

// ── Leaflet loader (CDN, no npm package needed) ───────────────────
function useLeaflet(cb) {
  useEffect(() => {
    if (window.L) { cb(window.L); return; }
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
    document.head.appendChild(link);

    const script = document.createElement("script");
    script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
    script.onload = () => cb(window.L);
    document.head.appendChild(script);
  }, []);
}

// ── Transform backend response → internal trip shape ─────────────
function transformResponse(data) {
  const itinerary = data.itinerary || data;
  const days = (itinerary.days || []).map((day, di) => ({
    day_number: day.day_number,
    date: day.date || `Day ${day.day_number}`,
    title: day.title || `Day ${day.day_number}`,
    total_minutes: day.total_minutes || 0,
    stops: (day.scheduled_visits || []).map((v) => {
      const s = v.stop || v;
      return {
        id: `${day.day_number}-${s.id || s.name}-${v.arrival_time || Math.random()}`,
        name: s.name,
        lat: parseFloat(s.latitude ?? s.lat),
        lng: parseFloat(s.longitude ?? s.lng),
        category: (s.category || "default").toLowerCase(),
        arrival_time: v.arrival_time || "",
        departure_time: v.departure_time || "",
        visit_minutes: s.visit_minutes || v.visit_minutes || 0,
        address: s.address || s.formatted_address || "",
        transport_mode: v.transport_mode_from_previous || "",
        travel_minutes: v.travel_minutes_from_previous || 0,
        booking_links: s.booking_links || {},
        warnings: v.warnings || [],
      };
    }),
  }));

  console.log("TRANSFORMED DAYS:", days);

  return {
    destination: data.destination || itinerary.destination || "",
    anchor: itinerary.anchor_location
      ? {
          name: itinerary.anchor_location.name,
          lat: parseFloat(itinerary.anchor_location.latitude),
          lng: parseFloat(itinerary.anchor_location.longitude),
        }
      : null,
    hotels: (data.hotels || []).map((h, i) => ({
      id: h.location_id || i,
      name: h.name,
      rating: h.rating,
      address: h.address,
      lat: parseFloat(h.latitude ?? h.lat),
      lng: parseFloat(h.longitude ?? h.lng),
    })),
    days,
  };
}

// ── Map component ─────────────────────────────────────────────────
function MapView({ trip, activeDay, selectedStop, onSelectStop }) {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);
  const layerGroup = useRef(null);

  // ─────────────────────────────────────────────
  // INITIALIZE MAP ONCE
  // ─────────────────────────────────────────────
  useEffect(() => {
    let mounted = true;

    const init = async () => {
      // Load leaflet if needed
      if (!window.L) {
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href =
          "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
        document.head.appendChild(link);

        await new Promise((resolve) => {
          const script = document.createElement("script");
          script.src =
            "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
          script.onload = resolve;
          document.head.appendChild(script);
        });
      }

      if (!mounted) return;

      const L = window.L;

      // Prevent duplicate init
      if (mapInstance.current) return;

      mapInstance.current = L.map(mapRef.current, {
        center: [40.75, -73.98],
        zoom: 12,
        zoomControl: true,
      });

      L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
          attribution: "© OpenStreetMap contributors",
          maxZoom: 19,
        }
      ).addTo(mapInstance.current);

      layerGroup.current = L.layerGroup().addTo(
        mapInstance.current
      );
    };

    init();

    return () => {
      mounted = false;
    };
  }, []);

  // ─────────────────────────────────────────────
  // DRAW MARKERS + ROUTES
  // ─────────────────────────────────────────────
  useEffect(() => {
    if (
      !trip ||
      !window.L ||
      !mapInstance.current ||
      !layerGroup.current
    ) {
      return;
    }

    const L = window.L;

    // Clear previous layers
    layerGroup.current.clearLayers();

    const allCoords = [];

    // ─────────────────────────────────────────
    // HOTELS
    // ─────────────────────────────────────────
    trip.hotels?.forEach((hotel) => {
      if (
        Number.isNaN(hotel.lat) ||
        Number.isNaN(hotel.lng)
      ) {
        return;
      }

      allCoords.push([hotel.lat, hotel.lng]);

      const hotelIcon = L.divIcon({
        html: `
          <div style="
            background:#111;
            color:#fff;
            border-radius:999px;
            padding:5px 8px;
            font-size:11px;
            font-weight:700;
            border:2px solid #fff;
            box-shadow:0 2px 8px rgba(0,0,0,0.25);
            white-space:nowrap;
          ">
            🏨
          </div>
        `,
        className: "",
        iconSize: [34, 24],
        iconAnchor: [17, 12],
      });

      L.marker([hotel.lat, hotel.lng], {
        icon: hotelIcon,
      })
        .addTo(layerGroup.current)
        .bindPopup(`
          <div style="font-family:sans-serif">
            <div style="font-weight:700">
              🏨 ${hotel.name}
            </div>
          </div>
        `);
    });

    // ─────────────────────────────────────────
    // DAYS TO SHOW
    // ─────────────────────────────────────────
    const visibleDays =
      activeDay === 0
        ? trip.days
        : trip.days.filter(
            (d) => d.day_number === activeDay
          );

    // ─────────────────────────────────────────
    // DRAW EACH DAY
    // ─────────────────────────────────────────
    visibleDays.forEach((day) => {
      const color =
        DAY_COLORS[
          (day.day_number - 1) % DAY_COLORS.length
        ];

      const validStops = day.stops.filter(
        (s) =>
          Number.isFinite(s.lat) &&
          Number.isFinite(s.lng)
      );

      // Route line
      if (validStops.length > 1) {
        const coords = validStops.map((s) => [
          s.lat,
          s.lng,
        ]);

        L.polyline(coords, {
          color,
          weight: 4,
          opacity: 0.8,
        }).addTo(layerGroup.current);
      }

      // Markers
      validStops.forEach((stop, i) => {
        allCoords.push([stop.lat, stop.lng]);

        const isSelected =
          selectedStop?.id === stop.id;

        const icon = L.divIcon({
          html: `
            <div style="
              background:${color};
              color:#fff;
              border-radius:50%;
              width:${isSelected ? 38 : 30}px;
              height:${isSelected ? 38 : 30}px;
              display:flex;
              align-items:center;
              justify-content:center;
              font-size:${isSelected ? 14 : 12}px;
              font-weight:700;
              border:3px solid #fff;
              box-shadow:0 2px 8px rgba(0,0,0,0.3);
            ">
              ${i + 1}
            </div>
          `,
          className: "",
          iconSize: [
            isSelected ? 38 : 30,
            isSelected ? 38 : 30,
          ],
          iconAnchor: [
            isSelected ? 19 : 15,
            isSelected ? 19 : 15,
          ],
        });

        const marker = L.marker(
          [stop.lat, stop.lng],
          { icon }
        )
          .addTo(layerGroup.current)
          .bindPopup(`
            <div style="font-family:sans-serif">
              <div style="font-weight:700">
                ${stop.name}
              </div>

              <div style="font-size:12px;color:#666">
                ${stop.arrival_time || ""}
              </div>
            </div>
          `);

        marker.on("click", () => {
          onSelectStop(
            isSelected ? null : stop
          );
        });

        if (isSelected) {
          marker.openPopup();
        }
      });
    });

    // ─────────────────────────────────────────
    // FIT MAP
    // ─────────────────────────────────────────
    if (allCoords.length > 0) {
      const bounds = window.L.latLngBounds(
        allCoords
      );

      mapInstance.current.fitBounds(bounds, {
        padding: [60, 60],
        maxZoom: 13,
      });
    }
  }, [trip, activeDay, selectedStop]);

  return (
    <div
      ref={mapRef}
      style={{
        width: "100%",
        height: "100%",
        background: "#f0f0f0",
      }}
    />
  );
}

// ── Stop row ──────────────────────────────────────────────────────
function StopRow({ stop, index, color, isSelected, onSelect }) {
  const emoji = CAT_EMOJI[stop.category] || CAT_EMOJI.default;
  return (
    <div
      onClick={() => onSelect(isSelected ? null : stop)}
      style={{
        display: "flex",
        gap: 10,
        padding: "8px 0",
        cursor: "pointer",
        borderBottom: "1px solid #f3f4f6",
        background: isSelected ? "#fafafa" : "transparent",
        borderRadius: isSelected ? 6 : 0,
        paddingLeft: isSelected ? 6 : 0,
        paddingRight: isSelected ? 6 : 0,
        transition: "all 0.15s",
      }}
    >
      <div style={{
        width: 24, height: 24, borderRadius: "50%",
        background: color, color: "#fff",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 10, fontWeight: 700, flexShrink: 0, marginTop: 2,
      }}>{index + 1}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "#111", display: "flex", gap: 6, alignItems: "center" }}>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{stop.name}</span>
          <span style={{ fontSize: 12, flexShrink: 0 }}>{emoji}</span>
        </div>
        <div style={{ fontSize: 11, color: "#6b7280", marginTop: 1 }}>
          {stop.arrival_time && <span>{stop.arrival_time}{stop.departure_time ? `–${stop.departure_time}` : ""} · </span>}
          <span>{stop.visit_minutes}m</span>
          {stop.travel_minutes > 0 && <span> · {stop.transport_mode === "walk" ? "🚶" : stop.transport_mode === "transit" ? "🚇" : "🚗"} {stop.travel_minutes}m</span>}
        </div>
        {isSelected && stop.booking_links && Object.keys(stop.booking_links).length > 0 && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
            {Object.entries(stop.booking_links).slice(0, 3).map(([name, url]) => (
              <a
                key={name}
                href={url}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
                style={{
                  fontSize: 10, padding: "2px 8px",
                  borderRadius: 20, border: "1px solid #d1d5db",
                  color: "#374151", textDecoration: "none",
                  background: "#fff",
                }}
              >{name}</a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Day accordion ─────────────────────────────────────────────────
function DayCard({ day, isOpen, onToggle, selectedStop, onSelectStop }) {
  const color = DAY_COLORS[(day.day_number - 1) % DAY_COLORS.length];
  return (
    <div style={{ borderRadius: 8, border: "1px solid #e5e7eb", marginBottom: 8, overflow: "hidden" }}>
      <div
        onClick={onToggle}
        style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "10px 14px", cursor: "pointer",
          background: isOpen ? "#fafafa" : "#fff",
          borderBottom: isOpen ? "1px solid #e5e7eb" : "none",
        }}
      >
        <div style={{
          width: 32, height: 32, borderRadius: 6,
          background: color + "18", border: `1px solid ${color}44`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 13, fontWeight: 800, color,
        }}>{day.day_number}</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#111" }}>{day.title}</div>
          <div style={{ fontSize: 11, color: "#9ca3af" }}>
            {day.date && <span>{day.date} · </span>}
            {day.stops.length} stops
            {day.total_minutes > 0 && ` · ${Math.floor(day.total_minutes / 60)}h${day.total_minutes % 60 > 0 ? `${day.total_minutes % 60}m` : ""}`}
          </div>
        </div>
        <span style={{ color: "#9ca3af", fontSize: 14, transform: isOpen ? "rotate(90deg)" : "none", transition: "transform 0.2s" }}>›</span>
      </div>
      {isOpen && (
        <div style={{ padding: "8px 14px" }}>
          {day.stops.map((stop, i) => (
            <StopRow
              key={stop.id}
              stop={stop}
              index={i}
              color={color}
              isSelected={selectedStop?.id === stop.id}
              onSelect={onSelectStop}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────
export default function App() {
  const [trip, setTrip] = useState(null);
  const [activeDay, setActiveDay] = useState(0);
  const [openDays, setOpenDays] = useState([1]);
  const [selectedStop, setSelectedStop] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Form state
  const [dest, setDest] = useState("New York City");
  const [startDate, setStartDate] = useState("2026-06-10");
  const [endDate, setEndDate] = useState("2026-06-12");
  const [budget, setBudget] = useState("mid-range");
  const [vibe, setVibe] = useState("");
  const [dietary, setDietary] = useState("");
  const [required, setRequired] = useState("");

  const handlePlan = async () => {
    if (!dest.trim()) return;
    setLoading(true);
    setError("");
    setTrip(null);
    setSelectedStop(null);

    try {
      const res = await fetch("http://localhost:8000/api/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          destination: dest.trim(),
          start_date: startDate,
          end_date: endDate,
          budget,
          vibe: vibe.trim(),
          dietary_restrictions: dietary ? dietary.split(",").map(s => s.trim()).filter(Boolean) : [],
          required_attractions: required ? required.split(",").map(s => s.trim()).filter(Boolean) : [],
        }),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Server error ${res.status}: ${text.slice(0, 200)}`);
      }

      const data = await res.json();
      console.log("RAW API RESPONSE:", data);
      const transformed = transformResponse(data);
      setTrip(transformed);
      setActiveDay(0);
      setOpenDays(
        transformed.days.map(d => d.day_number)
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectStop = (stop) => {
    setSelectedStop(stop);
    if (stop) {
      const day = trip?.days.find(d => d.stops.some(s => s.id === stop.id));
      if (day) {
        setActiveDay(day.day_number);
        setOpenDays(prev => prev.includes(day.day_number) ? prev : [...prev, day.day_number]);
      }
    }
  };

  const inputStyle = {
    width: "100%",
    padding: "8px 10px",
    border: "1px solid #d1d5db",
    borderRadius: 6,
    fontSize: 13,
    color: "#111",
    background: "#fff",
    outline: "none",
    boxSizing: "border-box",
  };

  const labelStyle = {
    display: "block",
    fontSize: 11,
    fontWeight: 600,
    color: "#6b7280",
    marginBottom: 4,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  };

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      width: "100vw",
      height: "100vh",
      margin: 0,
      padding: 0,
      overflow: "hidden",
      fontFamily: "'Inter', 'Helvetica Neue', sans-serif",
      background: "#f9fafb",
    }}>

      {/* ── Header ── */}
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: 16,
        padding: "0 20px",
        height: 52,
        background: "#fff",
        borderBottom: "1px solid #e5e7eb",
        flexShrink: 0,
        boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 20 }}>🗺️</span>
          <span style={{ fontSize: 16, fontWeight: 700, color: "#111", letterSpacing: "-0.3px" }}>Wayfinder</span>
        </div>
        <div style={{ width: 1, height: 20, background: "#e5e7eb" }} />
        {trip && (
          <span style={{ fontSize: 13, color: "#6b7280" }}>
            {trip.destination} · {trip.days.length} days · {trip.days.reduce((n, d) => n + d.stops.length, 0)} stops
          </span>
        )}
      </div>

      {/* ── Body ── */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden", minHeight: 0 }}>

        {/* ── Sidebar ── */}
        <div
          style={{
            display: "flex",
            width: 680,
            flexShrink: 0,
            background: "#fff",
            borderRight: "1px solid #e5e7eb",
            overflow: "hidden",
            height: "100%",
          }}
        >

          {/* ── LEFT COLUMN: PLANNER ── */}
          <div
            style={{
              width: 320,
              borderRight: "1px solid #e5e7eb",
              overflowY: "auto",
              padding: 16,
              flexShrink: 0,
            }}
          >

            <div style={{ marginBottom: 10 }}>
              <label style={labelStyle}>Destination</label>
              <input
                style={inputStyle}
                value={dest}
                onChange={e => setDest(e.target.value)}
                placeholder="e.g. Tokyo, Paris, New York"
                onKeyDown={e => e.key === "Enter" && handlePlan()}
              />
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 8,
                marginBottom: 10,
              }}
            >
              <div>
                <label style={labelStyle}>From</label>
                <input
                  style={inputStyle}
                  type="date"
                  value={startDate}
                  onChange={e => setStartDate(e.target.value)}
                />
              </div>

              <div>
                <label style={labelStyle}>To</label>
                <input
                  style={inputStyle}
                  type="date"
                  value={endDate}
                  onChange={e => setEndDate(e.target.value)}
                />
              </div>
            </div>

            <div style={{ marginBottom: 10 }}>
              <label style={labelStyle}>Budget</label>
              <select
                style={inputStyle}
                value={budget}
                onChange={e => setBudget(e.target.value)}
              >
                <option value="budget">Budget</option>
                <option value="mid-range">Mid-range</option>
                <option value="luxury">Luxury</option>
              </select>
            </div>

            <div style={{ marginBottom: 10 }}>
              <label style={labelStyle}>Vibe</label>
              <input
                style={inputStyle}
                value={vibe}
                onChange={e => setVibe(e.target.value)}
                placeholder="e.g. food, nightlife, museums"
              />
            </div>

            <div style={{ marginBottom: 10 }}>
              <label style={labelStyle}>Dietary</label>
              <input
                style={inputStyle}
                value={dietary}
                onChange={e => setDietary(e.target.value)}
                placeholder="e.g. vegetarian, halal"
              />
            </div>

            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>Must-see</label>
              <input
                style={inputStyle}
                value={required}
                onChange={e => setRequired(e.target.value)}
                placeholder="e.g. Central Park, MoMA"
              />
            </div>

            <button
              onClick={handlePlan}
              disabled={loading}
              style={{
                width: "100%",
                padding: "10px 0",
                background: loading ? "#9ca3af" : "#111",
                color: "#fff",
                border: "none",
                borderRadius: 7,
                fontSize: 13,
                fontWeight: 600,
                cursor: loading ? "not-allowed" : "pointer",
              }}
            >
              {loading ? "Planning…" : "Plan my trip →"}
            </button>

            {error && (
              <div
                style={{
                  marginTop: 10,
                  padding: "8px 10px",
                  background: "#fef2f2",
                  border: "1px solid #fecaca",
                  borderRadius: 6,
                  fontSize: 12,
                  color: "#dc2626",
                }}
              >
                {error}
              </div>
            )}
          </div>

          {/* ── RIGHT COLUMN: ITINERARY ── */}
          <div
            style={{
              width: 360,
              overflowY: "auto",
              overflowX: "hidden",
              padding: 12,
              minWidth: 0,
            }}
          >

            {/* Day pills */}
            {trip && (
              <div
                style={{
                  display: "flex",
                  gap: 6,
                  marginBottom: 12,
                  flexWrap: "wrap",
                }}
              >
                <button
                  onClick={() => {
                    setActiveDay(0);
                    setOpenDays(trip.days.map(d => d.day_number));
                  }}
                  style={{
                    padding: "3px 10px",
                    borderRadius: 20,
                    fontSize: 11,
                    cursor: "pointer",
                    background: activeDay === 0 ? "#111" : "#fff",
                    color: activeDay === 0 ? "#fff" : "#6b7280",
                    border: "1px solid #d1d5db",
                  }}
                >
                  All
                </button>

                {trip.days.map(d => {
                  const col =
                    DAY_COLORS[(d.day_number - 1) % DAY_COLORS.length];

                  const isActive = activeDay === d.day_number;

                  return (
                    <button
                      key={d.day_number}
                      onClick={() => {
                        setActiveDay(d.day_number);
                        setOpenDays([d.day_number]);
                      }}
                      style={{
                        padding: "3px 10px",
                        borderRadius: 20,
                        fontSize: 11,
                        cursor: "pointer",
                        background: isActive ? col : "#fff",
                        color: isActive ? "#fff" : col,
                        border: `1px solid ${col}`,
                      }}
                    >
                      Day {d.day_number}
                    </button>
                  );
                })}
              </div>
            )}

            {/* Empty state */}
            {!trip && !loading && (
              <div
                style={{
                  textAlign: "center",
                  padding: "40px 20px",
                  color: "#9ca3af",
                }}
              >
                <div style={{ fontSize: 32, marginBottom: 12 }}>🗺️</div>
                <div style={{ fontSize: 13 }}>
                  Enter a destination and generate a trip
                </div>
              </div>
            )}

            {/* Loading */}
            {loading && (
              <div
                style={{
                  textAlign: "center",
                  padding: "40px 20px",
                  color: "#6b7280",
                }}
              >
                <div style={{ fontSize: 28, marginBottom: 12 }}>⏳</div>
                <div style={{ fontSize: 13 }}>
                  Building your itinerary…
                </div>
              </div>
            )}

            {/* Day cards */}
            {trip &&
              (activeDay === 0
                ? trip.days
                : trip.days.filter(d => d.day_number === activeDay)
              ).map(day => (
                <DayCard
                  key={day.day_number}
                  day={day}
                  isOpen={openDays.includes(day.day_number)}
                  onToggle={() =>
                    setOpenDays(prev =>
                      prev.includes(day.day_number)
                        ? prev.filter(d => d !== day.day_number)
                        : [...prev, day.day_number]
                    )
                  }
                  selectedStop={selectedStop}
                  onSelectStop={handleSelectStop}
                />
              ))}

            {/* Hotels */}
            {trip && trip.hotels?.length > 0 && (
              <div
                style={{
                  marginTop: 8,
                  padding: 12,
                  background: "#fafafa",
                  borderRadius: 8,
                  border: "1px solid #e5e7eb",
                }}
              >
                <div
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    color: "#6b7280",
                    marginBottom: 8,
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                  }}
                >
                  Hotels
                </div>

                {trip.hotels.slice(0, 3).map(h => (
                  <div
                    key={h.name || h.location_id}
                    style={{
                      fontSize: 12,
                      color: "#374151",
                      padding: "4px 0",
                      borderBottom: "1px solid #f3f4f6",
                    }}
                  >
                    <span style={{ fontWeight: 600 }}>
                      {h.name}
                    </span>

                    {h.rating && (
                      <span
                        style={{
                          color: "#f59e0b",
                          marginLeft: 6,
                        }}
                      >
                        ★ {h.rating}
                      </span>
                    )}

                    {h.address && (
                      <div
                        style={{
                          fontSize: 11,
                          color: "#9ca3af",
                        }}
                      >
                        {h.address}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ── Map ── */}
        <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
          <MapView
            trip={trip}
            activeDay={activeDay}
            selectedStop={selectedStop}
            onSelectStop={handleSelectStop}
          />
          {!trip && !loading && (
            <div style={{
              position: "absolute", inset: 0,
              display: "flex", alignItems: "center", justifyContent: "center",
              pointerEvents: "none",
            }}>
              <div style={{
                background: "rgba(255,255,255,0.9)",
                borderRadius: 10, padding: "16px 24px",
                fontSize: 13, color: "#6b7280",
                boxShadow: "0 2px 12px rgba(0,0,0,0.1)",
                textAlign: "center",
              }}>
                <div style={{ fontSize: 24, marginBottom: 8 }}>📍</div>
                Map will show your route here
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}