// Безопасный рендер HTML-подмножества Telegram: белый список тегов, script/onerror/
// javascript: экранируются или выбрасываются, переносы строк → <br>.
import { cleanup, render } from "@testing-library/preact";
import { afterEach, describe, expect, it } from "vitest";
import { parseTelegramHtml, renderTelegramHtml } from "../../src/app/html";

afterEach(cleanup);

describe("parseTelegramHtml: белый список", () => {
  it("разрешённые теги разбираются", () => {
    expect(parseTelegramHtml("<b>жирный</b>")).toEqual([{ tag: "b", children: ["жирный"] }]);
    expect(parseTelegramHtml("<strong>x</strong>")).toEqual([{ tag: "strong", children: ["x"] }]);
    expect(parseTelegramHtml("<i>a</i><em>b</em><u>c</u><s>d</s>")).toEqual([
      { tag: "i", children: ["a"] },
      { tag: "em", children: ["b"] },
      { tag: "u", children: ["c"] },
      { tag: "s", children: ["d"] },
    ]);
    expect(parseTelegramHtml("<code>1+1</code>")).toEqual([{ tag: "code", children: ["1+1"] }]);
    expect(parseTelegramHtml("<pre>x</pre>")).toEqual([{ tag: "pre", children: ["x"] }]);
  });

  it("ссылка: только http/https", () => {
    expect(parseTelegramHtml('<a href="https://t.me/bot">бот</a>')).toEqual([
      { tag: "a", href: "https://t.me/bot", children: ["бот"] },
    ]);
    expect(parseTelegramHtml('<a href="http://x.ru">x</a>')).toEqual([
      { tag: "a", href: "http://x.ru", children: ["x"] },
    ]);
  });

  it("javascript: в href выбрасывается, текст остаётся", () => {
    const nodes = parseTelegramHtml('<a href="javascript:alert(1)">жми</a>');
    expect(nodes).toEqual(["жми"]);
  });

  it("script и style выбрасываются целиком", () => {
    expect(parseTelegramHtml("<script>alert(1)</script>привет")).toEqual(["привет"]);
    expect(parseTelegramHtml("<style>b{}</style>ок")).toEqual(["ок"]);
  });

  it("чужой тег снимается, содержимое остаётся", () => {
    expect(parseTelegramHtml("<table><td>клетка</td></table>")).toEqual(["клетка"]);
    expect(parseTelegramHtml("a<unknown>b</unknown>c")).toEqual(["a", "b", "c"]);
  });

  it("перенос строки становится <br>", () => {
    expect(parseTelegramHtml("первая\nвторая")).toEqual(["первая", { tag: "br", children: [] }, "вторая"]);
  });

  it("сущности раскрываются в текст", () => {
    expect(parseTelegramHtml("&lt;b&gt;не жирный&lt;/b&gt;")).toEqual(["<b>не жирный</b>"]);
    expect(parseTelegramHtml("А&amp;Б")).toEqual(["А&Б"]);
  });

  it("вложенность и смешение", () => {
    expect(parseTelegramHtml("<b>жирный <i>и курсив</i></b> хвост")).toEqual([
      { tag: "b", children: ["жирный ", { tag: "i", children: ["и курсив"] }] },
      " хвост",
    ]);
  });
});

describe("renderTelegramHtml: рендер в DOM", () => {
  it("рисует разрешённые теги", () => {
    const { container } = render(<div>{renderTelegramHtml("<b>a</b> и <code>c</code>")}</div>);
    expect(container.querySelector("b")?.textContent).toBe("a");
    expect(container.querySelector("code")?.textContent).toBe("c");
  });

  it("script не попадает в DOM", () => {
    const { container } = render(<div>{renderTelegramHtml("<script>alert(1)</script>текст")}</div>);
    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toBe("текст");
  });

  it("onerror не попадает в DOM", () => {
    const { container } = render(
      <div>{renderTelegramHtml('<img src=x onerror=alert(1)>после картинки')}</div>,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("[onerror]")).toBeNull();
    expect(container.textContent).toContain("после картинки");
  });

  it("ссылка с javascript: рисуется без href", () => {
    const { container } = render(
      <div>{renderTelegramHtml('<a href="javascript:alert(1)">жми</a>')}</div>,
    );
    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toContain("жми");
  });

  it("обычная ссылка получает href", () => {
    const { container } = render(<div>{renderTelegramHtml('<a href="https://t.me">бот</a>')}</div>);
    const link = container.querySelector("a");
    expect(link?.getAttribute("href")).toBe("https://t.me");
  });

  it("перенос строки рисуется как br", () => {
    const { container } = render(<div>{renderTelegramHtml("раз\nдва")}</div>);
    expect(container.querySelectorAll("br").length).toBe(1);
  });
});
