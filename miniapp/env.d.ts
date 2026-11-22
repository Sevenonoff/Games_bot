// Минимальное окружение Node для конфигов без @types/node (в списке зависимостей ТЗ его нет).
declare const process: { env: Record<string, string | undefined> };
