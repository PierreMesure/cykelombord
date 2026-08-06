import { cp, mkdir, stat } from "node:fs/promises";
import { resolve } from "node:path";

const projectRoot = resolve(import.meta.dirname, "../..");
const source = resolve(projectRoot, "data/generated/router");
const destination = resolve(projectRoot, "frontend/public/router");

try {
  await stat(resolve(source, "stops.bin"));
  await stat(resolve(projectRoot, "data/generated/gtfs/route-metadata.json"));
  await mkdir(destination, { recursive: true });
  await cp(source, destination, { recursive: true });
  await cp(
    resolve(projectRoot, "data/generated/gtfs/route-metadata.json"),
    resolve(destination, "route-metadata.json"),
  );
  console.log("Copied generated router data to frontend/public/router.");
} catch {
  console.error("Router data is missing. Generate it first with the Minotor parse command.");
  process.exitCode = 1;
}
