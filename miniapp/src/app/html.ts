// Безопасный рендер HTML-подмножества Telegram из текста экрана.
// Разрешены b, strong, i, em, u, s, code, pre, a[href] и переносы строк.
// Разбор — DOMParser (скрипты в разобранном документе не исполняются), затем дерево
// SafeNode и рендер элементами Preact: innerHTML с непроверенной строкой не используется.
import { h } from "preact";
import type { ComponentChild } from "preact";

type AllowedTag = "b" | "strong" | "i" | "em" | "u" | "s" | "code" | "pre" | "a" | "br";

/** Узел безопасного дерева: строка или разрешённый тег (у ссылки — только http/https). */
export type SafeNode = string | { tag: AllowedTag; href?: string; children: SafeNode[] };

const ALLOWED = new Set(["b", "strong", "i", "em", "u", "s", "code", "pre", "a"]);
/** Содержимое этих тегов не показывается вовсе. */
const DROPPED = new Set(["script", "style"]);

export function parseTelegramHtml(text: string): SafeNode[] {
  const doc = new DOMParser().parseFromString(text, "text/html");
  return parseNodes(doc.body.childNodes);
}

function parseNodes(list: NodeList): SafeNode[] {
  const out: SafeNode[] = [];
  for (const node of Array.from(list)) {
    if (node.nodeType === Node.TEXT_NODE) out.push(...withBreaks(node.textContent ?? ""));
    else if (node.nodeType === Node.ELEMENT_NODE) out.push(...parseElement(node as Element));
  }
  return out;
}

function parseElement(el: Element): SafeNode[] {
  const tag = el.tagName.toLowerCase();
  if (DROPPED.has(tag)) return [];                       // script/style — целиком прочь
  if (!ALLOWED.has(tag)) return parseNodes(el.childNodes); // прочий тег снять, текст оставить
  if (tag === "a") {
    const href = el.getAttribute("href") ?? "";
    if (!/^https?:/i.test(href)) return parseNodes(el.childNodes);  // javascript: и прочее — без ссылки
    return [{ tag: "a", href, children: parseNodes(el.childNodes) }];
  }
  return [{ tag: tag as AllowedTag, children: parseNodes(el.childNodes) }];
}

/** Перенос строки в тексте → <br/> (так форматирует тексты ядро). */
function withBreaks(text: string): SafeNode[] {
  const out: SafeNode[] = [];
  text.split("\n").forEach((part, i) => {
    if (i > 0) out.push({ tag: "br", children: [] });
    if (part) out.push(part);
  });
  return out;
}

/** Дерево SafeNode → дети Preact. */
export function renderTelegramHtml(text: string): ComponentChild[] {
  return parseTelegramHtml(text).map(toChild);
}

function toChildren(nodes: SafeNode[]): ComponentChild[] {
  return nodes.map(toChild);
}

function toChild(node: SafeNode): ComponentChild {
  if (typeof node === "string") return node;
  if (node.tag === "a") {
    return h("a", { href: node.href, target: "_blank", rel: "noopener noreferrer" }, toChildren(node.children));
  }
  return h(node.tag, {}, toChildren(node.children));
}
