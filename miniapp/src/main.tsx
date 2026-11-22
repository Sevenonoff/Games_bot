// Вход: Telegram.WebApp.ready()/expand(), тема и монтирование <App/>.
import { render } from "preact";
import { App } from "./app/App";
import { applyTheme, watchTheme } from "./app/theme";
import "./app/app.css";

const tg = window.Telegram?.WebApp;
if (tg !== undefined) {
  tg.ready();
  tg.expand();
  applyTheme(tg.themeParams);
  watchTheme(tg);
}

render(<App />, document.getElementById("app")!);
