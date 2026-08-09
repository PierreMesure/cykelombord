import { RangeQuery, Router, StopsIndex, Timetable } from "minotor";
import { routerDataUrl } from "./router-data";

type Request =
  | { type: "init"; date: string }
  | { type: "suggest"; field: "from" | "to"; query: string }
  | {
      type: "route";
      date: string;
      from: number;
      to: number;
      departureTime: number;
      journey: "outbound" | "return";
      searchId: number;
    };

let stopsIndex: StopsIndex | undefined;
const routers = new Map<string, Router>();
let routeMetadata: Record<string, Array<{ agency: string; service: string; agency_id: string }>> = {};

function toStop(stop: { id: number; name: string; platform?: string }) {
  return { id: stop.id, name: stop.name, platform: stop.platform };
}

async function initialise(date: string, notify = true): Promise<Router> {
  let activeRouter = routers.get(date);
  if (!activeRouter) {
    const timetableResponse = await fetch(routerDataUrl(`timetable-${date}.bin`));
    if (!timetableResponse.ok) {
      throw new Error("Kunde inte läsa den lokala tidtabellen. Kör först npm run prepare-router-data.");
    }
  if (!stopsIndex) {
    const [stopsResponse, metadataResponse] = await Promise.all([
      fetch(routerDataUrl("stops.bin")),
      fetch(routerDataUrl("route-metadata.json")),
    ]);
    if (!stopsResponse.ok || !metadataResponse.ok) {
      throw new Error("Kunde inte läsa den lokala tidtabellen. Kör först npm run prepare-router-data.");
    }
    stopsIndex = StopsIndex.fromData(new Uint8Array(await stopsResponse.arrayBuffer()));
    const metadata = (await metadataResponse.json()) as {
      by_short_name?: Record<string, Array<{ agency: string; service: string; agency_id: string }>>;
    };
    routeMetadata = metadata.by_short_name ?? {};
  }
    const timetable = Timetable.fromData(new Uint8Array(await timetableResponse.arrayBuffer()));
    activeRouter = new Router(timetable, stopsIndex);
    routers.set(date, activeRouter);
  }
  if (notify) self.postMessage({ type: "ready", stopCount: stopsIndex!.size(), date });
  return activeRouter;
}

self.addEventListener("message", ({ data }: MessageEvent<Request>) => {
  void (async () => {
    try {
      if (data.type === "init") {
        await initialise(data.date);
      } else if (data.type === "suggest") {
        if (!stopsIndex) return;
        self.postMessage({
          type: "suggestions",
          field: data.field,
          stops: stopsIndex.findStopsByName(data.query, 6).map(toStop),
        });
      } else if (data.type === "route") {
        const activeRouter = await initialise(data.date, false);
        const routes = activeRouter
          .rangeRoute(
            new RangeQuery.Builder()
              .from(data.from)
              .to(data.to)
              .departureTime(data.departureTime)
              .lastDepartureTime(data.departureTime + 120)
              .maxTransfers(4)
              .build(),
          )
          .getRoutes()
          .slice(0, 5);
        self.postMessage({
          type: "route",
          journey: data.journey,
          searchId: data.searchId,
          routes: routes.map((route) => ({
            legs: route.legs.map((leg) =>
              "route" in leg
                ? {
                    kind: "vehicle",
                    from: toStop(leg.from),
                    to: toStop(leg.to),
                    departureTime: leg.departureTime,
                    arrivalTime: leg.arrivalTime,
                    route: leg.route,
                    metadata: routeMetadata[leg.route.name] ?? [],
                  }
                : {
                    kind: "transfer",
                    from: toStop(leg.from),
                    to: toStop(leg.to),
                    duration: "duration" in leg ? leg.duration : leg.minTransferTime,
                  },
            ),
          })),
        });
      }
    } catch (error) {
      self.postMessage({
        type: "error",
        message: error instanceof Error ? error.message : "Okänt fel i ruttsökningen.",
      });
    }
  })();
});
