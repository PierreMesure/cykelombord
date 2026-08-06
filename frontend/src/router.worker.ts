import { Query, Router, StopsIndex, Timetable } from "minotor";

type Request =
  | { type: "init"; date: string }
  | { type: "suggest"; field: "from" | "to"; query: string }
  | { type: "route"; from: number; to: number; departureTime: number };

let stopsIndex: StopsIndex | undefined;
let router: Router | undefined;
let routeMetadata: Record<string, Array<{ agency: string; service: string }>> = {};

function toStop(stop: { id: number; name: string; platform?: string }) {
  return { id: stop.id, name: stop.name, platform: stop.platform };
}

async function initialise(date: string): Promise<void> {
  const timetableResponse = await fetch(`/router/timetable-${date}.bin`);
  if (!timetableResponse.ok) {
    throw new Error("Kunde inte läsa den lokala tidtabellen. Kör först npm run prepare-router-data.");
  }
  if (!stopsIndex) {
    const [stopsResponse, metadataResponse] = await Promise.all([
      fetch("/router/stops.bin"),
      fetch("/router/route-metadata.json"),
    ]);
    if (!stopsResponse.ok || !metadataResponse.ok) {
      throw new Error("Kunde inte läsa den lokala tidtabellen. Kör först npm run prepare-router-data.");
    }
    stopsIndex = StopsIndex.fromData(new Uint8Array(await stopsResponse.arrayBuffer()));
    const metadata = (await metadataResponse.json()) as {
      by_short_name?: Record<string, Array<{ agency: string; service: string }>>;
    };
    routeMetadata = metadata.by_short_name ?? {};
  }
  const timetable = Timetable.fromData(new Uint8Array(await timetableResponse.arrayBuffer()));
  router = new Router(timetable, stopsIndex);
  self.postMessage({ type: "ready", stopCount: stopsIndex.size(), date });
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
        if (!router) return;
        const route = router
          .route(
            new Query.Builder()
              .from(data.from)
              .to(data.to)
              .departureTime(data.departureTime)
              .maxTransfers(4)
              .build(),
          )
          .bestRoute();
        self.postMessage({
          type: "route",
          route: route && {
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
          },
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
