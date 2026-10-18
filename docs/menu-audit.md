# Hermes Telegram Control — аудит (Фаза A)

Дата: 2026-10-18. Hermes build: установленный локально в `~/.hermes/hermes-agent`
(venv `/home/qwertyonek/.hermes/installs/488de35190ed1444/...`, python-telegram-bot 22.8).

Это честная инвентаризация того, что публичный Plugin API реально позволяет,
проверенная чтением исходников Hermes (не документации в отрыве от кода) и
живыми экспериментами на запущенном gateway. Выводы ниже определяют, что
Фаза B–D реализуют как настоящую функцию, и что помечено как архитектурно
недостижимое без изменения Hermes core.

## 1. Как Hermes даёт плагину встроиться в Telegram

### 1.1 `ctx.register_telegram_handler(factory)`
`factory(native, adapter)` вызывается при `connect()` и при повторном wiring
после позднего enable. `native` — живой `telegram.ext.Application` (PTB).
Внутри фабрики можно добавлять `CommandHandler`, `CallbackQueryHandler`,
`MessageHandler` напрямую.

**Порядок диспетчеризации подтверждён в коде**
(`gateway/platforms/base.py::_wire_plugin_handlers`,
`plugins/platforms/telegram/adapter.py::_wire_plugin_handlers`): core
регистрирует свои catch-all хендлеры (`CommandHandler` на `filters.COMMAND`,
один `CallbackQueryHandler` без паттерна) в `_register_handlers()`, затем
плагинные фабрики запускаются, и специально написанный код **переставляет
только что добавленные плагином хендлеры перед первым core-хендлером той же
группы** (комментарий в коде: "a plugin handler appended after connect would
never fire... Move whatever a late factory added ahead of the first core
handler of its group"). Для позднего `enable` в рантайме это тоже работает —
протестировано: `hermes plugins enable` → `hermes gateway restart` →
`journalctl` не показывает ошибок регистрации, плагинные команды (`/menu`,
`/qr`) реально отвечают раньше, чем core успел бы перехватить `/menu` как
неизвестную команду.

**Вывод:** наш `CallbackQueryHandler(on_callback, pattern="^qr:")` гарантированно
видит свои callback-и первым, PTB вызывает только первый матчащий handler в
группе (`group=0` по умолчанию у всех — core и плагин), и наш `pattern=`
гарантирует, что мы не поглощаем чужие callback-и (core, другие плагины).

### 1.2 `ctx.inject_message(content, role, origin=...)` — НЕ годится для команд
Прочитано в `gateway/run_plugin_injection.py` и `gateway/platforms/event.py`:
каждое инжектированное через этот API сообщение получает
`allow_gateway_control=False`, а `MessageEvent.get_command()` возвращает
`None`, если `allow_gateway_control` ложно — **независимо от текста**. Это
проверено юнит-тестом ядра (`tests/gateway/test_plugin_message_injection.py`:
`assert queued.allow_gateway_control is False` и `assert event.get_command()
is None`). Живой тест на моём gateway подтвердил то же самое: кнопка,
инжектирующая `/status`, отправляла текст в LLM, а не в command dispatcher
(бот ответил "`/status` is a built-in gateway command, not my tool...").

**Вывод:** `inject_message` принципиально не может «нажать» slash-команду —
это осознанный security boundary (плагин не должен управлять control-plane
от имени пользователя программно), не недостающая фича. Единственный честный
способ — Telegram `ReplyKeyboardMarkup`, где кнопка **отправляет свой текст
как настоящее сообщение пользователя**. Выбрано как основной механизм
выполнения любой команды в этом плагине.

### 1.3 `ctx.register_command(name, handler, ...)`
Регистрирует `/name` как in-session slash-команду. **Отклоняет** регистрацию,
если имя конфликтует с built-in командой (проверено: `/s` отклонён, т.к. это
алиас `/steer`; залогирован `WARNING`, плагин продолжает грузиться). Рабочие
команды плагина — `/menu`, `/qr` (без конфликта).

## 2. Чтение реального состояния (toggles, списки)

ТЗ п.10 требует: "состояния переключателей отображаются по фактическим
данным; не угадывай". Проверено, что реально читаемо:

| Данные | Доступны ли плагину | Как |
|---|---|---|
| Список именованных сессий (для `/resume`) | ✅ Да | `hermes sessions list --source telegram` (публичный CLI, read-only), спарсено в `sessions.py` |
| `approvals.mode` (глобальный, персистентный в `config.yaml`) | ✅ Да | `hermes config get approvals.mode` — проверено живьём, вернул `off` |
| `display.busy_input_mode` | ✅ Да | то же самое, читается из `config.yaml` |
| YOLO-режим (per-session) | ❌ Нет | персистится в SQLite routing entry (`session_store.set_session_yolo`), не в `config.yaml`; нет публичного CLI/tool-геттера |
| Voice mode / footer toggle | ⚠️ Частично | `voice.auto_tts` — глобальный конфиг-ключ, читаем через `hermes config get`; НО `/voice` слэш-команда может переключать per-session override, который `config get` не видит |
| Текущая модель сессии | ❌ Нет надёжного способа | `hermes model` без аргументов — интерактивный визард (OAuth/picker UI), не read-only CLI; текущая модель сессии — внутреннее состояние `AIAgent`, не выставлено наружу плагинам |
| Список доступных моделей | ❌ Нет | то же — только через интерактивный `hermes model`, нет API `list_models()` плагину |
| Pending approval requests (для `/approve`/`/deny`) | ❌ Нет | `pre_approval_request`/`post_approval_response` хуки — **observer-only**, возвращаемое значение игнорируется; нет способа ни прочитать текущий pending request ID, ни ответить на него программно из плагина |
| Active agents / background tasks (`/agents`) | ❌ Нет публичного листинга | внутреннее состояние gateway runner, не экспортировано |
| Kanban tasks | ⚠️ Частично | `kanban_*` tools существуют и теоретически доступны через `ctx.dispatch_tool`, но это требует активной Kanban-доски и профильного контекста; не протестировано в рамках этого аудита (нет настроенной доски) |

**Следствие для UX-контракта:** честно показывать 🟢/⚪/❔ возможно только
для `approvals.mode` и аналогичных **персистентных конфиг-ключей**. Для
YOLO, voice override, текущей модели и approve/deny queue единственный
правдивый вариант — **не изображать статус**, а дать кнопку, которая
отправляет саму slash-команду без аргументов (большинство из них без
аргумента показывают текущее состояние как часть ответа — например `/busy`
без аргумента возвращает текущий режим текстом). Это соответствует правилу
10 ("не угадывай") буквально: лучше не показать индикатор, чем показать
неверный.

## 3. `/approve` и `/deny` — архитектурно недостижимы как кнопки меню

ТЗ требует отдельные действия для approve/deny с привязкой к конкретному
pending request ID. Проверено: `pre_approval_request` / `post_approval_response`
хуки в `hermes_cli/plugins.py::VALID_HOOKS` — **observers**, их возвращаемые
значения игнорируются (документация `hooks.md`: "Approval observers
(returns ignored; veto via pre_tool_call)"). Нет публичного API, который бы
отдавал плагину список pending approval requests с их ID, и нет публичного
способа ответить на конкретный запрос программно (минуя `/approve`/`/deny`
текстом).

**Вывод:** `/approve` и `/deny` в этом плагине реализованы как
**reply-keyboard кнопки без аргумента** — тап отправляет голый `/approve`
или `/deny`, что воспроизводит штатное поведение (Hermes сам резолвит
последний pending request для этого чата, как было и до плагина). Полноценная
привязка к конкретному request ID из меню потребовала бы нового публичного
hook в Hermes core — зафиксировано как `НЕВОЗМОЖНО В ТЕКУЩЕЙ ВЕРСИИ`,
предложение подать issue see §7.

## 4. Удаление команд из стандартного Telegram `/`-меню

Подтверждено в коде (`plugins/platforms/telegram/adapter.py::_register_command_menu`,
документация `user-guide/messaging/telegram.md` §"Command menu priority and
cap"): Hermes вызывает `set_my_commands()` **само, при каждом connect**, с
списком, построенным из `telegram_menu_commands()` — построено из core
registry + priority config. Плагин **не может** просто вызвать
`delete_my_commands()` один раз — Hermes пере-регистрирует список при
следующем reconnect/restart, что оверрайдит любое ручное удаление плагином
(гонка состояний: "устранить источник повторной регистрации, а не только
однократно удалить список", как и требует ТЗ §6).

**Честное решение — официальный конфиг-механизм**, НЕ патч плагина:

```yaml
platforms:
  telegram:
    extra:
      command_menu:
        max_commands: 2
        priority_mode: replace
        priority:
          - menu
          - help
```

Это заставляет `telegram_menu_commands()` (вызываемую самим ядром при каждом
connect) отдавать только `/menu` и `/help` в `set_my_commands()`. Остальные
68 команд **продолжают диспетчеризоваться штатно** — это только видимость в
автокомплите `/`, согласно документации: "the command's handler stays
dispatchable when typed" — команда просто не висит в подсказке. Протестировано
живьём (см. §6 отчёта о тестах).

**Полное исчезновение системной кнопки Telegram "Menu"** (синей, слева от
поля ввода) — не предлагается и не обещается: это нативный Telegram UI
элемент (`setChatMenuButton`), он **всегда** показывает список команд
бота, если команды зарегистрированы. С `max_commands: 2` список будет
коротким (2 позиции), но сама кнопка меню исчезнуть не может, пока у бота
есть хоть одна зарегистрированная команда — убирать её незачем и вредно
(юзер потеряет автокомплит `/help`).

## 5. Навигационная модель (реализуемость в рамках Telegram API)

- Inline-кнопки (`InlineKeyboardMarkup`) используются ИСКЛЮЧИТЕЛЬНО для
  навигации (экран ↔ экран), никогда для выполнения команд (см. §1.2). Тап
  вызывает `query.edit_message_text(...)` на том же message_id — панель не
  плодит новые сообщения при навигации "вперёд/назад".
- Реальное выполнение команды — ReplyKeyboardMarkup (новое сообщение
  "Нажмите кнопку 👇" с клавиатурой под полем ввода), потому что
  `ReplyKeyboardMarkup` физически не может быть `reply_markup` при
  `edit_message_text` (Telegram Bot API ограничение — reply keyboards
  прикрепляются только к НОВЫМ сообщениям, inline keyboards — к любым).
  Это объясняет двухуровневую архитектуру: категория = инлайн-навигация,
  "выполнить команду" = отдельное сообщение с реальной клавиатурой.
- `NavigationStack`/`PanelInstance` по ТЗ §5: реализовано как **callback_data
  кодирует весь маршрут** (`qr:cat:3`, `qr:home`), без серверного state —
  Telegram callback_data (64 байт) достаточно для кодирования `screen_id` +
  малых параметров (индекс категории, номер страницы). Для `MenuRoute` с
  параметрами страницы/фильтра этого достаточно; для `InteractionFlow`
  (мастеров с вводом текста) состояние должно жить в plugin state
  (`ctx.state`), см. Фазу C.

## 6. Что проверено живьём на этом этапе (аудит), что — только чтением кода

**Живой gateway (`hermes-gateway.service`, systemd user unit):**
- ✅ Плагин грузится, `hermes plugins doctor . --ci` и `hermes plugins
  validate . --install-deps` проходят зелёным.
- ✅ `/menu`, `/qr` реально отвечают в Telegram (видел скриншоты пользователя).
- ✅ `inject_message` подтверждённо НЕ исполняет slash-команды (видел
  реальный ответ бота "/status is a built-in gateway command, not my tool").
- ✅ `hermes config get approvals.mode` возвращает реальное значение (`off`).
- ✅ `hermes sessions list --source telegram` — реальный вывод, распарсен
  и подтверждён корректным (включая кириллицу, длинные названия).
- ✅ Переименование сессии через `hermes sessions rename` и повторный список
  — подтверждена корректная фильтрация безымянных сессий.

**Только чтение исходников (не исполнено на живом инстансе в рамках этого
аудита — отдельно отмечено в Фазе E, что требует реального теста):**
- `command_menu.priority_mode: replace` — поведение подтверждено кодом
  (`_telegram_command_menu_config`, `_prioritize_telegram_menu_candidates`),
  но изменение конфига и визуальная проверка в Telegram будет сделана в
  Фазе D и подтверждена в финальном отчёте.
- `pre_approval_request`/`post_approval_response` observer-only — подтверждено
  чтением `VALID_HOOKS` и `hooks.md`, не воспроизведено живым pending-request
  сценарием (требует реальной опасной команды в полёте).
- `_wire_plugin_handlers` hoisting — подтверждено чтением кода обеих версий
  (`gateway/platforms/base.py` и адаптера), и косвенно подтверждено тем,
  что `/menu`'s inline callback реально срабатывает (если бы hoisting не
  работал, core перехватывал бы весь callback traffic первым).

## 7. Предложение для Hermes core (не блокирует эту реализацию)

Чтобы `/approve`/`/deny` и статус-переключатели (YOLO, текущая модель) стали
по-настоящему управляемыми из плагинного UI, Hermes нужен один из:
1. Публичный read-only API: `ctx.dispatch_tool`-совместимый tool или
   `ctx`-метод, возвращающий текущие pending approval requests с ID +
   описанием команды (без возможности их одобрить программно — только
   чтение, чтобы кнопка могла показать "Подтвердить запуск `rm -rf...`?" с
   точным текстом).
2. Публичный геттер текущей модели сессии и короткого списка доступных
   моделей (не весь интерактивный визард `hermes model`).
3. Публичный геттер per-session YOLO/voice override state.

Это зафиксировано как `НЕВОЗМОЖНО БЕЗ ИЗМЕНЕНИЯ HERMES CORE`, предложение
подать как issue в `NousResearch/hermes-agent`, не реализуется патчем этого
плагина (запрещено правилом "No core override" каталога и п.0 этого ТЗ:
"не меняй сам Hermes Core").

## 8. Выводы для Фазы B–D

1. Используем **ReplyKeyboardMarkup для любого реального выполнения
   команды** (session resume, toggle, system action) — это единственный
   путь, не нарушающий security boundary.
2. Используем **InlineKeyboardMarkup только для навигации** между экранами
   меню (категории, страницы списков) — редактируем то же сообщение.
3. `/approve`, `/deny` — кнопки без аргумента (резолвят последний pending
   request штатно, как и раньше); честно не обещаем привязку к конкретному
   ID в описании кнопки.
4. Toggle-статусы показываем 🟢/⚪ **только** для `approvals.mode` и других
   подтверждённо читаемых `config.yaml` ключей; для остального — просто
   кнопка без статус-индикатора (с текстом действия, не "состояния").
5. Список моделей/активных агентов/kanban — кнопка отправляет голую команду
   без параметров; Hermes сам покажет список/picker в ответ (как было бы,
   если юзер написал команду руками) — это НЕ фиктивная заглушка, это
   честная передача управления штатному обработчику Hermes.
6. Уменьшаем стандартное Telegram `/`-меню до `/menu` + `/help` через
   `platforms.telegram.extra.command_menu` (официальный конфиг), с явной
   инструкцией пользователю добавить это в свой `config.yaml` (плагин не
   может менять чужой `config.yaml` в общем профиле без явного запроса —
   это пользовательская настройка, не плагинный файл).
