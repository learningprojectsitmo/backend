---
marp: true
theme: default
paginate: true
size: 16:9
header: "EduFlow · Акселератор 2026"
footer: "Отборочный питчинг"
---

<!--
Экспорт из backend/ (--allow-local-files нужен, чтобы вставить логотип из frontend/public):
  npx -y @marp-team/marp-cli --allow-local-files docs/pitch/eduflow-pitch.md -o eduflow-pitch.pdf
  npx -y @marp-team/marp-cli --allow-local-files docs/pitch/eduflow-pitch.md -o eduflow-pitch.pptx
  npx -y @marp-team/marp-cli -s docs/pitch            # живой предпросмотр
Плейсхолдеры помечены […] — заменить перед выступлением.
Тайминг: слайды 1–12 = 3 минуты. Всё после «Приложение» — только для Q&A, не показывать.
-->

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
  --app-background: #f7f7f8;
  --app-surface: #ffffff;
  --app-border: #e5e7eb;
  --app-border-light: #ececf1;
  --app-text: #111827;
  --app-muted: #6b7280;
  --app-primary: #0f172a;
  --app-blue: #2563eb;
  --app-ghost: #f3f4f6;
  --badge-blue-bg: #eef2ff;
  --badge-blue-fg: #4f46e5;
  --badge-amber-bg: #fef3c7;
  --badge-amber-fg: #92400e;
  --status-inprogress-bg: #dbeafe;
  --status-inprogress-text: #2563eb;
  --status-review-bg: #fef3c7;
  --status-review-text: #d97706;
  --status-completed-bg: #dcfce7;
  --status-completed-text: #16a34a;
  --status-planned-bg: #e5e7eb;
  --status-planned-text: #6b7280;
}

section {
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  color: var(--app-text);
  background: var(--app-background);
  padding: 44px 56px;
  font-size: 18px;
  line-height: 1.5;
  letter-spacing: 0;
}

section::after { color: var(--app-muted); font-size: 12px; }
header, footer { font-size: 12px; color: var(--app-muted); letter-spacing: 0; }

h1 { color: var(--app-primary); font-weight: 700; font-size: 46px; line-height: 1.2; letter-spacing: -0.02em; margin: 0 0 8px; }
h2 { color: var(--app-primary); font-weight: 700; font-size: 34px; line-height: 1.25; letter-spacing: -0.01em; margin: 0 0 16px; }
h3 { color: var(--app-text); font-weight: 600; font-size: 20px; margin: 0 0 4px; }
strong { color: var(--app-primary); font-weight: 600; }
em { color: var(--app-muted); font-style: normal; }
a { color: var(--app-blue); text-decoration: none; }

.lead { color: var(--app-muted); font-size: 24px; }
.badge {
  display: inline-block; background: var(--badge-blue-bg); color: var(--badge-blue-fg);
  border-radius: 8px; padding: 4px 12px; font-size: 14px; font-weight: 500;
}
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.card {
  background: var(--app-surface); border: 1px solid var(--app-border); border-radius: 12px;
  padding: 18px 20px;
}
.card h3 { margin-top: 0; }
.problem { border-left: 3px solid var(--status-review-text); }
.solution { border-left: 3px solid var(--app-blue); }
table { width: 100%; border-collapse: collapse; font-size: 16px; }
th, td { border-bottom: 1px solid var(--app-border); padding: 8px 12px; text-align: left; }
th { color: var(--app-muted); font-weight: 500; }
.yes { color: var(--status-completed-text); font-weight: 600; }
.no { color: var(--app-muted); }
.fill { background: var(--badge-amber-bg); border-radius: 6px; padding: 1px 8px; color: var(--badge-amber-fg); font-weight: 600; }
.center { text-align: center; }
.sub { color: var(--app-muted); font-size: 14px; }
.num { color: var(--app-blue); font-weight: 700; font-size: 28px; }
section.title { background: var(--app-surface); }
section.title h1 { font-size: 56px; }
section.title::before {
  content: ""; display: block; height: 6px; background: var(--app-primary);
  position: absolute; top: 0; left: 0; right: 0;
}
</style>

<!-- _paginate: false -->
<!-- _header: "" -->
<!-- _footer: "" -->
<!--
[0:00–0:10] Открытие. Один слайд-визитка.
-->

# **EduFlow**

### Двадцать проектов. Один список.

<span class="badge">Отборочный питчинг · Акселератор</span>

![w:200](../../../frontend/public/eduflow.PNG)

**Команда ИТМО** · Афанасьев Антон · Карагулов Мансур
_Распределение людей по командам и управление совместными проектами_

---

<!--
[0:10–0:50] ПРОБЛЕМА. Не читать текст — рассказывать. Три боли, каждую одним предложением.
-->

## Проблема

<div class="grid3">
<div class="card problem">
<h3>Людей и команд — десятки</h3>
Чем больше студентов и команд, тем сложнее держать в голове, кто в какой команде, чем занят и на каком этапе.
</div>
<div class="card problem">
<h3>Распределение вручную</h3>
Подбирать людей в команды по навыкам, интересам и желаемым ролям приходится в таблицах и чатах — долго и субъективно.
</div>
<div class="card problem">
<h3>Всё разбросано</h3>
Резюме, отклики, приглашения, роли и статусы живут в переписке, а не в единой системе. Картины по всем командам нет.
</div>
</div>

**Чем больше людей и команд, тем дороже ошибка:** слабый состав, дубли ролей и сорванные сроки в масштабе целого потока.

---

<!--
[0:50–1:10] РЫНОК И ЦА. Показать сегменты, назвать first market. Цифры TAM/SAM/SOM — [заполнить].
-->

## Кому и какой рынок

| Сегмент | Боль |
|---|---|
| Учебные команды и вузы | распределение людей по командам, десятки проектов, оценивание |
| Продуктовые команды | доска, этапы и история решений вместо мессенджеров |
| Исследовательские группы | распределение ролей и общая картина по команде |
| Хакатоны и акселераторы | сборка команд, жюри, дедлайны и роли на событии |
| Руководители проектов | статус, состав и сроки нескольких команд одновременно |

**First market — ИТМО.** `[TAM/SAM/SOM — заполнить]`
_Сервис бесплатный на входе, данные хранятся в России._

---

<!--
[1:10–1:35] ПРОДУКТ. Показать экран. Заменить слоты на реальные скриншоты.
-->

## Продукт

Единый список **людей и команд**: этап, состав, прогресс и сроки с фильтрами по этапу, тегу, участнику и дате. Плюс **распределение по командам** — резюме, навыки и желаемые роли в одном месте.

<div class="grid">
<div>
<em>Слот: скриншот единого списка проектов и команд</em>

`[вставить: список команд с фильтрами]`
</div>
<div>
<em>Слот: скриншот распределения по командам</em>

`[вставить: резюме, навыки и желаемые роли]`
</div>
</div>

<span class="sub">Компоненты реальные: `project-list-mockup` и `kanban-mockup` с лендинга EduFlow; отклики, приглашения и роли на уровне проекта уже в продукте.</span>

---

<!--
[1:35–1:50] КАК ЭТО РАБОТАЕТ. 3 шага, быстро.
-->

## Как это работает

<div class="grid3">
<div class="card solution">
<h3>1. Пространство</h3>
Контейнер проектов по направлению: учебная команда или рабочая группа.
</div>
<div class="card solution">
<h3>2. Проекты и команда</h3>
Описать проект, задать тип с этапами, позвать участников и назначить роли.
</div>
<div class="card solution">
<h3>3. Доска</h3>
Задачи, подзадачи, приоритеты и WIP-лимиты. ТЗ и вики — рядом с проектом.
</div>
</div>

**Уже работает:** регистрация с подтверждением e-mail, профиль, резюме и портфолио, поиск людей по навыкам.

---

<!--
[1:50–2:10] ВОЗМОЖНОСТИ. Три колонки, не перечислять всё — назвать группы.
-->

## Возможности

<div class="grid3">
<div class="card">
<h3>Команда</h3>
Распределение по командам<br>
Поиск людей по навыкам и ролям<br>
Приглашения, отклики и резюме<br>
Роли и права на уровне проекта
</div>
<div class="card">
<h3>Работа</h3>
Канбан с перетаскиванием<br>
WIP-лимиты и приоритеты<br>
ТЗ с согласованием требований<br>
Вики проекта
</div>
<div class="card">
<h3>Контроль</h3>
Единый список с фильтрами<br>
Уведомления из всех проектов<br>
История изменений<br>
Аудит действий
</div>
</div>

---

<!--
[2:10–2:30] КОНКУРЕНТЫ. Таблица — читать по строкам «что важно для учёбы».
-->

## Чем отличаемся

| Критерий | EduFlow | Trello / Notion / Трекер | Moodle / Blackboard |
|---|---|---|---|
| Проектный учебный процесс | <span class="yes">Да</span> | <span class="no">Нет</span> | <span class="no">Частично</span> |
| Распределение людей по командам | <span class="yes">Да</span> | <span class="no">Нет</span> | <span class="no">Нет</span> |
| Роли и права на уровне проекта | <span class="yes">Да</span> | <span class="no">Базовые</span> | <span class="no">Курсовые</span> |
| Оценивание преподавателем | <span class="yes">В роадмапе</span> | <span class="no">Нет</span> | <span class="no">Да, тяжёлое</span> |
| Единый список + канбан + ТЗ + вики | <span class="yes">Да</span> | <span class="no">По частям</span> | <span class="no">Нет</span> |
| Данные в РФ | <span class="yes">Да</span> | <span class="no">Нет</span> | <span class="no">Зависит</span> |

_Мы — вертикальное решение под проектное обучение, а не универсальный таск-трекер._

---

<!--
[2:30–2:45] БИЗНЕС-МОДЕЛЬ. Подписка + B2B. Назвать цены — [заполнить].
-->

## Бизнес-модель

<div class="grid">
<div class="card">
<h3>Подписка (B2C)</h3>
Команды и руководители платят за расширенные лимиты и возможности.

Цена: <span class="fill">[мес/год — заполнить]</span>
</div>
<div class="card">
<h3>B2B-лицензии</h3>
Вузы, организации хакатонов и акселераторов — за места и администрирование.

Цена: <span class="fill">[вуз / событие — заполнить]</span>
</div>
</div>

**Воронка:** бесплатный вход → активная команда → подписка / B2B.
Целевые метрики: <span class="fill">[вузы, студенты, MRR — заполнить]</span>

---

<!--
[2:45–2:55] СТАТУС. Подчеркнуть: продукт не идея, а работающий сервис.
-->

## Что уже сделано

<div class="grid">
<div>
**Продукт**

- Регистрация с подтверждением e-mail, сброс пароля
- Профиль: резюме, портфолио, образование, языки, график активности
- Распределение: резюме и навыки, отклики, вакансии, приглашения по ссылке
- Пространства: категории, статусы, настройки, типы проектов
- Проекты: этапы, ТЗ с критериями приёмки, канбан, вики, уведомления
</div>
<div>
**Платформа**

- Backend: FastAPI + SQLAlchemy, слои api → services → repository
- Frontend: React 18 + TypeScript + Vite
- PostgreSQL, Alembic-миграции, Docker-деплой
- Роли и права: 4 роли, 52 права, авторство
- Мониторинг: Prometheus + Grafana, CI, тесты

Тракшн: <span class="fill">[пилоты, пользователи, факультеты — заполнить]</span>
</div>
</div>

---

<!--
[2:55–3:05] РОАДМАП. Быстро, по пунктам.
-->

## Роадмап развития

1. **Багфиксы и стабильность** — довести сценарии до прод-качества
2. **Распределение по командам** — подбор людей по навыкам и ролям, автораспределение по проектам
3. **Открытые пространства** — доделать `join_policy`, публичный каталог
4. **Доработка БД** — производительность и целостность
5. **Управление пространствами** — расширенные настройки и модерация
6. **Система оценивания проекта** — от критериев приёмки в ТЗ к оценке преподавателя
7. **Интеграции** — GitHub и ITMO ID

---

<!--
[3:05–3:15] КОМАНДА. Назвать роли. Заполнить имена.
-->

## Команда

Команда ИТМО — продукт, разработка и дизайн в одном составе.

| Участник | Роль |
|---|---|
| Афанасьев Антон | Лид, продукт, backend |
| Карагулов Мансур | `[роль — заполнить]` |
| <span class="fill">[ФИО]</span> | <span class="fill">[роль]</span> |

Ядро по истории репозитория: Афанасьев Антон, Карагулов Мансур, Nurgunpopov, LearnBeFree, bLamixs, Никита Терещенко, FedorS, Данила Москалец, Raman.

---

<!--
[3:15–3:20] ЦЕЛЬ НА АКСЕЛЕРАТОР. Одно конкретное предложение. Заполнить.
-->

## Цель на Акселератор

<span class="fill">[Что конкретно хотите получить: пилоты в N дисциплинах ИТМО, X активных студентов, валидация B2B-модели с вузами, менторы, инвестиции — заполнить]</span>

<div class="center" style="margin-top:48px">

# Вместо двадцати вкладок — один список

**Спасибо! Вопросы?**
Афанасьев Антон · orderkworinaa@gmail.com · Карагулов Мансур · mrkaragulov@itmo.ru

</div>

---
<!--
=== ПРИЛОЖЕНИЕ ДЛЯ Q&A — НЕ ПОКАЗЫВАТЬ В 3 МИНУТАХ ===
-->

<!-- _header: "Приложение · Q&A" -->

## Приложение: архитектура

<div class="grid3">
<div class="card">
<h3>Backend</h3>
FastAPI, Python 3.14+, слои<br>
api → services → repository<br>
SQLAlchemy (async), Alembic
</div>
<div class="card">
<h3>Frontend</h3>
React 18 + TypeScript<br>
Vite, TanStack Query, Axios<br>
Tailwind + shadcn/ui
</div>
<div class="card">
<h3>Инфраструктура</h3>
PostgreSQL 15, Docker<br>
Nginx edge, CI/CD<br>
Prometheus + Grafana
</div>
</div>

Модули: аутентификация, профиль/резюме, пространства, проекты, канбан, ТЗ, вики, идеи, уведомления, аудит, админ-панель, лендинг (ru/en).

---

<!-- _header: "Приложение · Q&A" -->

## Приложение: роли и права

Три независимых слоя доступа:

1. **Глобальная роль** — `admin` / `teacher` / `manager` / `member`, 52 права.
2. **Роль в пространстве** — назначается ссылкой-приглашением или вручную.
3. **Права создателя** — «кто создал, тот владелец», поверх ролей.

Права выдаются декларативно (`permission_required("entity:action")`) — не в коде обработчиков. `/admin/*` — только глобальный админ.

---

<!-- _header: "Приложение · Q&A" -->

## Приложение: безопасность и данные

- Данные хранятся на сервере в России.
- JWT-сессии, сброс пароля по одноразовому токену, подтверждение e-mail.
- Аудит действий пользователей и история изменений задач.
- Разграничение доступа: роль + владелец объекта.

---

<!-- _header: "Приложение · Q&A" -->

## Приложение: заготовки ответов

| Вопрос трекера | Ответ |
|---|---|
| Почему не Notion/Trello? | Они универсальны; у нас учебный процесс, роли и оценивание из коробки |
| Как зарабатываете? | Подписка команд + B2B-лицензии вузам, хакатонам, акселераторам |
| Что с данными и 152-ФЗ? | Хостинг в РФ, аудит действий, разграничение доступа |
| Кто платит — студент или вуз? | Обе модели: B2C-подписка и B2B-лицензия на организацию |
| Почему вы? | Работающий продукт на ИТМО + понимание процесса изнутри |
| Рынок? | `[TAM/SAM/SOM]` |
| Что за 3 месяца? | Багфиксы, открытые пространства, БД, управление пространствами, оценивание |
