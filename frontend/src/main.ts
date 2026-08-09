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
      <div class="brand-row">
        <img class="brand-logo" src="/logo.webp" alt="" width="480" height="407">
        <h1>Cykel ombord</h1>
        <span class="beta-badge">BETA</span>
      </div>
      <p class="intro">Hitta kollektivtrafik som tillåter cyklar</p>
    </header>

    <section class="planner" aria-label="Resesökning">
      <form id="route-form">
        <div class="fields">
          <label class="field">
            <span>Från</span>
            <input id="from" name="from" role="combobox" autocomplete="off" autocorrect="off" autocapitalize="none" spellcheck="false" aria-autocomplete="list" aria-controls="from-suggestions" aria-expanded="false" placeholder="t.ex. Stockholm C" disabled>
            <div id="from-suggestions" class="suggestions" role="listbox" hidden></div>
          </label>
          <label class="field">
            <span>Till</span>
            <input id="to" name="to" role="combobox" autocomplete="off" autocorrect="off" autocapitalize="none" spellcheck="false" aria-autocomplete="list" aria-controls="to-suggestions" aria-expanded="false" placeholder="t.ex. Uppsala C" disabled>
            <div id="to-suggestions" class="suggestions" role="listbox" hidden></div>
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
      <p>Denna webbsida togs fram av <a href="https://pierre.mesu.re" target="_blank" rel="author">Pierre Mesure</a> och publiceras som <a href="https://github.com/PierreMesure/cykelombord" target="_blank">öppen källkod</a> ❤️ (AGPLv3).</p>
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
type FieldName = keyof typeof fields;
const suggestionState: Record<FieldName, { stops: Stop[]; activeIndex: number }> = {
  from: { stops: [], activeIndex: -1 },
  to: { stops: [], activeIndex: -1 },
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

function hideSuggestions(field: FieldName): void {
  const controls = fields[field];
  const state = suggestionState[field];
  controls.suggestions.hidden = true;
  controls.input.setAttribute("aria-expanded", "false");
  controls.input.removeAttribute("aria-activedescendant");
  state.activeIndex = -1;
  controls.suggestions.querySelectorAll("[role='option']").forEach((option) => {
    option.setAttribute("aria-selected", "false");
  });
}

function selectStop(field: FieldName, stop: Stop): void {
  fields[field].input.value = stop.name;
  hideSuggestions(field);
  if (field === "from") fromStop = stop;
  else toStop = stop;
  updateSearchState();
}

function setActiveSuggestion(field: FieldName, index: number): void {
  const controls = fields[field];
  const state = suggestionState[field];
  if (!state.stops.length) return;
  state.activeIndex = (index + state.stops.length) % state.stops.length;
  const options = [...controls.suggestions.querySelectorAll<HTMLElement>("[role='option']")];
  options.forEach((option, optionIndex) => {
    option.setAttribute("aria-selected", String(optionIndex === state.activeIndex));
  });
  const activeOption = options[state.activeIndex];
  if (activeOption) {
    controls.input.setAttribute("aria-activedescendant", activeOption.id);
    activeOption.scrollIntoView({ block: "nearest" });
  }
}

function focusNextField(field: FieldName): void {
  if (field === "from") fields.to.input.focus();
  else dateInput.focus();
}

function showSuggestions(field: FieldName, stops: Stop[]): void {
  const controls = fields[field];
  const container = controls.suggestions;
  suggestionState[field] = { stops, activeIndex: -1 };
  container.replaceChildren();
  for (const [index, stop] of stops.entries()) {
    const button = document.createElement("button");
    button.type = "button";
    button.id = `${field}-suggestion-${index}`;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", "false");
    button.textContent = stop.platform ? `${stop.name}, läge ${stop.platform}` : stop.name;
    button.addEventListener("mouseenter", () => setActiveSuggestion(field, index));
    button.addEventListener("mousedown", (event) => {
      event.preventDefault();
      selectStop(field, stop);
    });
    container.append(button);
  }
  container.hidden = stops.length === 0;
  controls.input.setAttribute("aria-expanded", String(stops.length > 0));
  if (!stops.length) controls.input.removeAttribute("aria-activedescendant");
}

for (const [field, controls] of Object.entries(fields) as Array<
  [FieldName, (typeof fields)["from"]]
>) {
  controls.input.addEventListener("input", () => {
    if (field === "from") fromStop = undefined;
    else toStop = undefined;
    updateSearchState();
    const query = controls.input.value.trim();
    if (query.length < 2) {
      suggestionState[field].stops = [];
      hideSuggestions(field);
      return;
    }
    worker.postMessage({ type: "suggest", field, query });
  });
  controls.input.addEventListener("keydown", (event) => {
    const state = suggestionState[field];
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (!state.stops.length) return;
      event.preventDefault();
      controls.suggestions.hidden = false;
      controls.input.setAttribute("aria-expanded", "true");
      const direction = event.key === "ArrowDown" ? 1 : -1;
      setActiveSuggestion(field, state.activeIndex + direction);
    } else if (event.key === "Enter" && state.activeIndex >= 0 && !controls.suggestions.hidden) {
      event.preventDefault();
      const stop = state.stops[state.activeIndex];
      if (stop) {
        selectStop(field, stop);
        focusNextField(field);
      }
    } else if (event.key === "Escape" && !controls.suggestions.hidden) {
      event.preventDefault();
      hideSuggestions(field);
    }
  });
  controls.input.addEventListener("blur", () => {
    window.setTimeout(() => hideSuggestions(field), 150);
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
