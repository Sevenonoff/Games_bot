// Универсальный рендер экрана: текст (безопасное HTML-подмножество), картинка, кнопки.
// Экраны партий с view рисуют игры (M3/M4); сюда приходят экраны без view и текстовая
// часть партий (заглушка Placeholder).
import type { VNode } from "preact";
import { useState } from "preact/hooks";
import type { Button, Screen } from "../protocol";
import { renderTelegramHtml } from "./html";

/** Меню узнаём по кнопке «Мемо» (tz-m2 §3.5). */
export function isMenuScreen(screen: Screen): boolean {
  return screen.rows.some((row) => row.some((b) => b.data === "new:memo"));
}

/** Основная кнопка экрана: первая в последнем ряду, если это «Играть»/«Ещё раз»/«Новая партия…». */
function isPrimary(text: string): boolean {
  const label = text.replace(/^\p{Extended_Pictographic}[\uFE0F]?\s*/u, "").trim();
  return label === "Играть" || label === "Ещё раз" || label.startsWith("Новая партия");
}

/** Кнопка-плитка игры из меню. */
function isGameButton(data: string): boolean {
  return data === "sea" || data.startsWith("new:");
}

const PLACEHOLDER_RATIO = 16 / 9;   // до загрузки место под картинку резервируем 16:9

export function GenericScreen(props: { screen: Screen; press: (payload: string) => void }): VNode {
  const { screen } = props;
  const menu = isMenuScreen(screen);

  // В меню кнопки игр идут плиткой по две; остальные ряды — как есть.
  const tiles: Button[] = [];
  const rows: Button[][] = [];
  for (const row of screen.rows) {
    if (menu && row.length === 1 && isGameButton(row[0].data)) tiles.push(row[0]);
    else rows.push(row);
  }

  return (
    <div class="screen">
      {screen.image !== null && <ScreenImage src={screen.image} menu={menu} />}
      <div class="text">{renderTelegramHtml(screen.text)}</div>
      {menu && tiles.length > 0 && (
        <div class="tiles">
          {tiles.map((b, i) => <TileButton key={i} button={b} press={props.press} />)}
        </div>
      )}
      {rows.map((row, i) => {
        const last = i === rows.length - 1;
        const primary = last && row.length <= 4 && isPrimary(row[0].text) ? row[0].data : null;
        return row.length >= 5 ? (
          <div class="cells" key={i} style={{ gridTemplateColumns: `repeat(${row.length}, 1fr)` }}>
            {row.map((b, j) => <CellButton key={j} button={b} press={props.press} />)}
          </div>
        ) : (
          <div class="row" key={i}>
            {row.map((b, j) => (
              <PressButton key={j} button={b} press={props.press} primary={b.data === primary} />
            ))}
          </div>
        );
      })}
    </div>
  );
}

/** Картинка во всю ширину над текстом: место резервируется заранее, появление плавное. */
function ScreenImage(props: { src: string; menu: boolean }): VNode {
  const [ratio, setRatio] = useState<number | null>(null);
  const [loaded, setLoaded] = useState(false);
  return (
    <div class={"image-box" + (props.menu ? " image-menu" : "")}
         style={{ aspectRatio: ratio ?? PLACEHOLDER_RATIO }}>
      <img
        src={props.src}
        alt=""
        class={loaded ? "loaded" : ""}
        onLoad={(e) => {
          const img = e.currentTarget;
          const w = img.naturalWidth, h = img.naturalHeight;
          if (w > 0 && h > 0) setRatio(w / h);
          setLoaded(true);
        }}
        onError={() => setLoaded(true)}
      />
    </div>
  );
}

function PressButton(props: { button: Button; press: (payload: string) => void; primary: boolean }): VNode {
  const disabled = props.button.data === "noop";
  return (
    <button
      type="button"
      class={"btn" + (props.primary ? " primary" : "")}
      disabled={disabled}
      data-payload={props.button.data}
      onClick={() => { if (!disabled) props.press(props.button.data); }}
    >
      {props.button.text}
    </button>
  );
}

/** Клетка игрового поля в старом виде: ряд из 5–8 кнопок — сетка квадратных клеток. */
function CellButton(props: { button: Button; press: (payload: string) => void }): VNode {
  const disabled = props.button.data === "noop";
  return (
    <button
      type="button"
      class="cell"
      disabled={disabled}
      data-payload={props.button.data}
      onClick={() => { if (!disabled) props.press(props.button.data); }}
    >
      {props.button.text}
    </button>
  );
}

/** Плитка игры: крупный эмодзи (первый символ подписи) и название. */
function TileButton(props: { button: Button; press: (payload: string) => void }): VNode {
  const emoji = [...props.button.text][0] ?? "";
  const name = props.button.text.slice(emoji.length).trim();
  return (
    <button type="button" class="tile" data-payload={props.button.data}
            onClick={() => props.press(props.button.data)}>
      <span class="tile-emoji">{emoji}</span>
      {name !== "" && <span class="tile-name">{name}</span>}
    </button>
  );
}
