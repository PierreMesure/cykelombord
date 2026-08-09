import { mkdir, readdir, rm, stat, symlink } from "node:fs/promises";
import { dirname, relative, resolve } from "node:path";

const projectRoot = resolve(import.meta.dirname, "../..");
const source = resolve(projectRoot, "data/generated/router");
const destination = resolve(projectRoot, "frontend/public/router");

try {
  await stat(resolve(source, "stops.bin"));
  await stat(resolve(projectRoot, "data/generated/gtfs/route-metadata.json"));
  await mkdir(destination, { recursive: true });
  for (const entry of await readdir(destination)) {
    if (entry !== ".gitkeep") await rm(resolve(destination, entry), { recursive: true });
  }
  for (const entry of await readdir(source)) {
    const destinationPath = resolve(destination, entry);
    await symlink(relative(dirname(destinationPath), resolve(source, entry)), destinationPath);
  }
  const metadataPath = resolve(destination, "route-metadata.json");
  const metadataSource = resolve(projectRoot, "data/generated/gtfs/route-metadata.json");
  await symlink(relative(dirname(metadataPath), metadataSource), metadataPath);
  console.log("Symlinked generated router data into frontend/public/router.");
} catch {
  console.error("Router data is missing. Generate it first with the Minotor parse command.");
  process.exitCode = 1;
}
