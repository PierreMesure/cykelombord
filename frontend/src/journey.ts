export type Stop = { id: number; name: string; platform?: string };

export type VehicleLeg = {
  kind: "vehicle";
  from: Stop;
  to: Stop;
  departureTime: number;
  arrivalTime: number;
  route: { name: string; type: string };
  metadata: Array<{ agency: string; service: string; agency_id: string }>;
};

export type TransferLeg = {
  kind: "transfer";
  from: Stop;
  to: Stop;
  duration?: number;
};

export type Route = { legs: Array<VehicleLeg | TransferLeg> };

type AgencyInfo = {
  agency: string;
  service: string;
  initials: string;
  color: string;
  agencyIds: string[];
};

const agencyColors = ["#286b59", "#b85c38", "#5367a6", "#9b4f76", "#7c6a32"];

function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function icon(name: string, className: string): HTMLElement {
  const node = document.createElement("iconify-icon");
  node.setAttribute("icon", name);
  node.className = className;
  node.setAttribute("aria-hidden", "true");
  return node;
}

function formatTime(minutes: number): string {
  const hours = Math.floor(minutes / 60) % 24;
  const mins = minutes % 60;
  return `${String(hours).padStart(2, "0")}:${String(mins).padStart(2, "0")}`;
}

function formatDuration(minutes: number): string {
  const rounded = Math.max(0, Math.round(minutes));
  if (rounded < 60) return `${rounded} min`;
  const hours = Math.floor(rounded / 60);
  const remaining = rounded % 60;
  return remaining ? `${hours} h ${remaining} min` : `${hours} h`;
}

function getAgencyInfo(leg: VehicleLeg): AgencyInfo {
  const agencies = [...new Set(leg.metadata.map((item) => item.agency).filter(Boolean))];
  const services = [...new Set(leg.metadata.map((item) => item.service).filter(Boolean))];
  const agencyIds = [...new Set(leg.metadata.map((item) => item.agency_id).filter(Boolean))];
  const agency = agencies.length ? agencies.join(" / ") : "Operatör saknas";
  const service = services.length === 1 ? services[0]! : "";
  const initials =
    agency
      .split(/\s+/)
      .filter((word) => word.length > 2)
      .slice(0, 2)
      .map((word) => word[0])
      .join("")
      .toUpperCase() || "TÅG";
  const colorIndex = [...agency].reduce((hash, character) => hash + character.charCodeAt(0), 0);
  return {
    agency,
    service,
    initials,
    color: agencyColors[colorIndex % agencyColors.length]!,
    agencyIds,
  };
}

function renderOperatorFallback(info: AgencyInfo): HTMLElement {
  const fallback = element("span", "operator-fallback");
  fallback.append(
    element("span", "operator-initials", info.initials),
    element("span", "operator-name", info.agency),
  );
  return fallback;
}

function renderOperatorBadge(info: AgencyInfo): HTMLElement {
  const agencyId = info.agencyIds[0];
  const fallback = renderOperatorFallback(info);
  if (!agencyId) return fallback;

  const badge = element("span", "operator-badge");
  const image = element("img", "operator-logo");
  image.src = `https://reseplanerare.resrobot.se/img/light/operators/${agencyId}.png`;
  image.alt = info.agency;
  image.loading = "lazy";
  fallback.hidden = true;
  image.addEventListener("load", () => (fallback.hidden = true));
  image.addEventListener("error", () => {
    image.hidden = true;
    fallback.hidden = false;
  });
  badge.append(image, fallback);
  return badge;
}

function renderJourneySummary(first: VehicleLeg, last: VehicleLeg, changes: number): HTMLElement {
  const summary = element("div", "journey-summary");
  const departure = element("div");
  departure.append(
    element("strong", undefined, formatTime(first.departureTime)),
    element("span", undefined, first.from.name),
  );
  const duration = element("div", "duration");
  duration.append(
    element("strong", undefined, formatDuration(last.arrivalTime - first.departureTime)),
    element("span", undefined, `${changes} ${changes === 1 ? "byte" : "byten"}`),
  );
  const arrival = element("div");
  arrival.append(
    element("strong", undefined, formatTime(last.arrivalTime)),
    element("span", undefined, last.to.name),
  );
  summary.append(departure, duration, arrival);
  return summary;
}

function renderJourneyPath(vehicles: VehicleLeg[]): DocumentFragment {
  const fragment = document.createDocumentFragment();
  const path = element("div", "journey-path");
  path.setAttribute("aria-label", "Resans byten");
  const route = element("span", "path-route");

  vehicles.forEach((leg, index) => {
    const info = getAgencyInfo(leg);
    if (index > 0) {
      const change = element("span", "path-dent");
      change.setAttribute("aria-label", "Byte");
      route.append(change);
    }
    const segment = element("span", "path-segment");
    segment.style.setProperty("--segment-color", info.color);
    segment.title = info.agency;
    segment.append(icon("material-symbols:train", "path-train"));
    route.append(segment);
  });

  const startNode = element("span", "path-node");
  const endNode = element("span", "path-node");
  startNode.setAttribute("aria-hidden", "true");
  endNode.setAttribute("aria-hidden", "true");
  path.append(startNode, route, endNode);

  const labels = element("div", "path-labels");
  labels.append(
    element("span", undefined, vehicles[0]!.from.name),
    element("span", undefined, vehicles.at(-1)!.to.name),
  );
  fragment.append(path, labels);
  return fragment;
}

function renderTimelineTrack(kind: "start" | "connection" | "service" | "end"): HTMLElement {
  const track = element("span", `detail-track detail-track-${kind}`);
  track.setAttribute("aria-hidden", "true");
  if (kind === "service") {
    const marker = element("span", "service-marker");
    marker.append(icon("material-symbols:train", "train-icon"));
    track.append(marker);
  } else {
    track.append(element("span", "station-dot"));
  }
  return track;
}

function renderStationRow(
  kind: "start" | "connection" | "end",
  stop: Stop,
  times: number[],
  waiting?: number,
): HTMLLIElement {
  const row = element("li", `detail-row detail-station detail-station-${kind}`);
  const timeCell = element("div", "station-times");
  for (const value of times) timeCell.append(element("time", undefined, formatTime(value)));
  row.append(timeCell, renderTimelineTrack(kind), element("span", "station-name", stop.name));
  if (waiting !== undefined) {
    row.append(element("small", "station-wait", `b. ${formatDuration(waiting)}`));
  }
  return row;
}

function renderServiceRow(leg: VehicleLeg): HTMLLIElement {
  const info = getAgencyInfo(leg);
  const row = element("li", "detail-row detail-service");
  row.style.setProperty("--segment-color", info.color);
  const title = element("div", "detail-title");
  const operator = element("div", "detail-operator");
  operator.append(renderOperatorBadge(info));
  const service = element("div", "detail-service-info");
  service.append(element("span", "line-badge", leg.route.name));
  if (info.service) service.append(element("strong", undefined, info.service));
  title.append(
    operator,
    service,
    element("small", "service-duration", formatDuration(leg.arrivalTime - leg.departureTime)),
  );
  row.append(element("span", "detail-time-spacer"), renderTimelineTrack("service"), title);
  return row;
}

function renderDetailRows(vehicles: VehicleLeg[]): HTMLOListElement {
  const list = element("ol", "detail-legs");
  const first = vehicles[0]!;
  list.append(renderStationRow("start", first.from, [first.departureTime]));

  vehicles.forEach((leg, index) => {
    if (index > 0) {
      const previous = vehicles[index - 1]!;
      list.append(
        renderStationRow(
          "connection",
          leg.from,
          [previous.arrivalTime, leg.departureTime],
          Math.max(0, leg.departureTime - previous.arrivalTime),
        ),
      );
    }
    list.append(renderServiceRow(leg));
  });

  const last = vehicles.at(-1)!;
  list.append(renderStationRow("end", last.to, [last.arrivalTime]));
  return list;
}

function renderDetailsToggle(): HTMLElement {
  const summary = element("summary");
  const label = element("span", "summary-label");
  label.append(
    element("span", "summary-closed", "Detaljer"),
    element("span", "summary-open", "Göm detaljer"),
  );
  summary.append(
    label,
    icon("material-symbols:keyboard-arrow-down", "summary-arrow"),
  );
  return summary;
}

function renderJourneyDetails(vehicles: VehicleLeg[]): HTMLDetailsElement {
  const details = element("details", "journey-details");
  details.append(renderDetailsToggle(), renderDetailRows(vehicles));
  return details;
}

export function renderJourney(route: Route | undefined): HTMLElement {
  if (!route) {
    return element("p", "empty", "Ingen cykelvänlig resa hittades i den här tidtabellen.");
  }

  const vehicles = route.legs.filter((leg): leg is VehicleLeg => leg.kind === "vehicle");
  const first = vehicles[0];
  const last = vehicles.at(-1);
  if (!first || !last) {
    return element("p", "empty", "Ingen cykelvänlig resa hittades i den här tidtabellen.");
  }

  const journey = element("article", "journey");
  journey.append(
    renderJourneySummary(first, last, Math.max(0, vehicles.length - 1)),
    renderJourneyPath(vehicles),
    renderJourneyDetails(vehicles),
  );
  return journey;
}
