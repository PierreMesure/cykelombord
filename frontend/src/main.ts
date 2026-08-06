import "./style.css";

type Stop = { id: number; name: string; platform?: string };

type VehicleLeg = {
  kind: "vehicle";
  from: Stop;
  to: Stop;
  departureTime: number;
  arrivalTime: number;
  route: { name: string; type: string };
  metadata: Array<{ agency: string; service: string }>;
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
      <h1>Cykel på tåg</h1>
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
    const response = await fetch("/router/router-manifest.json");
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

  results.innerHTML = `
    <article class="journey">
      <div class="journey-summary">
        <div><strong>${formatTime(first.departureTime)}</strong><span>${first.from.name}</span></div>
        <div class="duration">${Math.max(0, last.arrivalTime - first.departureTime)} min<br><span>${Math.max(0, vehicles.length - 1)} byten</span></div>
        <div><strong>${formatTime(last.arrivalTime)}</strong><span>${last.to.name}</span></div>
      </div>
      <ol class="legs">
        ${route.legs
          .map((leg) => {
            if (leg.kind === "transfer") {
              return `<li class="transfer">Byte${leg.duration ? ` · minst ${leg.duration} min` : ""}</li>`;
            }
            const agencies = [...new Set(leg.metadata.map((item) => item.agency))];
            const services = [...new Set(leg.metadata.map((item) => item.service).filter(Boolean))];
            const operator = agencies.length ? agencies.join(" / ") : "Operatör saknas";
            const service = services.length === 1 ? ` · ${services[0]}` : "";
            return `<li>
              <time>${formatTime(leg.departureTime)}–${formatTime(leg.arrivalTime)}</time>
              <div><strong>${operator}${service}</strong><span>Linje ${leg.route.name} · ${leg.from.name} → ${leg.to.name}</span></div>
              <span class="mode">${leg.route.type}</span>
            </li>`;
          })
          .join("")}
      </ol>
      <p class="bike-note">Cykeln är tillåten enligt det prunade regelverket. Kapacitet, eventuell bokning och avgift visas i nästa steg.</p>
    </article>
  `;
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
