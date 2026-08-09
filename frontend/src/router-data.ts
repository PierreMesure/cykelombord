const releaseDataBaseUrl =
  "https://github.com/PierreMesure/cykelombord/releases/download/router-data";

// Local development uses generated files copied to public/router. Production
// always reads the rolling assets from the stable GitHub Release tag.
const routerDataBaseUrl = import.meta.env.DEV ? "/router" : releaseDataBaseUrl;

export function routerDataUrl(filename: string): string {
  return `${routerDataBaseUrl}/${filename}`;
}
