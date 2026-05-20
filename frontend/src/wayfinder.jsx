import { useState, useEffect, useRef, useCallback } from "react";

const SAMPLE_TRIP = {
  destination: "New York City",
  start_date: "2026-06-10",
  end_date: "2026-06-12",
  anchor: { name: "Hotel Beacon", lat: 40.7807, lng: -73.981 },
  days: [
    {
      day_number: 1,
      date: "Jun 10",
      title: "Downtown & Memorial",
      total_minutes: 420,
      stops: [
        { id: "liberty", name: "Statue of Liberty Ferry", category: "landmark", arrival_time: "09:00", departure_time: "11:30", visit_minutes: 150, lat: 40.7029, lng: -74.0154, transport_mode_from_previous: "walk", travel_minutes_from_previous: 18, address: "Battery Park, New York" },
        { id: "museum-911", name: "9/11 Memorial & Museum", category: "museum", arrival_time: "12:00", departure_time: "14:00", visit_minutes: 120, lat: 40.7116, lng: -74.0133, transport_mode_from_previous: "walk", travel_minutes_from_previous: 12, address: "180 Greenwich St" },
        { id: "chelsea-lunch", name: "Chelsea Market", category: "food", arrival_time: "14:30", departure_time: "15:30", visit_minutes: 60, lat: 40.7425, lng: -74.006, transport_mode_from_previous: "transit", travel_minutes_from_previous: 22, address: "75 9th Ave" },
      ],
    },
    {
      day_number: 2,
      date: "Jun 11",
      title: "Culture & Parks",
      total_minutes: 480,
      stops: [
        { id: "met", name: "The Metropolitan Museum of Art", category: "museum", arrival_time: "09:00", departure_time: "12:00", visit_minutes: 180, lat: 40.7791, lng: -73.9627, transport_mode_from_previous: "transit", travel_minutes_from_previous: 20, address: "1000 5th Ave" },
        { id: "high-line", name: "The High Line", category: "park", arrival_time: "13:00", departure_time: "14:15", visit_minutes: 75, lat: 40.7465, lng: -74.0094, transport_mode_from_previous: "transit", travel_minutes_from_previous: 35, address: "New York, NY 10011" },
        { id: "top-rock", name: "Top of the Rock", category: "viewpoint", arrival_time: "15:00", departure_time: "16:30", visit_minutes: 90, lat: 40.7594, lng: -73.98, transport_mode_from_previous: "transit", travel_minutes_from_previous: 25, address: "30 Rockefeller Plaza" },
      ],
    },
    {
      day_number: 3,
      date: "Jun 12",
      title: "Departure Morning",
      total_minutes: 240,
      stops: [
        { id: "brunch", name: "Sarabeth's Kitchen", category: "food", arrival_time: "09:00", departure_time: "10:00", visit_minutes: 60, lat: 40.7805, lng: -73.9845, transport_mode_from_previous: "walk", travel_minutes_from_previous: 3, address: "423 Amsterdam Ave" },
        { id: "central-park", name: "Central Park", category: "park", arrival_time: "10:15", departure_time: "11:45", visit_minutes: 90, lat: 40.7851, lng: -73.9683, transport_mode_from_previous: "walk", travel_minutes_from_previous: 10, address: "Central Park, New York" },
      ],
    },
  ],
};

const CATEGORY_META = {
  landmark: { icon: "🏛️", color: "#E07B39" },
  museum: { icon: "🎨", color: "#7B5EA7" },
  food: { icon: "🍽️", color: "#3B9E6E" },
  park: { icon: "🌿", color: "#4D9E4D" },
  viewpoint: { icon: "🔭", color: "#3A7BBF" },
  hotel: { icon: "🏨", color: "#C0956D" },
  default: { icon: "📍", color: "#888" },
};

const TRANSPORT_ICONS = {
  walk: "🚶",
  transit: "🚇",
  drive: "🚗",
  bike: "🚲",
};

function toRad(d) { return (d * Math.PI) / 180; }
function haversine(a, b) {
  const R = 6371000;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
}

function MapCanvas({ trip, activeDay, selectedStop, onSelectStop }) {
  const canvasRef = useRef(null);
  const [size, setSize] = useState({ w: 800, h: 500 });
  const animFrame = useRef(null);
  const pulse = useRef(0);

  const allStops = trip.days.flatMap(d => d.stops.map(s => ({ ...s, day: d.day_number })));
  const visibleStops = activeDay === 0
    ? allStops
    : trip.days.find(d => d.day_number === activeDay)?.stops.map(s => ({ ...s, day: activeDay })) ?? [];

  const allPoints = [
    ...allStops.map(s => ({ lat: s.lat, lng: s.lng })),
    { lat: trip.anchor.lat, lng: trip.anchor.lng },
  ];

  const minLat = Math.min(...allPoints.map(p => p.lat));
  const maxLat = Math.max(...allPoints.map(p => p.lat));
  const minLng = Math.min(...allPoints.map(p => p.lng));
  const maxLng = Math.max(...allPoints.map(p => p.lng));

  const project = useCallback((lat, lng, w, h) => {
    const pad = 56;
    const scaleX = (w - pad * 2) / (maxLng - minLng || 0.01);
    const scaleY = (h - pad * 2) / (maxLat - minLat || 0.01);
    const scale = Math.min(scaleX, scaleY);
    const offX = (w - (maxLng - minLng) * scale) / 2;
    const offY = (h - (maxLat - minLat) * scale) / 2;
    return {
      x: offX + (lng - minLng) * scale,
      y: h - (offY + (lat - minLat) * scale),
    };
  }, [minLat, maxLat, minLng, maxLng]);

  useEffect(() => {
    const obs = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      setSize({ w: Math.floor(width), h: Math.floor(height) });
    });
    if (canvasRef.current?.parentElement) obs.observe(canvasRef.current.parentElement);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    let t = 0;
    function draw() {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      const { w, h } = size;
      canvas.width = w;
      canvas.height = h;
      t += 0.04;
      pulse.current = t;

      ctx.clearRect(0, 0, w, h);

      ctx.fillStyle = "#0d1117";
      ctx.fillRect(0, 0, w, h);

      const gridColor = "rgba(255,255,255,0.04)";
      ctx.strokeStyle = gridColor;
      ctx.lineWidth = 1;
      for (let gx = 0; gx < w; gx += 40) {
        ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, h); ctx.stroke();
      }
      for (let gy = 0; gy < h; gy += 40) {
        ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(w, gy); ctx.stroke();
      }

      const dayColors = ["#E07B39", "#7B5EA7", "#3A7BBF", "#3B9E6E"];

      if (activeDay === 0) {
        trip.days.forEach((day, di) => {
          const col = dayColors[di % dayColors.length];
          const stops = day.stops;
          for (let i = 0; i < stops.length - 1; i++) {
            const a = project(stops[i].lat, stops[i].lng, w, h);
            const b = project(stops[i + 1].lat, stops[i + 1].lng, w, h);
            ctx.beginPath();
            ctx.setLineDash([6, 4]);
            ctx.strokeStyle = col + "55";
            ctx.lineWidth = 1.5;
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
            ctx.setLineDash([]);
          }
        });
      } else {
        const dayData = trip.days.find(d => d.day_number === activeDay);
        if (dayData) {
          const col = dayColors[(activeDay - 1) % dayColors.length];
          const stops = dayData.stops;
          const anchor = project(trip.anchor.lat, trip.anchor.lng, w, h);
          if (stops.length > 0) {
            const first = project(stops[0].lat, stops[0].lng, w, h);
            ctx.beginPath();
            ctx.setLineDash([4, 4]);
            ctx.strokeStyle = col + "44";
            ctx.lineWidth = 1.5;
            ctx.moveTo(anchor.x, anchor.y);
            ctx.lineTo(first.x, first.y);
            ctx.stroke();
            ctx.setLineDash([]);
          }
          for (let i = 0; i < stops.length - 1; i++) {
            const a = project(stops[i].lat, stops[i].lng, w, h);
            const b = project(stops[i + 1].lat, stops[i + 1].lng, w, h);
            const progress = (t * 0.5) % 1;
            ctx.beginPath();
            ctx.strokeStyle = col + "33";
            ctx.lineWidth = 2;
            ctx.setLineDash([]);
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();

            ctx.beginPath();
            ctx.strokeStyle = col;
            ctx.lineWidth = 2.5;
            ctx.setLineDash([8, 4]);
            ctx.lineDashOffset = -(t * 30);
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
            ctx.setLineDash([]);
          }
        }
      }

      const anchorPt = project(trip.anchor.lat, trip.anchor.lng, w, h);
      ctx.beginPath();
      ctx.arc(anchorPt.x, anchorPt.y, 8, 0, Math.PI * 2);
      ctx.fillStyle = "#C0956D";
      ctx.fill();
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.font = "10px monospace";
      ctx.fillStyle = "#C0956D";
      ctx.fillText("⌂ " + trip.anchor.name, anchorPt.x + 12, anchorPt.y + 4);

      visibleStops.forEach((stop, i) => {
        const pt = project(stop.lat, stop.lng, w, h);
        const meta = CATEGORY_META[stop.category] || CATEGORY_META.default;
        const isSelected = selectedStop?.id === stop.id;
        const r = isSelected ? 14 : 10;

        if (isSelected) {
          const pulseR = r + 6 + Math.sin(t * 3) * 3;
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, pulseR, 0, Math.PI * 2);
          ctx.strokeStyle = meta.color + "66";
          ctx.lineWidth = 2;
          ctx.stroke();
        }

        ctx.beginPath();
        ctx.arc(pt.x, pt.y, r, 0, Math.PI * 2);
        ctx.fillStyle = meta.color;
        ctx.fill();
        ctx.strokeStyle = isSelected ? "#fff" : "rgba(255,255,255,0.5)";
        ctx.lineWidth = isSelected ? 2.5 : 1.5;
        ctx.stroke();

        ctx.font = `${isSelected ? 13 : 11}px sans-serif`;
        ctx.fillStyle = "#fff";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        const dayData = trip.days.find(d => d.day_number === stop.day);
        const stopIdx = dayData?.stops.findIndex(s => s.id === stop.id) ?? i;
        ctx.fillText(stopIdx + 1, pt.x, pt.y);
        ctx.textAlign = "left";

        if (isSelected) {
          const label = stop.name;
          const lw = ctx.measureText(label).width;
          const bx = pt.x + 16;
          const by = pt.y - 10;
          ctx.fillStyle = "rgba(13,17,23,0.88)";
          ctx.beginPath();
          ctx.roundRect(bx - 4, by - 4, lw + 12, 20, 4);
          ctx.fill();
          ctx.strokeStyle = meta.color + "88";
          ctx.lineWidth = 1;
          ctx.stroke();
          ctx.fillStyle = "#fff";
          ctx.font = "11px sans-serif";
          ctx.fillText(label, bx + 2, by + 6);
        }
      });

      animFrame.current = requestAnimationFrame(draw);
    }
    draw();
    return () => cancelAnimationFrame(animFrame.current);
  }, [size, visibleStops, selectedStop, activeDay, project, trip]);

  const handleClick = useCallback((e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    let closest = null, closestDist = 20;
    visibleStops.forEach(stop => {
      const pt = project(stop.lat, stop.lng, size.w, size.h);
      const d = Math.hypot(pt.x - mx, pt.y - my);
      if (d < closestDist) { closestDist = d; closest = stop; }
    });
    onSelectStop(closest);
  }, [visibleStops, project, size, onSelectStop]);

  return (
    <canvas
      ref={canvasRef}
      onClick={handleClick}
      style={{ width: "100%", height: "100%", cursor: "crosshair", display: "block" }}
    />
  );
}

function StopCard({ stop, index, isSelected, onSelect }) {
  const meta = CATEGORY_META[stop.category] || CATEGORY_META.default;
  return (
    <div
      onClick={() => onSelect(isSelected ? null : stop)}
      style={{
        display: "flex",
        gap: 12,
        padding: "10px 14px",
        borderRadius: 10,
        cursor: "pointer",
        background: isSelected ? meta.color + "18" : "transparent",
        border: isSelected ? `1.5px solid ${meta.color}55` : "1.5px solid transparent",
        transition: "all 0.15s",
        marginBottom: 4,
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 0 }}>
        <div style={{
          width: 28, height: 28, borderRadius: "50%",
          background: meta.color,
          display: "flex", alignItems: "center", justifyContent: "center",
          color: "#fff", fontSize: 11, fontWeight: 700,
          flexShrink: 0,
        }}>{index + 1}</div>
        <div style={{ width: 1.5, flex: 1, background: meta.color + "44", minHeight: 8 }} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{stop.name}</span>
          <span style={{ fontSize: 10, background: meta.color + "22", color: meta.color, borderRadius: 4, padding: "1px 6px", flexShrink: 0 }}>{meta.icon} {stop.category}</span>
        </div>
        <div style={{ display: "flex", gap: 10, fontSize: 11, color: "#94a3b8" }}>
          <span>⏰ {stop.arrival_time}–{stop.departure_time}</span>
          <span>⏱ {stop.visit_minutes}m</span>
          {stop.travel_minutes_from_previous > 0 && (
            <span>{TRANSPORT_ICONS[stop.transport_mode_from_previous] || "🚶"} {stop.travel_minutes_from_previous}m travel</span>
          )}
        </div>
        {isSelected && (
          <div style={{ marginTop: 6, fontSize: 11, color: "#64748b" }}>{stop.address}</div>
        )}
      </div>
    </div>
  );
}

function DayPanel({ day, isActive, onToggle, selectedStop, onSelectStop }) {
  const total_h = Math.floor(day.total_minutes / 60);
  const total_m = day.total_minutes % 60;
  const col = ["#E07B39", "#7B5EA7", "#3A7BBF", "#3B9E6E"][day.day_number - 1] || "#888";

  return (
    <div style={{
      borderRadius: 12,
      border: `1px solid ${isActive ? col + "66" : "rgba(255,255,255,0.07)"}`,
      overflow: "hidden",
      marginBottom: 8,
      background: "rgba(255,255,255,0.02)",
    }}>
      <div
        onClick={onToggle}
        style={{
          display: "flex", alignItems: "center", gap: 12,
          padding: "12px 16px",
          cursor: "pointer",
          background: isActive ? col + "18" : "transparent",
        }}
      >
        <div style={{
          width: 36, height: 36, borderRadius: 8,
          background: col + "22", border: `1px solid ${col}44`,
          display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
          flexShrink: 0,
        }}>
          <span style={{ fontSize: 8, color: col, fontWeight: 700, letterSpacing: 1 }}>DAY</span>
          <span style={{ fontSize: 16, color: col, fontWeight: 800, lineHeight: 1 }}>{day.day_number}</span>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0" }}>{day.title}</div>
          <div style={{ fontSize: 11, color: "#64748b" }}>{day.date} · {day.stops.length} stops · {total_h}h {total_m > 0 ? `${total_m}m` : ""}</div>
        </div>
        <span style={{ color: "#64748b", fontSize: 16, transform: isActive ? "rotate(90deg)" : "rotate(0)", transition: "transform 0.2s" }}>›</span>
      </div>
      {isActive && (
        <div style={{ padding: "8px 14px 12px" }}>
          {day.stops.map((stop, i) => (
            <StopCard
              key={stop.id}
              stop={stop}
              index={i}
              isSelected={selectedStop?.id === stop.id}
              onSelect={onSelectStop}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function InputPanel({ trip, onTripChange }) {
  const [dest, setDest] = useState(trip.destination);
  const [start, setStart] = useState(trip.start_date);
  const [end, setEnd] = useState(trip.end_date);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");

  const handlePlan = async () => {
  setLoading(true);
  const res = await fetch("http://localhost:8000/api/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      destination: dest,
      start_date: start,
      end_date: end,
      budget: "mid-range",
    }),
  });
  const data = await res.json();
  // transform data.itinerary into the trip shape the map expects
  setTrip(transformItinerary(data));
  setLoading(false);
};

  return (
    <div style={{ padding: "16px 20px", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
      <div style={{ fontSize: 11, color: "#64748b", letterSpacing: 1, marginBottom: 12, textTransform: "uppercase" }}>Plan a Trip</div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input
          value={dest}
          onChange={e => setDest(e.target.value)}
          placeholder="Destination…"
          style={{
            flex: "1 1 140px", padding: "8px 10px",
            borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)",
            background: "rgba(255,255,255,0.06)", color: "#e2e8f0",
            fontSize: 13, outline: "none",
          }}
        />
        <input
          type="date"
          value={start}
          onChange={e => setStart(e.target.value)}
          style={{
            flex: "1 1 110px", padding: "8px 10px",
            borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)",
            background: "rgba(255,255,255,0.06)", color: "#94a3b8",
            fontSize: 12, outline: "none",
          }}
        />
        <input
          type="date"
          value={end}
          onChange={e => setEnd(e.target.value)}
          style={{
            flex: "1 1 110px", padding: "8px 10px",
            borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)",
            background: "rgba(255,255,255,0.06)", color: "#94a3b8",
            fontSize: 12, outline: "none",
          }}
        />
        <button
          onClick={handlePlan}
          disabled={loading}
          style={{
            padding: "8px 16px", borderRadius: 8,
            background: loading ? "rgba(94,234,212,0.1)" : "rgba(94,234,212,0.15)",
            border: "1px solid rgba(94,234,212,0.3)",
            color: "#5eead4", fontSize: 13, cursor: "pointer",
            fontWeight: 600,
          }}
        >
          {loading ? "…" : "Plan →"}
        </button>
      </div>
      {status && <div style={{ marginTop: 8, fontSize: 11, color: "#5eead4" }}>{status}</div>}
    </div>
  );
}

function LegendBar({ activeDay, setActiveDay, totalDays }) {
  const dayColors = ["#E07B39", "#7B5EA7", "#3A7BBF", "#3B9E6E"];
  return (
    <div style={{ display: "flex", gap: 6, padding: "8px 12px", borderBottom: "1px solid rgba(255,255,255,0.06)", flexWrap: "wrap" }}>
      <button
        onClick={() => setActiveDay(0)}
        style={{
          padding: "4px 12px", borderRadius: 20, fontSize: 11, cursor: "pointer",
          background: activeDay === 0 ? "rgba(94,234,212,0.15)" : "transparent",
          border: activeDay === 0 ? "1px solid rgba(94,234,212,0.4)" : "1px solid rgba(255,255,255,0.1)",
          color: activeDay === 0 ? "#5eead4" : "#64748b",
        }}
      >All Days</button>
      {Array.from({ length: totalDays }, (_, i) => i + 1).map(d => (
        <button
          key={d}
          onClick={() => setActiveDay(d)}
          style={{
            padding: "4px 12px", borderRadius: 20, fontSize: 11, cursor: "pointer",
            background: activeDay === d ? dayColors[(d - 1) % dayColors.length] + "22" : "transparent",
            border: activeDay === d ? `1px solid ${dayColors[(d - 1) % dayColors.length]}55` : "1px solid rgba(255,255,255,0.07)",
            color: activeDay === d ? dayColors[(d - 1) % dayColors.length] : "#64748b",
          }}
        >Day {d}</button>
      ))}
      <div style={{ flex: 1 }} />
      {Object.entries(CATEGORY_META).filter(([k]) => k !== "default").map(([cat, m]) => (
        <span key={cat} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "#64748b" }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: m.color, display: "inline-block" }} />
          {cat}
        </span>
      ))}
    </div>
  );
}

export default function WayfinderApp() {
  const [trip] = useState(SAMPLE_TRIP);
  const [activeDay, setActiveDay] = useState(0);
  const [openDays, setOpenDays] = useState([1]);
  const [selectedStop, setSelectedStop] = useState(null);
  const [sidebarTab, setSidebarTab] = useState("itinerary");

  const toggleDay = (dayNum) => {
    setOpenDays(prev =>
      prev.includes(dayNum) ? prev.filter(d => d !== dayNum) : [...prev, dayNum]
    );
    setActiveDay(dayNum);
  };

  const handleSelectStop = (stop) => {
    setSelectedStop(stop);
    if (stop) {
      const day = trip.days.find(d => d.stops.some(s => s.id === stop.id));
      if (day) {
        setActiveDay(day.day_number);
        setOpenDays(prev => prev.includes(day.day_number) ? prev : [...prev, day.day_number]);
      }
    }
  };

  const allStops = trip.days.flatMap(d => d.stops);

  return (
    <div style={{
      display: "flex", flexDirection: "column", height: "100vh", minHeight: 600,
      background: "#0a0d13", color: "#e2e8f0",
      fontFamily: "'DM Mono', 'SF Mono', monospace",
    }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 12,
        padding: "0 20px", height: 52,
        borderBottom: "1px solid rgba(255,255,255,0.07)",
        background: "rgba(255,255,255,0.02)",
        flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 18 }}>🗺️</span>
          <span style={{ fontSize: 16, fontWeight: 700, color: "#5eead4", letterSpacing: -0.5 }}>Wayfinder</span>
        </div>
        <div style={{ width: 1, height: 20, background: "rgba(255,255,255,0.1)" }} />
        <span style={{ fontSize: 12, color: "#94a3b8" }}>{trip.destination}</span>
        <span style={{ fontSize: 11, color: "#475569", background: "rgba(255,255,255,0.05)", padding: "2px 8px", borderRadius: 4 }}>
          {trip.start_date} → {trip.end_date}
        </span>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 11, color: "#64748b" }}>
          {allStops.length} stops · {trip.days.length} days
        </span>
      </div>

      <div style={{ display: "flex", flex: 1, overflow: "hidden", minHeight: 0 }}>
        <div style={{
          width: 340, flexShrink: 0,
          borderRight: "1px solid rgba(255,255,255,0.06)",
          display: "flex", flexDirection: "column",
          background: "#0d1117",
          overflow: "hidden",
        }}>
          <InputPanel trip={trip} onTripChange={() => {}} />

          <div style={{ display: "flex", borderBottom: "1px solid rgba(255,255,255,0.06)", flexShrink: 0 }}>
            {["itinerary", "stops"].map(tab => (
              <button
                key={tab}
                onClick={() => setSidebarTab(tab)}
                style={{
                  flex: 1, padding: "10px 0", fontSize: 12, cursor: "pointer",
                  background: "transparent", border: "none",
                  color: sidebarTab === tab ? "#5eead4" : "#475569",
                  borderBottom: sidebarTab === tab ? "2px solid #5eead4" : "2px solid transparent",
                  textTransform: "capitalize", fontWeight: sidebarTab === tab ? 600 : 400,
                }}
              >{tab}</button>
            ))}
          </div>

          <div style={{ flex: 1, overflowY: "auto", padding: "12px" }}>
            {sidebarTab === "itinerary" && trip.days.map(day => (
              <DayPanel
                key={day.day_number}
                day={day}
                isActive={openDays.includes(day.day_number)}
                onToggle={() => toggleDay(day.day_number)}
                selectedStop={selectedStop}
                onSelectStop={handleSelectStop}
              />
            ))}
            {sidebarTab === "stops" && (
              <div>
                {allStops.map((stop, i) => {
                  const dayNum = trip.days.find(d => d.stops.some(s => s.id === stop.id))?.day_number;
                  const dayIdx = trip.days.findIndex(d => d.day_number === dayNum);
                  const stopIdx = trip.days[dayIdx]?.stops.findIndex(s => s.id === stop.id) ?? i;
                  return (
                    <StopCard
                      key={stop.id}
                      stop={{ ...stop, day: dayNum }}
                      index={stopIdx}
                      isSelected={selectedStop?.id === stop.id}
                      onSelect={handleSelectStop}
                    />
                  );
                })}
                <div style={{
                  marginTop: 12, padding: "10px 14px", borderRadius: 10,
                  border: "1px solid rgba(192,149,109,0.2)",
                  background: "rgba(192,149,109,0.06)",
                }}>
                  <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                    <span style={{ fontSize: 18 }}>🏨</span>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "#C0956D" }}>{trip.anchor.name}</div>
                      <div style={{ fontSize: 11, color: "#64748b" }}>Hotel anchor · all days</div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <LegendBar activeDay={activeDay} setActiveDay={setActiveDay} totalDays={trip.days.length} />
          <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
            <MapCanvas
              trip={trip}
              activeDay={activeDay}
              selectedStop={selectedStop}
              onSelectStop={handleSelectStop}
            />
            {selectedStop && (
              <div style={{
                position: "absolute", bottom: 16, left: "50%", transform: "translateX(-50%)",
                background: "rgba(13,17,23,0.92)",
                border: `1px solid ${(CATEGORY_META[selectedStop.category] || CATEGORY_META.default).color}55`,
                borderRadius: 12, padding: "10px 16px",
                display: "flex", alignItems: "center", gap: 12,
                backdropFilter: "blur(4px)",
                minWidth: 260, maxWidth: 420,
              }}>
                <div style={{
                  width: 36, height: 36, borderRadius: 8,
                  background: (CATEGORY_META[selectedStop.category] || CATEGORY_META.default).color + "22",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 18,
                }}>
                  {(CATEGORY_META[selectedStop.category] || CATEGORY_META.default).icon}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0" }}>{selectedStop.name}</div>
                  <div style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>
                    {selectedStop.arrival_time}–{selectedStop.departure_time} · {selectedStop.visit_minutes}m
                  </div>
                </div>
                <button
                  onClick={() => setSelectedStop(null)}
                  style={{ background: "none", border: "none", color: "#475569", cursor: "pointer", fontSize: 18, padding: 0 }}
                >×</button>
              </div>
            )}
            <div style={{
              position: "absolute", top: 12, right: 12,
              background: "rgba(13,17,23,0.7)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 8, padding: "6px 10px",
              fontSize: 10, color: "#475569",
              lineHeight: 1.6,
            }}>
              Click stops to select<br/>
              Animated route = active day
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
