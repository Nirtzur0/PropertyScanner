import { useMemo, useState } from "react";
import DeckGL from "@deck.gl/react";
import { ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import Map, { NavigationControl } from "react-map-gl/maplibre";
import maplibregl from "maplibre-gl";

import type { MarkerPoint } from "../types";

const VOYAGER = "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json";

type MarkerRenderPoint = MarkerPoint & {
  fillColor: [number, number, number];
  ringColor: [number, number, number];
  labelText: string;
  isSelected: boolean;
  isBasketed: boolean;
  scoreWeight: number;
};

type WorkbenchMapProps = {
  markers: MarkerPoint[];
  selectedId?: string;
  selectedIds: string[];
  showHeat: boolean;
  showLabels: boolean;
  onSelect: (id: string, options: { multi: boolean }) => void;
  onHover: (marker?: MarkerPoint) => void;
};

type HoverState = {
  marker: MarkerPoint;
  x: number;
  y: number;
} | null;

type WorkbenchViewState = {
  longitude: number;
  latitude: number;
  zoom: number;
  pitch: number;
  bearing: number;
};

function hexToRgb(hex: string): [number, number, number] {
  const value = hex.replace("#", "");
  const full = value.length === 3 ? value.split("").map((ch) => ch + ch).join("") : value;
  const num = Number.parseInt(full, 16);
  return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
}

function labelText(marker: MarkerPoint) {
  if (marker.value_delta_pct !== undefined && marker.value_delta_pct !== null) {
    return `${Math.round(marker.value_delta_pct * 100)}%`;
  }
  return marker.label;
}

function ringColor(marker: MarkerPoint): [number, number, number] {
  if (marker.valuation_status !== "available") return [154, 90, 70];
  if (marker.watchlisted) return [45, 124, 130];
  if (marker.memo_state !== "none") return [197, 107, 55];
  if (marker.comp_review_state !== "none") return [214, 170, 78];
  return [255, 250, 242];
}

function isMultiSelectTrigger(event: unknown) {
  const maybe = event as { srcEvent?: { shiftKey?: boolean; metaKey?: boolean; ctrlKey?: boolean } };
  return Boolean(maybe?.srcEvent?.shiftKey || maybe?.srcEvent?.metaKey || maybe?.srcEvent?.ctrlKey);
}

export function WorkbenchMap({
  markers,
  selectedId,
  selectedIds,
  showHeat,
  showLabels,
  onSelect,
  onHover,
}: WorkbenchMapProps) {
  const [viewState, setViewState] = useState<WorkbenchViewState>({
    longitude: markers[0]?.lon ?? -3.7038,
    latitude: markers[0]?.lat ?? 40.4168,
    zoom: markers.length > 60 ? 5.8 : 7.2,
    pitch: 34,
    bearing: 0,
  });
  const [hovered, setHovered] = useState<HoverState>(null);

  const layers = useMemo(() => {
    const items: MarkerRenderPoint[] = markers.map((marker) => ({
      ...marker,
      fillColor: hexToRgb(marker.marker_color),
      ringColor: ringColor(marker),
      isSelected: marker.id === selectedId,
      isBasketed: selectedIds.includes(marker.id),
      scoreWeight: Math.max((marker.value_delta_pct ?? 0) + 0.12, 0.01),
      labelText: labelText(marker),
    }));

    const haloLayer = new ScatterplotLayer<MarkerRenderPoint>({
      id: "workbench-halo",
      data: items.filter((item) => item.isSelected || item.isBasketed || item.watchlisted),
      getPosition: (d) => [d.lon, d.lat],
      getFillColor: [0, 0, 0, 0],
      getLineColor: (d) => (d.isSelected ? [255, 250, 242] : d.ringColor),
      getRadius: (d) => (d.marker_size + (d.isSelected ? 18 : 10)) * 1050,
      radiusMinPixels: 14,
      radiusMaxPixels: 46,
      lineWidthMinPixels: 2.5,
      stroked: true,
      filled: false,
      pickable: false,
    });

    const pointLayer = new ScatterplotLayer<MarkerRenderPoint>({
      id: "workbench-points",
      data: items,
      getPosition: (d) => [d.lon, d.lat],
      getFillColor: (d) => d.fillColor,
      getLineColor: (d) => (d.isSelected ? [255, 250, 242] : [26, 37, 40]),
      getRadius: (d) => d.marker_size * 900,
      radiusMinPixels: 10,
      radiusMaxPixels: 36,
      lineWidthMinPixels: 1.5,
      stroked: true,
      filled: true,
      pickable: true,
      onClick: (info, event) => {
        if (info.object) {
          onSelect(info.object.id, { multi: isMultiSelectTrigger(event) });
        }
      },
      onHover: (info: PickingInfo<MarkerRenderPoint>) => {
        if (!info.object) {
          setHovered(null);
          onHover(undefined);
          return;
        }
        setHovered({
          marker: info.object,
          x: info.x ?? 0,
          y: info.y ?? 0,
        });
        onHover(info.object);
      },
    });

    const layersToRender: Layer[] = [haloLayer, pointLayer];

    if (showHeat) {
      layersToRender.unshift(
        new HeatmapLayer<MarkerRenderPoint>({
          id: "workbench-heat",
          data: items,
          getPosition: (d: MarkerRenderPoint) => [d.lon, d.lat],
          getWeight: (d: MarkerRenderPoint) => d.scoreWeight,
          radiusPixels: 65,
          intensity: 1.05,
          threshold: 0.08,
        }),
      );
    }

    if (showLabels && viewState.zoom >= 8.5) {
      layersToRender.push(
        new TextLayer<MarkerRenderPoint>({
          id: "workbench-labels",
          data: items,
          getPosition: (d: MarkerRenderPoint) => [d.lon, d.lat],
          getText: (d: MarkerRenderPoint) => d.labelText,
          getColor: [31, 37, 40],
          getSize: 13,
          getPixelOffset: [0, -24],
          getBackgroundColor: [255, 250, 242, 224],
          background: true,
          pickable: false,
          fontFamily: "IBM Plex Sans",
        }),
      );
    }

    return layersToRender;
  }, [markers, onHover, onSelect, selectedId, selectedIds, showHeat, showLabels, viewState.zoom]);

  return (
    <div className="map-card">
      <DeckGL
        controller
        viewState={viewState}
        onViewStateChange={(event) => {
          const next = event.viewState as unknown as WorkbenchViewState;
          setViewState({
            longitude: next.longitude,
            latitude: next.latitude,
            zoom: next.zoom,
            pitch: next.pitch,
            bearing: next.bearing,
          });
        }}
        layers={layers}
      >
        <Map mapLib={maplibregl} mapStyle={VOYAGER} reuseMaps>
          <NavigationControl position="top-right" />
        </Map>
      </DeckGL>

      <div className="map-overlay map-overlay-top">
        <div className="map-panel">
          <p className="eyebrow">Analyst dense map</p>
          <div className="map-badges">
            <span className="layer-chip">Color = support / source state</span>
            <span className="layer-chip">Size = value opportunity</span>
            <span className="layer-chip">Labels = delta or ask</span>
          </div>
        </div>
      </div>

      <div className="map-overlay map-overlay-right">
        <div className="map-legend">
          <strong>Legend</strong>
          <div className="legend-row">
            <span className="legend-pill">Teal: supported</span>
            <span className="legend-pill">Amber: degraded</span>
            <span className="legend-pill">Red: unavailable</span>
            <span className="legend-pill">Ring: watchlist / memo / selection</span>
          </div>
        </div>
      </div>

      {hovered ? (
        <div
          className="map-overlay map-overlay-bottom"
          style={{
            left: Math.min(Math.max(hovered.x - 40, 16), 520),
          }}
        >
          <div className="hover-card">
            <p className="eyebrow">{hovered.marker.next_action}</p>
            <h4>{hovered.marker.title}</h4>
            <p>
              {hovered.marker.city}, {hovered.marker.country}
            </p>
            <div className="hover-metrics">
              <div>
                <span className="tray-label">Ask</span>
                <strong>{hovered.marker.label}</strong>
              </div>
              <div>
                <span className="tray-label">Support</span>
                <strong>
                  {hovered.marker.support !== null && hovered.marker.support !== undefined
                    ? `${Math.round(hovered.marker.support * 100)}%`
                    : "N/A"}
                </strong>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
