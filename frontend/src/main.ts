import "./style.css";
import "iconify-icon";
import trainIcon from "@iconify/icons-material-symbols/train";
import keyboardArrowDownIcon from "@iconify/icons-material-symbols/keyboard-arrow-down";
import { addIcon } from "iconify-icon";
import { renderJourney, type Route, type Stop } from "./journey";
import { routerDataUrl } from "./router-data";

// Keep the single glyph local so the planner remains functional offline.
addIcon("material-symbols:train", trainIcon);
addIcon("material-symbols:keyboard-arrow-down", keyboardArrowDownIcon);

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
      <p class="eyebrow"><span class="beta-badge">BETA</span></p>
      <h1>Cykel ombord</h1>
      <p class="intro">Hitta tågresor som tillåter cyklar</p>
    </header>

    <section class="planner" aria-label="Resesökning">
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
            <small id="date-error" class="date-error" hidden>Datumet finns inte i databasen. Enbart 90 dagar framåt</small>
          </label>
        </div>
        <div class="form-footer">
          <button id="search" type="submit" disabled>Sök cykelvänlig resa</button>
        </div>
      </form>
    </section>

    <section id="results" class="results" aria-live="polite">
    </section>

    <footer>
      <p>Denna webbsida togs fram av <a href="https://mesu.re" rel="author">Pierre Mesure</a> och publiceras som <a href="https://github.com/PierreMesure/cykelombord">öppen källkod</a> ❤️ (AGPLv3).</p>
    </footer>
  </main>
`;

const form = document.querySelector<HTMLFormElement>("#route-form")!;
const results = document.querySelector<HTMLElement>("#results")!;
const searchButton = document.querySelector<HTMLButtonElement>("#search")!;
const dateInput = document.querySelector<HTMLInputElement>("#date")!;
const dateError = document.querySelector<HTMLElement>("#date-error")!;
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

function updateSearchState(): void {
  searchButton.disabled = !ready || !fromStop || !toStop;
}

function loadDate(value: string): void {
  if (!availableDates.has(value)) {
    ready = false;
    updateSearchState();
    dateError.hidden = false;
    return;
  }
  dateError.hidden = true;
  ready = false;
  updateSearchState();
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
    loadDate(dateInput.value);
  } catch {
    results.innerHTML = `<p class="empty">Kunde inte läsa listan över publicerade tidtabeller.</p>`;
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
    fields.from.input.disabled = false;
    fields.to.input.disabled = false;
    updateSearchState();
  } else if (data.type === "suggestions") {
    showSuggestions(data.field, data.stops);
  } else if (data.type === "route") {
    results.replaceChildren(renderJourney(data.route));
  } else if (data.type === "error") {
    results.innerHTML = `<p class="empty">${data.message}</p>`;
  }
});

void loadManifest();
