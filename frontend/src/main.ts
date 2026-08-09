import "./style.css";
import "iconify-icon";
import trainIcon from "@iconify/icons-material-symbols/train";
import { addIcon } from "iconify-icon";
import { routerDataUrl } from "./router-data";

// Keep the single glyph local so the planner remains functional offline.
addIcon("material-symbols:train", trainIcon);

type Stop = { id: number; name: string; platform?: string };

type VehicleLeg = {
  kind: "vehicle";
  from: Stop;
  to: Stop;
  departureTime: number;
  arrivalTime: number;
  route: { name: string; type: string };
  metadata: Array<{ agency: string; service: string; agency_id: string }>;
};

type TransferLeg = {
  kind: "transfer";
  from: Stop;
  to: Stop;
  duration?: number;
};

type Route = { legs: Array<VehicleLeg | TransferLeg> };

type WorkerResponse =
  | { type: "ready"; stopCount: number; date: string }
  | { type: "suggestions"; field: "from" | "to"; stops: Stop[] }
  | { type: "route"; route?: Route }
  | { type: "error"; message: string };

const app = document.querySelector<HTMLElement>("#app");

if (!app) {
  throw new Error("Missing #app element");
}

const worker = new Worker(new URL("./router.worker.ts", import.meta.url), {
  type: "module",
});

let ready = false;
let fromStop: Stop | undefined;
let toStop: Stop | undefined;
let availableDates = new Set<string>();

app.innerHTML = `
  <main>
    <header>
      <p class="eyebrow">Experimentell reseplanerare</p>
      <h1>Cykel ombord</h1>
      <p class="intro">Hitta resor i ett GTFS-urval där cykelreglerna har granskats.</p>
    </header>

    <section class="planner" aria-labelledby="planner-title">
      <div class="planner-heading">
        <h2 id="planner-title">Planera en resa</h2>
        <p id="status" role="status">Laddar den lokala tidtabellen …</p>
      </div>
      <form id="route-form">
        <div class="fields">
          <label class="field">
            <span>Från</span>
            <input id="from" name="from" autocomplete="off" placeholder="t.ex. Stockholm Central" disabled>
            <div id="from-suggestions" class="suggestions" hidden></div>
          </label>
          <label class="field">
            <span>Till</span>
            <input id="to" name="to" autocomplete="off" placeholder="t.ex. Uppsala Central" disabled>
            <div id="to-suggestions" class="suggestions" hidden></div>
          </label>
          <label class="field date-field">
            <span>Resdatum</span>
            <input id="date" name="date" type="date" disabled>
          </label>
        </div>
        <div class="form-footer">
          <p id="feed-note" class="feed-note">Laddar tillgängliga resdatum …</p>
          <button id="search" type="submit" disabled>Sök cykelvänlig resa</button>
        </div>
      </form>
    </section>

    <section id="results" class="results" aria-live="polite">
      <p class="empty">Välj två hållplatser för att prova ruttsökningen.</p>
    </section>

    <footer>
      <p>Ruttberäkningen körs lokalt i webbläsaren med den prunade GTFS-filen. Kontrollera alltid villkoren hos trafikbolaget före avresa.</p>
    </footer>
  </main>
`;

const form = document.querySelector<HTMLFormElement>("#route-form")!;
const status = document.querySelector<HTMLElement>("#status")!;
const feedNote = document.querySelector<HTMLElement>("#feed-note")!;
const results = document.querySelector<HTMLElement>("#results")!;
const searchButton = document.querySelector<HTMLButtonElement>("#search")!;
const dateInput = document.querySelector<HTMLInputElement>("#date")!;
const fields = {
  from: {
    input: document.querySelector<HTMLInputElement>("#from")!,
    suggestions: document.querySelector<HTMLElement>("#from-suggestions")!,
  },
  to: {
    input: document.querySelector<HTMLInputElement>("#to")!,
    suggestions: document.querySelector<HTMLElement>("#to-suggestions")!,
  },
};

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

const agencyColors = ["#286b59", "#b85c38", "#5367a6", "#9b4f76", "#7c6a32"];

function agencyInfo(leg: VehicleLeg): { agency: string; service: string; initials: string; color: string; agencyIds: string[] } {
  const agencies = [...new Set(leg.metadata.map((item) => item.agency).filter(Boolean))];
  const services = [...new Set(leg.metadata.map((item) => item.service).filter(Boolean))];
  const agencyIds = [...new Set(leg.metadata.map((item) => item.agency_id).filter(Boolean))];
  const agency = agencies.length ? agencies.join(" / ") : "Operatör saknas";
  const service = services.length === 1 ? services[0]! : "";
  const initials = agency
    .split(/\s+/)
    .filter((word) => word.length > 2)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase() || "TÅG";
  const colorIndex = [...agency].reduce((hash, character) => hash + character.charCodeAt(0), 0);
  return { agency, service, initials, color: agencyColors[colorIndex % agencyColors.length]!, agencyIds };
}

function operatorBadge(info: ReturnType<typeof agencyInfo>): string {
  const agencyId = info.agencyIds[0];
  const fallback = `<span class="operator-fallback"><span class="operator-initials">${info.initials}</span><span>${info.agency}</span></span>`;
  if (!agencyId) return fallback;
  return `<span class="operator-badge"><img class="operator-logo" src="https://reseplanerare.resrobot.se/img/light/operators/${agencyId}.png" alt="${info.agency}" loading="lazy"><span class="operator-fallback" hidden><span class="operator-initials">${info.initials}</span><span>${info.agency}</span></span></span>`;
}

function updateSearchState(): void {
  searchButton.disabled = !ready || !fromStop || !toStop;
}

function loadDate(value: string): void {
  if (!availableDates.has(value)) {
    ready = false;
    updateSearchState();
    status.textContent = "Det datumet har ingen publicerad tidtabell.";
    return;
  }
  ready = false;
  updateSearchState();
  status.textContent = "Laddar den lokala tidtabellen …";
  worker.postMessage({ type: "init", date: value });
}

async function loadManifest(): Promise<void> {
  try {
    const response = await fetch(routerDataUrl("router-manifest.json"));
    if (!response.ok) throw new Error("missing manifest");
    const manifest = (await response.json()) as { available_dates?: Array<{ date: string }> };
    const dates = manifest.available_dates?.map((item) => item.date) ?? [];
    if (!dates.length) throw new Error("empty manifest");
    availableDates = new Set(dates);
    dateInput.min = dates[0]!;
    dateInput.max = dates.at(-1)!;
    const today = new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Stockholm" });
    dateInput.value = availableDates.has(today) ? today : dates[0]!;
    dateInput.disabled = false;
    feedNote.textContent = `Tidtabeller finns ${dates[0]}–${dates.at(-1)}.`;
    loadDate(dateInput.value);
  } catch {
    status.textContent = "Kunde inte läsa listan över publicerade tidtabeller.";
    feedNote.textContent = "Ingen tidtabell är tillgänglig.";
  }
}

function selectStop(field: "from" | "to", stop: Stop): void {
  fields[field].input.value = stop.name;
  fields[field].suggestions.hidden = true;
  if (field === "from") fromStop = stop;
  else toStop = stop;
  updateSearchState();
}

function showSuggestions(field: "from" | "to", stops: Stop[]): void {
  const container = fields[field].suggestions;
  container.replaceChildren();
  for (const stop of stops) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = stop.platform ? `${stop.name}, läge ${stop.platform}` : stop.name;
    button.addEventListener("mousedown", (event) => {
      event.preventDefault();
      selectStop(field, stop);
    });
    container.append(button);
  }
  container.hidden = stops.length === 0;
}

function renderRoute(route: Route | undefined): void {
  if (!route) {
    results.innerHTML = `<p class="empty">Ingen cykelvänlig resa hittades i den här tidtabellen.</p>`;
    return;
  }

  const vehicles = route.legs.filter((leg): leg is VehicleLeg => leg.kind === "vehicle");
  const first = vehicles[0];
  const last = vehicles.at(-1);
  if (!first || !last) return;

  const changes = Math.max(0, vehicles.length - 1);
  const pathSegments: string[] = [];
  const details: string[] = [];

  details.push(`<li class="detail-station detail-station-start"><div class="station-times"><time>${formatTime(first.departureTime)}</time></div><span class="station-dot" aria-hidden="true"></span><span class="station-name">${first.from.name}</span></li>`);

  for (const [index, leg] of vehicles.entries()) {
    const info = agencyInfo(leg);
    const legDuration = leg.arrivalTime - leg.departureTime;
    if (index > 0) {
      const previous = vehicles[index - 1]!;
      const waiting = Math.max(0, leg.departureTime - previous.arrivalTime);
      pathSegments.push(`<span class="path-dent" aria-label="Byte"></span>`);
      details.push(`<li class="detail-station detail-station-connection"><div class="station-times"><time>${formatTime(previous.arrivalTime)}</time><time>${formatTime(leg.departureTime)}</time></div><span class="station-dot" aria-hidden="true"></span><span class="station-name">${leg.from.name}</span><small class="station-wait">${formatDuration(waiting)}</small></li>`);
    }
    pathSegments.push(`<span class="path-segment" style="--segment-color: ${info.color}" title="${info.agency}"><iconify-icon icon="material-symbols:train" class="path-train" aria-hidden="true"></iconify-icon></span>`);
    details.push(`<li class="detail-service" style="--segment-color: ${info.color}"><span class="detail-marker" aria-hidden="true"><iconify-icon icon="material-symbols:train" class="train-icon"></iconify-icon></span><div class="detail-title"><span class="line-badge">${leg.route.name}</span><strong>${operatorBadge(info)}${info.service || ""}</strong><small>${formatDuration(legDuration)}</small></div></li>`);
  }

  details.push(`<li class="detail-station detail-station-end"><div class="station-times"><time>${formatTime(last.arrivalTime)}</time></div><span class="station-dot" aria-hidden="true"></span><span class="station-name">${last.to.name}</span></li>`);

  results.innerHTML = `
    <article class="journey">
      <div class="journey-summary">
        <div><strong>${formatTime(first.departureTime)}</strong><span>${first.from.name}</span></div>
        <div class="duration"><strong>${formatDuration(last.arrivalTime - first.departureTime)}</strong><span>${changes} ${changes === 1 ? "byte" : "byten"}</span></div>
        <div><strong>${formatTime(last.arrivalTime)}</strong><span>${last.to.name}</span></div>
      </div>
      <div class="journey-path" aria-label="Resans byten"><span class="path-node" aria-hidden="true"></span><span class="path-route">${pathSegments.join("")}</span><span class="path-node" aria-hidden="true"></span></div>
      <div class="path-labels"><span>${first.from.name}</span><span>${last.to.name}</span></div>
      <details class="journey-details">
        <summary><span>Visa resans detaljer</span><span class="summary-arrow" aria-hidden="true">⌄</span></summary>
        <ol class="detail-legs">${details.join("")}</ol>
      </details>
    </article>
  `;
  results.querySelectorAll<HTMLImageElement>(".operator-logo").forEach((image) => {
    const fallback = image.nextElementSibling as HTMLElement | null;
    image.addEventListener("load", () => { if (fallback) fallback.hidden = true; });
    image.addEventListener("error", () => { image.hidden = true; if (fallback) fallback.hidden = false; });
  });
}

for (const [field, controls] of Object.entries(fields) as Array<
  ["from" | "to", (typeof fields)["from"]]
>) {
  controls.input.addEventListener("input", () => {
    if (field === "from") fromStop = undefined;
    else toStop = undefined;
    updateSearchState();
    const query = controls.input.value.trim();
    if (query.length < 2) {
      controls.suggestions.hidden = true;
      return;
    }
    worker.postMessage({ type: "suggest", field, query });
  });
  controls.input.addEventListener("blur", () => {
    window.setTimeout(() => (controls.suggestions.hidden = true), 150);
  });
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!fromStop || !toStop) return;
  results.innerHTML = `<p class="empty">Söker i den lokala tidtabellen …</p>`;
  worker.postMessage({
    type: "route",
    from: fromStop.id,
    to: toStop.id,
    departureTime: 8 * 60,
  });
});

dateInput.addEventListener("change", () => loadDate(dateInput.value));

worker.addEventListener("message", ({ data }: MessageEvent<WorkerResponse>) => {
  if (data.type === "ready") {
    ready = true;
    status.textContent = `${data.stopCount} hållplatser laddade lokalt för ${data.date}`;
    fields.from.input.disabled = false;
    fields.to.input.disabled = false;
    updateSearchState();
  } else if (data.type === "suggestions") {
    showSuggestions(data.field, data.stops);
  } else if (data.type === "route") {
    renderRoute(data.route);
  } else if (data.type === "error") {
    status.textContent = data.message;
    results.innerHTML = `<p class="empty">${data.message}</p>`;
  }
});

void loadManifest();
