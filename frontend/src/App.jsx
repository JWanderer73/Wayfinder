import { useState, useEffect, useRef } from "react";

// ─── Constants ────────────────────────────────────────────────────────────────

const DAY_COLORS = ["#2563EB", "#D97706", "#059669", "#DC2626", "#7C3AED", "#0891B2"];

const CAT_EMOJI = {
  landmark: "🏛", museum: "🎨", food: "🍽", restaurant: "🍽",
  park: "🌿", viewpoint: "🔭", hotel: "🏨", attraction: "⭐",
  religious: "⛪", shopping: "🛍", nightlife: "🌙", beach: "🏖",
  hike: "🥾", tour: "🎫", relaxation: "🧘", entertainment: "🎭",
  default: "📍",
};

const TRANSPORT_LABEL = {
  walk:    { icon: "🚶", label: "Walk" },
  transit: { icon: "🚇", label: "Public Transit" },
  drive:   { icon: "🚗", label: "Drive" },
  bike:    { icon: "🚲", label: "Bike" },
};

const SOURCE_LABELS = {
  user_required:     { text: "You asked for this", color: "#059669", bg: "#ecfdf5" },
  ranked:            { text: "AI pick",            color: "#2563EB", bg: "#eff6ff" },
  completeness:      { text: "AI suggests",        color: "#7C3AED", bg: "#f5f3ff" },
  swap:              { text: "You swapped in",      color: "#D97706", bg: "#fffbeb" },
  restaurant_inject: { text: "Near your route",    color: "#059669", bg: "#ecfdf5" },
};

function fmtMinutes(m) {
  if (!m) return null;
  const h = Math.floor(m / 60), mins = m % 60;
  if (h === 0) return `${mins}m`;
  return mins === 0 ? `${h}h` : `${h}h ${mins}m`;
}

function fmtMeters(m) {
  if (!m || !isFinite(m) || m === 0) return null;
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`;
}

// ─── Leaflet loader ───────────────────────────────────────────────────────────

function useLeafletMap(containerRef, onReady) {
  const mapRef   = useRef(null);
  const readyRef = useRef(false);

  useEffect(() => {
    function init(L) {
      if (readyRef.current || !containerRef.current) return;
      readyRef.current = true;
      const map = L.map(containerRef.current, { center: [20, 0], zoom: 2, zoomControl: true });
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap contributors", maxZoom: 19,
      }).addTo(map);
      mapRef.current = map;
      onReady(map, L);
    }
    if (window.L) { init(window.L); return; }
    if (!document.getElementById("leaflet-css")) {
      const link = document.createElement("link");
      link.id = "leaflet-css"; link.rel = "stylesheet";
      link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      document.head.appendChild(link);
    }
    if (!document.getElementById("leaflet-js")) {
      const script = document.createElement("script");
      script.id = "leaflet-js";
      script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
      script.onload = () => init(window.L);
      document.head.appendChild(script);
    } else {
      const t = setInterval(() => { if (window.L) { clearInterval(t); init(window.L); } }, 80);
    }
    return () => {
      if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; readyRef.current = false; }
    };
  }, []);

  return mapRef;
}

// ─── Transform backend → internal shape ──────────────────────────────────────
// The new pipeline returns:
//   data.itinerary.days[].scheduled_visits[].stop  (from spatial planner)
//   data.attractions[]                              (flat ranked list)
//   data.restaurants[]                              (separate list)
//   data.hotels[]
//   data.gaps_structured[]
//   data.weather_summary

function transform(data) {
  const itin = data.itinerary || {};

  const days = (itin.days || []).map((day) => ({
    day_number:          day.day_number,
    title:               day.title || `Day ${day.day_number}`,
    total_minutes:       day.total_minutes || 0,
    total_visit_minutes: day.total_visit_minutes || 0,
    total_travel_minutes:day.total_travel_minutes || 0,
    lunch_minutes:       day.lunch_minutes || 0,
    dinner_minutes:      day.dinner_minutes || 0,
    redundancy_minutes:  day.redundancy_minutes || 0,
    warnings:            day.warnings || [],
    // restaurants injected by bridge after clustering
    restaurants: (day.restaurants || []).map(r => ({
      id:       r.location_id || r.name,
      name:     r.name,
      lat:      parseFloat(r.latitude  ?? 0),
      lng:      parseFloat(r.longitude ?? 0),
      address:  r.address || "",
      rating:   r.rating,
      score:    r.score,
      booking_links: r.booking_links || {},
    })),
    stops: (day.scheduled_visits || []).map((v) => {
      const s = v.stop || v;
      // enrich stop with full attraction data if available
      const enriched = (data.attractions || []).find(a =>
        a.location_id === s.id || a.location_id === s.place_id || a.name === s.name
      ) || {};
      return {
        id:           s.id || s.name,
        name:         s.name,
        lat:          parseFloat(s.latitude  ?? s.lat  ?? 0),
        lng:          parseFloat(s.longitude ?? s.lng  ?? 0),
        category:     (s.category || "default").toLowerCase(),
        visit_minutes:s.visit_minutes || 0,
        visit_source: s.visit_minutes_source || "",
        address:      s.formatted_address || s.address || "",
        notes:        s.notes || "",
        required:     s.required || false,
        anchor_kind:  s.anchor_kind || "",
        // from enriched full attraction data
        is_mandatory:      enriched.is_mandatory     || s.required || false,
        selection_source:  enriched.selection_source || "ranked",
        confidence:        enriched.confidence       ?? 0.7,
        score:             enriched.score            ?? null,
        score_reason:      enriched.score_reason     || "",
        photo_url:         enriched.photo_url        || "",
        rating:            enriched.rating           ?? null,
        num_reviews:       enriched.num_reviews      ?? null,
        open_hours_text:   enriched.open_hours_text  || [],
        is_outdoor:        enriched.is_outdoor       || false,
        is_indoor:         enriched.is_indoor        || false,
        booking_links:     enriched.booking_links    || s.booking_links || {},
        // timing
        arrival_time:   v.arrival_time   || "",
        start_time:     v.start_time     || "",
        departure_time: v.departure_time || "",
        wait_minutes:   v.wait_minutes   || 0,
        // travel from previous
        travel_minutes: v.travel_minutes_from_previous || 0,
        travel_buffer:  v.travel_buffer_minutes        || 0,
        transport:      v.transport_mode_from_previous || "",
        distance_m:     v.distance_meters_from_previous || 0,
        warnings:       v.warnings || [],
      };
    }),
  }));

  return {
    destination:     data.destination || "",
    trip_id:         data.trip_id     || "",
    weather_summary: data.weather_summary || "",
    planning_notes:  itin.planning_notes  || [],
    removed_stops:   itin.removed_stops   || [],
    gaps_structured: data.gaps_structured || [],
    gaps:            data.gaps || "",
    anchor: itin.anchor_location ? {
      name: itin.anchor_location.name,
      lat:  parseFloat(itin.anchor_location.latitude),
      lng:  parseFloat(itin.anchor_location.longitude),
    } : null,
    hotels: (data.hotels || []).map(h => ({
      id:       h.location_id || h.name,
      name:     h.name,
      rating:   h.rating,
      price_level: h.price_level || "",
      num_reviews: h.num_reviews,
      address:  h.address || "",
      lat:      parseFloat(h.latitude  ?? 0),
      lng:      parseFloat(h.longitude ?? 0),
      photo_url: h.photo_url || "",
      booking_links: h.booking_links || {},
    })),
    days,
  };
}

// ─── Map panel ────────────────────────────────────────────────────────────────

function MapPanel({
    trip,
    activeDay,
    selectedStop,
    selectedHotel,
    onSelectHotel,
    onSelectStop,
  }) {
  const containerRef = useRef(null);
  const layersRef    = useRef(null);
  const mapRdy       = useRef(null);
  const Lref         = useRef(null);

  function makeIcon(L, label, color, size, selected) {
    return L.divIcon({
      html: `<div style="
        width:${size}px;height:${size}px;border-radius:50%;
        background:${color};color:#fff;
        display:flex;align-items:center;justify-content:center;
        font-size:${size < 30 ? 10 : 12}px;font-weight:700;
        border:${selected ? 3 : 2}px solid #fff;
        box-shadow:${selected ? `0 0 0 3px ${color}55,` : ""}0 2px 8px rgba(0,0,0,.22);
      ">${label}</div>`,
      className: "", iconSize: [size, size], iconAnchor: [size / 2, size / 2],
    });
  }

  function render(map, L, tripData, day, sel) {
    layersRef.current.clearLayers();
    if (!tripData) return;
    const bounds = [];

    // Hotel markers
    (tripData.hotels || []).forEach(h => {
      if (!h.lat || !h.lng) return;

      const isSelected =
        selectedHotel?.name === h.name;

      const marker = L.marker([h.lat, h.lng], {
        icon: L.divIcon({
          html: `
            <div style="
              background:${isSelected ? "#2563EB" : "#92400E"};
              color:#fff;
              width:${isSelected ? 38 : 30}px;
              height:${isSelected ? 38 : 30}px;
              border-radius:8px;
              display:flex;
              align-items:center;
              justify-content:center;
              font-size:16px;
              border:2px solid #fff;
              box-shadow:0 2px 8px rgba(0,0,0,.25);
            ">
              🏨
            </div>
          `,
          className: "",
          iconSize: isSelected ? [38, 38] : [30, 30],
          iconAnchor: isSelected ? [19, 19] : [15, 15],
        }),
      });

      marker
        .addTo(layersRef.current)
        .bindTooltip(`<b>${h.name}</b>`, {
          direction: "top",
          offset: [0, -18]
        });

      marker.on("click", () => {
        onSelectHotel({
          name: h.name,
          lat: h.lat,
          lng: h.lng,
        });
      });

      bounds.push([h.lat, h.lng]);
    });

    const daysToShow = day === 0 ? tripData.days : tripData.days.filter(d => d.day_number === day);

    daysToShow.forEach((d) => {
      const color = DAY_COLORS[(d.day_number - 1) % DAY_COLORS.length];
      const pts = d.stops.filter(s => s.lat && s.lng).map(s => [s.lat, s.lng]);

      if (pts.length > 1) {
        L.polyline(pts, { color, weight: 3.5, opacity: 0.7, dashArray: day === 0 ? "7 4" : null })
          .addTo(layersRef.current);
      }

      d.stops.forEach((stop, i) => {
        if (!stop.lat || !stop.lng) return;
        bounds.push([stop.lat, stop.lng]);
        const isSel = stop.id === sel?.id;
        const t = TRANSPORT_LABEL[stop.transport] || {};
        const dist = fmtMeters(stop.distance_m);

        const marker = L.marker([stop.lat, stop.lng], {
          icon: makeIcon(L, stop.is_mandatory ? "📌" : i + 1, color, isSel ? 38 : 30, isSel),
          zIndexOffset: isSel ? 1000 : 0,
        }).addTo(layersRef.current);

        const src = SOURCE_LABELS[stop.selection_source] || {};
        const srcBadge = src.text
          ? `<span style="font-size:9px;padding:1px 5px;border-radius:99px;background:${src.bg};color:${src.color};font-weight:600">${src.text}</span>`
          : "";

        const hoursHtml = stop.open_hours_text?.length
          ? `<div style="font-size:10px;color:#6b7280;margin-top:4px">${stop.open_hours_text[0]}</div>`
          : "";

        const bookingHtml = Object.keys(stop.booking_links).length
          ? `<div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:3px">
               ${Object.entries(stop.booking_links).slice(0,3).map(([n,u]) =>
                 `<a href="${u}" target="_blank" style="font-size:10px;padding:1px 6px;border:1px solid #d1d5db;border-radius:99px;text-decoration:none;color:#374151">${n}</a>`
               ).join("")}
             </div>`
          : "";

        marker.bindPopup(`
          <div style="font-family:system-ui;min-width:200px;padding:2px">
            ${stop.travel_minutes ? `<div style="font-size:10px;color:#9ca3af;margin-bottom:5px">${t.icon || "🚶"} ${stop.travel_minutes}m travel${dist ? ` · ${dist}` : ""}</div>` : ""}
            <div style="font-weight:700;font-size:13px;margin-bottom:3px">${CAT_EMOJI[stop.category] || "📍"} ${stop.name}</div>
            <div style="margin-bottom:4px">${srcBadge}</div>
            <div style="font-size:11px;color:#6b7280">
              ${stop.arrival_time ? `${stop.arrival_time}${stop.departure_time ? ` – ${stop.departure_time}` : ""}` : ""}
              ${stop.visit_minutes ? ` · ${fmtMinutes(stop.visit_minutes)}` : ""}
            </div>
            ${stop.score !== null ? `<div style="font-size:10px;color:#6b7280;margin-top:2px">Score: ${stop.score}/10 · ${stop.score_reason}</div>` : ""}
            ${stop.rating ? `<div style="font-size:10px;color:#f59e0b">★ ${stop.rating}${stop.num_reviews ? ` (${stop.num_reviews.toLocaleString()})` : ""}</div>` : ""}
            ${stop.address ? `<div style="font-size:10px;color:#9ca3af;margin-top:3px">${stop.address}</div>` : ""}
            ${hoursHtml}${bookingHtml}
          </div>
        `, { maxWidth: 280 });

        marker.on("click", () => onSelectStop(isSel ? null : stop));
        if (isSel) marker.openPopup();
      });

      // Restaurant markers for this day
      d.restaurants?.forEach(r => {
        if (!r.lat || !r.lng) return;
        const rIcon = L.divIcon({
          html: `<div style="background:#059669;color:#fff;width:24px;height:24px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:12px;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.2);">🍽</div>`,
          className: "", iconSize: [24, 24], iconAnchor: [12, 12],
        });
        L.marker([r.lat, r.lng], { icon: rIcon }).addTo(layersRef.current)
          .bindTooltip(`<b>${r.name}</b><br/>Restaurant`, { direction: "top", offset: [0, -14] });
        bounds.push([r.lat, r.lng]);
      });
    });

    if (bounds.length > 0) map.fitBounds(bounds, { padding: [52, 52], maxZoom: 15 });
  }

  useLeafletMap(containerRef, (map, L) => {
    mapRdy.current = map; Lref.current = L;
    layersRef.current = L.layerGroup().addTo(map);
    if (trip) render(map, L, trip, activeDay, selectedStop);
  });

  useEffect(() => {
    if (mapRdy.current && Lref.current)
      render(mapRdy.current, Lref.current, trip, activeDay, selectedStop);
  }, [trip, activeDay, selectedStop, selectedHotel]);

  useEffect(() => {
    if (
      mapRdy.current &&
      selectedHotel?.lat &&
      selectedHotel?.lng
    ) {
      mapRdy.current.flyTo(
        [selectedHotel.lat, selectedHotel.lng],
        14,
        { duration: 0.8 }
      );
    }
  }, [selectedHotel]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
      {!trip && (
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
          <div style={{ background: "rgba(255,255,255,0.92)", borderRadius: 12, padding: "18px 28px", textAlign: "center", boxShadow: "0 4px 20px rgba(0,0,0,.1)", fontSize: 13, color: "#6b7280" }}>
            <div style={{ fontSize: 28, marginBottom: 8 }}>🗺️</div>Your route will appear here
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Day time breakdown bar ───────────────────────────────────────────────────

function DayStats({ day }) {
  const items = [
    day.total_visit_minutes    && { label: "Visits",  val: fmtMinutes(day.total_visit_minutes),    color: "#2563EB" },
    day.total_travel_minutes   && { label: "Travel",  val: fmtMinutes(day.total_travel_minutes),   color: "#D97706" },
    day.lunch_minutes          && { label: "Lunch",   val: fmtMinutes(day.lunch_minutes),          color: "#059669" },
    day.dinner_minutes         && { label: "Dinner",  val: fmtMinutes(day.dinner_minutes),         color: "#7C3AED" },
    day.redundancy_minutes     && { label: "Slack",   val: fmtMinutes(day.redundancy_minutes),     color: "#9ca3af" },
  ].filter(Boolean);
  if (!items.length) return null;
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", padding: "5px 10px 8px", borderBottom: "1px solid #f3f4f6" }}>
      {items.map(({ label, val, color }) => (
        <div key={label} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "#6b7280" }}>
          <div style={{ width: 6, height: 6, borderRadius: "50%", background: color }} />
          <span style={{ fontWeight: 600, color }}>{val}</span>
          <span>{label}</span>
        </div>
      ))}
    </div>
  );
}

// ─── Stop card ────────────────────────────────────────────────────────────────

function StopCard({ stop, index, color, selected, onSelect }) {
  const t   = TRANSPORT_LABEL[stop.transport] || {};
  const src = SOURCE_LABELS[stop.selection_source] || {};
  const dist = fmtMeters(stop.distance_m);

  return (
    <div
      onClick={() => onSelect(selected ? null : stop)}
      style={{
        borderRadius: 8,
        border: `1px solid ${selected ? color + "44" : "#f3f4f6"}`,
        background: selected ? color + "08" : "#fff",
        padding: "9px 10px", marginBottom: 4, cursor: "pointer",
        transition: "all .15s",
      }}
    >
      {/* Travel from previous */}
      {stop.travel_minutes > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 6, fontSize: 10, color: "#9ca3af" }}>
          <div style={{ width: 1.5, height: 10, background: "#e5e7eb", marginLeft: 10 }} />
          <span>{t.icon || "🚶"} {fmtMinutes(stop.travel_minutes)}</span>
          {dist && <span>· {dist}</span>}
          {stop.travel_buffer > 0 && <span style={{ color: "#d1d5db" }}>+{stop.travel_buffer}m buffer</span>}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
        {/* Number bubble */}
        <div style={{
          width: 22, height: 22, borderRadius: "50%", background: color, color: "#fff",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 10, fontWeight: 700, flexShrink: 0, marginTop: 2,
        }}>{stop.is_mandatory ? "📌" : index + 1}</div>

        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Name row */}
          <div style={{ display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap", marginBottom: 2 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: "#111", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {stop.name}
            </span>
            <span style={{ fontSize: 11 }}>{CAT_EMOJI[stop.category] || "📍"}</span>
            {src.text && (
              <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 99, background: src.bg, color: src.color, fontWeight: 600, flexShrink: 0 }}>
                {src.text}
              </span>
            )}
            {stop.visit_source === "heuristic" && (
              <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 99, background: "#f3f4f6", color: "#9ca3af" }}>est.</span>
            )}
          </div>

          {/* Time + stats row */}
          <div style={{ display: "flex", gap: 8, fontSize: 11, color: "#6b7280", flexWrap: "wrap" }}>
            {stop.arrival_time && <span>{stop.arrival_time}{stop.departure_time ? `–${stop.departure_time}` : ""}</span>}
            {stop.visit_minutes > 0 && <span>⏱ {fmtMinutes(stop.visit_minutes)}</span>}
            {stop.wait_minutes > 0 && <span style={{ color: "#D97706" }}>⏸ {stop.wait_minutes}m wait</span>}
            {stop.rating && <span>★ {stop.rating}</span>}
            {stop.score !== null && stop.score !== undefined && (
              <span style={{ color: stop.score >= 8 ? "#059669" : stop.score >= 6 ? "#D97706" : "#9ca3af" }}>
                {stop.score}/10
              </span>
            )}
            {stop.is_outdoor && <span title="Outdoor">🌤</span>}
            {stop.is_indoor  && <span title="Indoor">🏠</span>}
          </div>

          {/* Expanded content */}
          {selected && (
            <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
              {stop.score_reason && (
                <div style={{ fontSize: 11, color: "#6b7280", fontStyle: "italic" }}>"{stop.score_reason}"</div>
              )}
              {stop.address && <div style={{ fontSize: 11, color: "#9ca3af" }}>📍 {stop.address}</div>}
              {stop.notes && !stop.notes.startsWith("📌") && (
                <div style={{ fontSize: 11, color: "#6b7280" }}>{stop.notes.split(" | ").slice(1,2).join("")}</div>
              )}
              {stop.open_hours_text?.length > 0 && (
                <div style={{ fontSize: 10, color: "#6b7280" }}>🕐 {stop.open_hours_text[0]}</div>
              )}
              {stop.warnings?.map((w, i) => (
                <div key={i} style={{ fontSize: 10, color: "#b45309", background: "#fffbeb", padding: "3px 7px", borderRadius: 5 }}>⚠️ {w}</div>
              ))}
              {Object.keys(stop.booking_links).length > 0 && (
                <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: 4 }}>
                  {Object.entries(stop.booking_links).slice(0, 4).map(([name, url]) => (
                    <a key={name} href={url} target="_blank" rel="noreferrer"
                      onClick={e => e.stopPropagation()}
                      style={{ fontSize: 10, padding: "2px 8px", borderRadius: 99, border: "1px solid #d1d5db", color: "#374151", textDecoration: "none", background: "#fff" }}>
                      {name}
                    </a>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Day accordion ────────────────────────────────────────────────────────────

function DayAccordion({ day, open, onToggle, selectedStop, onSelectStop }) {
  const color = DAY_COLORS[(day.day_number - 1) % DAY_COLORS.length];
  return (
    <div style={{ borderRadius: 8, border: "1px solid #e5e7eb", marginBottom: 6, overflow: "hidden" }}>
      <div onClick={onToggle} style={{
        display: "flex", alignItems: "center", gap: 10, padding: "10px 12px",
        cursor: "pointer", background: open ? "#fafafa" : "#fff",
        borderBottom: open ? "1px solid #f3f4f6" : "none", userSelect: "none",
      }}>
        <div style={{
          width: 30, height: 30, borderRadius: 6, flexShrink: 0,
          background: color + "18", border: `1.5px solid ${color}44`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 13, fontWeight: 800, color,
        }}>{day.day_number}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#111", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{day.title}</div>
          <div style={{ fontSize: 11, color: "#9ca3af" }}>
            {day.stops.length} stop{day.stops.length !== 1 ? "s" : ""}
            {day.total_minutes > 0 ? ` · ${fmtMinutes(day.total_minutes)} total` : ""}
            {day.restaurants?.length > 0 ? ` · ${day.restaurants.length} 🍽` : ""}
          </div>
        </div>
        {day.warnings?.length > 0 && <span title={day.warnings.join(" · ")}>⚠️</span>}
        <span style={{ color: "#9ca3af", fontSize: 13, transform: open ? "rotate(90deg)" : "none", transition: "transform .2s", flexShrink: 0 }}>›</span>
      </div>

      {open && (
        <>
          <DayStats day={day} />
          <div style={{ padding: "6px 8px 8px" }}>
            {day.stops.map((stop, i) => (
              <StopCard key={stop.id} stop={stop} index={i} color={color}
                selected={selectedStop?.id === stop.id} onSelect={onSelectStop} />
            ))}
            {day.restaurants?.length > 0 && (
              <div style={{ marginTop: 8, padding: "7px 10px", borderRadius: 7, background: "#f0fdf4", border: "1px solid #bbf7d0" }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: "#059669", marginBottom: 5, textTransform: "uppercase", letterSpacing: ".05em" }}>Nearby restaurants</div>
                {day.restaurants.map(r => (
                  <div key={r.id} style={{ fontSize: 12, color: "#374151", padding: "3px 0", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>🍽</span>
                    <span style={{ fontWeight: 500 }}>{r.name}</span>
                    {r.rating && <span style={{ color: "#f59e0b", fontSize: 11 }}>★ {r.rating}</span>}
                    {Object.keys(r.booking_links || {}).length > 0 && (
                      <a href={Object.values(r.booking_links)[0]} target="_blank" rel="noreferrer"
                        style={{ fontSize: 10, color: "#059669", textDecoration: "none" }}>Book</a>
                    )}
                  </div>
                ))}
              </div>
            )}
            {day.warnings?.map((w, i) => (
              <div key={i} style={{ fontSize: 11, color: "#b45309", padding: "5px 10px", background: "#fffbeb", borderRadius: 6, marginTop: 4 }}>⚠️ {w}</div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [trip, setTrip]                 = useState(null);
  const [activeDay, setActiveDay]       = useState(0);
  const [openDays, setOpenDays]         = useState([]);
  const [selectedStop, setSelectedStop] = useState(null);
  const [selectedHotel, setSelectedHotel] = useState(null);
  const [loading, setLoading]           = useState(false);
  const [error, setError]               = useState("");
  const [tab, setTab]                   = useState("itinerary");

  // form
  const [dest, setDest]       = useState("");
  const [start, setStart]     = useState("2026-06-10");
  const [end, setEnd]         = useState("2026-06-12");
  const [budget, setBudget]   = useState("mid-range");
  const [vibe, setVibe]       = useState("");
  const [dietary, setDietary] = useState("");
  const [must, setMust]       = useState("");
  const [shape, setShape]     = useState("balanced");
  const [mode, setMode]       = useState("TRANSIT");

  const handlePlan = async () => {
    if (!dest.trim()) return;
    setLoading(true); setError(""); setTrip(null); setSelectedStop(null); setTab("itinerary");
    try {
      const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
      const res = await fetch(`${BASE_URL}/api/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
        destination: dest.trim(),
        start_date: start,
        end_date: end,
        budget,

        preferred_categories:
            vibe
            ? vibe.split(",").map(s => s.trim()).filter(Boolean)
            : [],

        dietary_restrictions:
            dietary
            ? dietary.split(",").map(s => s.trim()).filter(Boolean)
            : [],

        required_attractions:
            must
            ? must.split(",").map(s => s.trim()).filter(Boolean)
            : [],

        trip_shape: shape,
        travel_mode: mode,
        }),
      });
      if (!res.ok) throw new Error(`Server returned ${res.status} — is the backend running?`);
      const data = await res.json();
      const t = transform(data);

      setTrip(t);

      if (t.anchor) {
        setSelectedHotel({
          name: t.anchor.name,
          lat: t.anchor.lat,
          lng: t.anchor.lng,
        });
      }

      setActiveDay(0);
      setOpenDays(t.days.map(d => d.day_number));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectStop = (stop) => {
    setSelectedStop(stop);
    if (stop) {
      const d = trip?.days.find(d => d.stops.some(s => s.id === stop.id));
      if (d) { setActiveDay(d.day_number); setOpenDays(p => p.includes(d.day_number) ? p : [...p, d.day_number]); }
    }
  };

  const inp = { width: "100%", padding: "7px 10px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 13, color: "#111", background: "#fff", outline: "none", boxSizing: "border-box", fontFamily: "inherit" };
  const lbl = { display: "block", fontSize: 10, fontWeight: 600, color: "#6b7280", marginBottom: 3, textTransform: "uppercase", letterSpacing: ".06em" };

  const totalStops = trip?.days.reduce((n, d) => n + d.stops.length, 0) || 0;
  const mandatoryCount = trip?.days.reduce((n, d) => n + d.stops.filter(s => s.is_mandatory).length, 0) || 0;

  return (
    <>
      <style>{`
        *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
        html,body,#root{width:100%;height:100%;overflow:hidden}
        body{font-family:'DM Sans',system-ui,sans-serif;background:#f9fafb}
        ::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:#d1d5db;border-radius:4px}
      `}</style>

      <div style={{ display: "flex", flexDirection: "column", width: "100vw", height: "100vh" }}>

        {/* Header */}
        <header style={{ display: "flex", alignItems: "center", gap: 14, padding: "0 20px", height: 50, flexShrink: 0, background: "#fff", borderBottom: "1px solid #e5e7eb", boxShadow: "0 1px 3px rgba(0,0,0,.05)" }}>
          <span style={{ fontSize: 18 }}>🗺️</span>
          <span style={{ fontSize: 15, fontWeight: 700, color: "#111", letterSpacing: "-.3px" }}>Wayfinder</span>
          <div style={{ width: 1, height: 18, background: "#e5e7eb" }} />
          {trip && (
            <div style={{ display: "flex", gap: 8, fontSize: 12, color: "#6b7280", flexWrap: "wrap" }}>
              <span>{trip.destination}</span>
              <span>·</span><span>{trip.days.length} days</span>
              <span>·</span><span>{totalStops} stops</span>
              {mandatoryCount > 0 && <><span>·</span><span style={{ color: "#059669" }}>📌 {mandatoryCount} must-see</span></>}
              {trip.weather_summary && <><span>·</span><span>🌤 {trip.weather_summary.split(",")[1]?.trim() || trip.weather_summary}</span></>}
            </div>
          )}
          {loading && <span style={{ fontSize: 12, color: "#2563EB" }}>⏳ Planning…</span>}
        </header>

        {/* Body */}
        <div style={{ display: "flex", flex: 1, minHeight: 0, overflow: "hidden" }}>

          {/* LEFT SIDEBAR */}
            <aside
            style={{
                width: 320,
                flexShrink: 0,
                background: "#fff",
                borderRight: "1px solid #e5e7eb",
                overflowY: "auto"
            }}
            >

            {/* Form */}
            <div style={{ padding: 14, borderBottom: "1px solid #f3f4f6", flexShrink: 0 }}>
              <div style={{ marginBottom: 8 }}>
                <label style={lbl}>Destination</label>
                <input style={inp} value={dest} placeholder="Tokyo, Paris, New York…"
                  onChange={e => setDest(e.target.value)} onKeyDown={e => e.key === "Enter" && handlePlan()} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 7, marginBottom: 8 }}>
                <div><label style={lbl}>From</label><input style={inp} type="date" value={start} onChange={e => setStart(e.target.value)} /></div>
                <div><label style={lbl}>To</label><input style={inp} type="date" value={end} onChange={e => setEnd(e.target.value)} /></div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 7, marginBottom: 8 }}>
                <div>
                  <label style={lbl}>Budget</label>
                  <select style={inp} value={budget} onChange={e => setBudget(e.target.value)}>
                    <option value="budget">Affordable</option>
                    <option value="mid-range">Mid-range</option>
                    <option value="luxury">Luxury</option>
                  </select>
                </div>
                <div>
                  <label style={lbl}>Pace</label>
                  <select style={inp} value={shape} onChange={e => setShape(e.target.value)}>
                    <option value="relaxed">Relaxed</option>
                    <option value="balanced">Balanced</option>
                    <option value="packed">Packed</option>
                  </select>
                </div>
              </div>
              <div style={{ marginBottom: 8 }}>
                <label style={lbl}>Vibe</label>
                <input style={inp} value={vibe} placeholder="culture, food, nightlife…" onChange={e => setVibe(e.target.value)} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 7, marginBottom: 8 }}>
                <div>
                  <label style={lbl}>Dietary</label>
                  <input style={inp} value={dietary} placeholder="vegetarian…" onChange={e => setDietary(e.target.value)} />
                </div>
                <div>
                  <label style={lbl}>Transport</label>
                  <select style={inp} value={mode} onChange={e => setMode(e.target.value)}>
                    <option value="TRANSIT">Public Transit</option>
                    <option value="DRIVE">Drive</option>
                    <option value="WALK">Walk</option>
                  </select>
                </div>
              </div>
              <div style={{ marginBottom: 10 }}>
                <label style={lbl}>Must-see</label>
                <input style={inp} value={must} placeholder="Eiffel Tower, Louvre…" onChange={e => setMust(e.target.value)} />
              </div>
              <button onClick={handlePlan} disabled={loading || !dest.trim()} style={{
                width: "100%", padding: "9px 0",
                background: loading || !dest.trim() ? "#9ca3af" : "#111",
                color: "#fff", border: "none", borderRadius: 7, fontSize: 13, fontWeight: 600,
                cursor: loading || !dest.trim() ? "not-allowed" : "pointer",
              }}>{loading ? "Planning… (15–30s)" : "Plan my trip →"}</button>
              {error && <div style={{ marginTop: 8, padding: "7px 10px", fontSize: 11, background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 6, color: "#b91c1c" }}>{error}</div>}
            </div>

            </aside>

            {/* MIDDLE PANEL */}
            <aside
            style={{
                width: 420,
                flexShrink: 0,
                background: "#fff",
                borderRight: "1px solid #e5e7eb",
                display: "flex",
                flexDirection: "column",
                overflow: "hidden"
            }}
            >

            {/* Tabs */}
            {trip && (
              <div style={{ display: "flex", borderBottom: "1px solid #e5e7eb", flexShrink: 0 }}>
                {["itinerary", "gaps", "notes", "hotels"].map(t => (
                  <button key={t} onClick={() => setTab(t)} style={{
                    flex: 1, padding: "8px 0", fontSize: 10, fontWeight: tab === t ? 700 : 400,
                    color: tab === t ? "#111" : "#9ca3af",
                    background: "transparent", border: "none",
                    borderBottom: tab === t ? "2px solid #111" : "2px solid transparent",
                    cursor: "pointer", textTransform: "capitalize",
                  }}>
                    {t}
                    {t === "gaps" && trip.gaps_structured?.length ? ` (${trip.gaps_structured.length})` : ""}
                  </button>
                ))}
              </div>
            )}

            {/* Day pills */}
            {trip && tab === "itinerary" && (
              <div style={{ display: "flex", gap: 5, padding: "7px 10px", borderBottom: "1px solid #f3f4f6", flexWrap: "wrap", flexShrink: 0 }}>
                {[0, ...trip.days.map(d => d.day_number)].map(d => {
                  const col = d === 0 ? "#374151" : DAY_COLORS[(d - 1) % DAY_COLORS.length];
                  const active = activeDay === d;
                  return (
                    <button key={d} onClick={() => setActiveDay(d)} style={{
                      padding: "3px 10px", borderRadius: 99, fontSize: 11, cursor: "pointer",
                      background: active ? col : "#fff", color: active ? "#fff" : col,
                      border: `1px solid ${active ? col : col + "66"}`,
                      fontWeight: active ? 600 : 400,
                    }}>{d === 0 ? "All" : `Day ${d}`}</button>
                  );
                })}
              </div>
            )}

            {/* Scrollable content */}
            <div style={{ flex: 1, overflowY: "auto", padding: "10px 10px 20px" }}>

              {!trip && !loading && (
                <div style={{ padding: "48px 16px", textAlign: "center", color: "#9ca3af" }}>
                  <div style={{ fontSize: 36, marginBottom: 12 }}>✈️</div>
                  <p style={{ fontSize: 13, lineHeight: 1.6 }}>Enter a destination and hit <strong style={{ color: "#374151" }}>Plan my trip</strong>.</p>
                </div>
              )}
              {loading && (
                <div style={{ padding: "48px 16px", textAlign: "center", color: "#6b7280" }}>
                  <div style={{ fontSize: 36, marginBottom: 12 }}>⏳</div>
                  <p style={{ fontSize: 13 }}>Fetching attractions and building your route…</p>
                  <p style={{ fontSize: 11, color: "#9ca3af", marginTop: 6 }}>Usually 15–30 seconds</p>
                </div>
              )}

              {/* Itinerary tab */}
              {trip && tab === "itinerary" && trip.days
                .filter(d => activeDay === 0 || d.day_number === activeDay)
                .map(day => (
                  <DayAccordion key={day.day_number} day={day}
                    open={openDays.includes(day.day_number)}
                    onToggle={() => setOpenDays(p => p.includes(day.day_number) ? p.filter(n => n !== day.day_number) : [...p, day.day_number])}
                    selectedStop={selectedStop} onSelectStop={handleSelectStop}
                  />
                ))
              }

              {/* Gaps tab — AI completeness suggestions */}
              {trip && tab === "gaps" && (
                <div>
                  {trip.weather_summary && (
                    <div style={{ padding: "8px 10px", background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 7, fontSize: 12, color: "#1d4ed8", marginBottom: 10 }}>
                      🌤 {trip.weather_summary}
                    </div>
                  )}
                  {(!trip.gaps_structured || trip.gaps_structured.length === 0) ? (
                    <p style={{ fontSize: 12, color: "#9ca3af", padding: "20px 0" }}>No gaps found — looks complete!</p>
                  ) : (
                    trip.gaps_structured.map((g, i) => (
                      <div key={i} style={{
                        fontSize: 12, color: g.text.startsWith("**") ? "#374151" : "#6b7280",
                        fontWeight: g.text.startsWith("**") ? 700 : 400,
                        padding: "5px 8px", borderRadius: 5,
                        background: g.text.startsWith("**") ? "#f9fafb" : "transparent",
                        marginBottom: 3, lineHeight: 1.5,
                      }}>
                        {g.text.startsWith("**") ? g.text.replace(/\*\*/g, "") : `• ${g.text}`}
                      </div>
                    ))
                  )}
                </div>
              )}

              {/* Notes tab */}
              {trip && tab === "notes" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                  {trip.planning_notes.length === 0 && <p style={{ fontSize: 12, color: "#9ca3af" }}>No planning notes.</p>}
                  {trip.planning_notes.map((note, i) => (
                    <div key={i} style={{ fontSize: 11, color: "#374151", padding: "7px 9px", background: "#f9fafb", borderRadius: 6, border: "1px solid #e5e7eb", lineHeight: 1.5 }}>{note}</div>
                  ))}
                  {trip.removed_stops.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <div style={{ fontSize: 10, fontWeight: 700, color: "#9ca3af", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 5 }}>Removed stops</div>
                      {trip.removed_stops.map((s, i) => (
                        <div key={i} style={{ fontSize: 11, color: "#9ca3af", padding: "3px 0", borderBottom: "1px solid #f3f4f6" }}>✕ {s}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Hotels tab */}
              {trip && tab === "hotels" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {(!trip.hotels || trip.hotels.length === 0) && <p style={{ fontSize: 12, color: "#9ca3af" }}>No hotel results.</p>}
                  {(trip.hotels || []).map((h, i) => (
                    <div
                      key={i}
                      onClick={() => {
                        setSelectedHotel({
                          name: h.name,
                          lat: h.lat,
                          lng: h.lng,
                        });
                      }}
                      style={{
                        padding: "10px 12px",
                        borderRadius: 8,
                        cursor: "pointer",
                        border:
                          selectedHotel?.name === h.name
                            ? "2px solid #2563EB"
                            : "1px solid #e5e7eb",
                        background:
                          selectedHotel?.name === h.name
                            ? "#eff6ff"
                            : "#fff"
                      }}
                    >
                      <div style={{ fontSize: 13, fontWeight: 600, color: "#111" }}>{h.name}</div>
                      <div style={{ display: "flex", gap: 8, fontSize: 11, color: "#6b7280", marginTop: 2 }}>
                        {h.rating && <span style={{ color: "#f59e0b" }}>★ {h.rating}</span>}
                        {h.num_reviews && <span>{h.num_reviews.toLocaleString()} reviews</span>}
                        {h.price_level && <span style={{ fontWeight: 600 }}>{h.price_level}</span>}
                      </div>
                      {h.address && <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 3 }}>{h.address}</div>}
                      {Object.keys(h.booking_links).length > 0 && (
                        <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: 7 }}>
                          {Object.entries(h.booking_links).slice(0, 3).map(([n, u]) => (
                            <a key={n} href={u} target="_blank" rel="noreferrer"
                              style={{ fontSize: 10, padding: "2px 8px", borderRadius: 99, border: "1px solid #d1d5db", color: "#374151", textDecoration: "none" }}>{n}</a>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </aside>

          {/* Map */}
          <main style={{ flex: 1, overflow: "hidden", position: "relative" }}>
            <MapPanel
              trip={trip}
              activeDay={activeDay}
              selectedStop={selectedStop}
              selectedHotel={selectedHotel}
              onSelectHotel={setSelectedHotel}
              onSelectStop={handleSelectStop}
            />
          </main>
        </div>
      </div>
    </>
  );
}
