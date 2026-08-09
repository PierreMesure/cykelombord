const publishedDataBaseUrl = "https://cdn.cykelombord.mesu.re";

// Local development uses symlinked generated files in public/router. Production
// uses the CORS-enabled GitHub Pages data site.
const routerDataBaseUrl = import.meta.env.DEV ? "/router" : publishedDataBaseUrl;

export function routerDataUrl(filename: string): string {
  return `${routerDataBaseUrl}/${filename}`;
}
