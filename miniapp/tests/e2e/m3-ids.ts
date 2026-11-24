// Раскладка id e2e-игроков (tz-m3 §7.3, приёмка M3-1 п. 2): пересечений между тестами
// нет, в том числе при --repeat-each=2 и параллельных проектах.
//
// Игроки (200–299): id = 200 + 8·k + 2·проект + повтор (0/1)
//   k=0 memo-full      k=1 memo-mismatch   k=2 memo-leak
//   k=3 matrix-error   k=4 tower-full      k=5 tower-error   k=6 path-full
//   max: 200 + 48 + 6 + 1 = 255
// Админы (300–399): id = 300 + 14·a + 4·проект + повтор (0/1)
//   a=0 memo-big      a=1 matrix-full   a=2 matrix-big
//   a=3 tower-big     a=4 path-error    a=5 path-big      a=6 path-size
//   max: 300 + 84 + 12 + 1 = 397
// DEV_ADMINS в playwright.config покрывает 300–399.

export function playerId(k: number, projectIndex: number, repeat = 0): number {
  return 200 + 8 * k + 2 * projectIndex + repeat;
}

export function adminId(a: number, projectIndex: number, repeat = 0): number {
  return 300 + 14 * a + 4 * projectIndex + repeat;
}
