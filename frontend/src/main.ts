import "./style.css";

const app = document.querySelector<HTMLElement>("#app");

if (!app) {
  throw new Error("Missing #app element");
}

app.innerHTML = `
  <section>
    <p class="eyebrow">Projektstruktur</p>
    <h1>Cykel på tåg</h1>
    <p>Den webbaserade reseplaneraren byggs i en senare milstolpe.</p>
  </section>
`;
