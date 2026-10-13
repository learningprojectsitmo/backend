---
marp: true
theme: default
paginate: true
size: 16:9
header: "EduFlow · Акселератор 2026"
footer: "Отборочный питчинг"
# Экспорт из backend/ (--allow-local-files нужен, чтобы вставить логотип из frontend/public):
#   npx -y @marp-team/marp-cli --allow-local-files docs/pitch/eduflow-pitch.md -o eduflow-pitch.pdf
#   npx -y @marp-team/marp-cli --allow-local-files docs/pitch/eduflow-pitch.md -o eduflow-pitch.pptx
#   npx -y @marp-team/marp-cli -s docs/pitch            # живой предпросмотр
# Дизайн слайдов повторяет UI сайта (frontend/src/index.css, ProjectCard, KanbanTask,
# column-styles, Button). Продуктовые экраны — реальные скриншоты docs/images/features/.
# Оценочные цифры помечены «оценка (уточнить)» — заменить на реальные перед выступлением.
# Тайминг: слайды 1–16 = 3 минуты. Всё после «Приложение» — только для Q&A, не показывать.
# Текст слайдов озвучивания — в комментариях-заметках (презентерские заметки в .pptx).
---

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* ============ Дизайн-токены (light) из frontend/src/index.css ============ */
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
  --gray-50: #f9fafb;
  --gray-100: #f3f4f6;
  --gray-200: #e5e7eb;
  --gray-300: #d1d5db;
  --gray-400: #9ca3af;
  --gray-500: #6b7280;
  --gray-600: #4b5563;
  --gray-900: #111827;
  --badge-blue-bg: #eef2ff;
  --badge-blue-fg: #4f46e5;
  --badge-amber-bg: #fef3c7;
  --badge-amber-fg: #92400e;
  --status-inprogress-bg: #dbeafe;
  --status-inprogress-text: #2563eb;
  --status-review-bg: #fef3c7;
  --status-review-text: #d97706;
  --status-planned-bg: #e5e7eb;
  --status-planned-text: #6b7280;
  --status-completed-bg: #dcfce7;
  --status-completed-text: #16a34a;
  --btn-dark-bg: #030213;
  --btn-outline-border: #0000001a;
  --kanban-hl: hsl(218, 45%, 94%);
  --shadow-card: 0 1px 2px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.04);
  --shadow-window: 0 25px 50px -12px rgba(17, 24, 39, 0.08);
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
/* Фоновые пятна как на титуле — на всех слайдах:
   синее сверху-слева + зелёное снизу-справа у всех, третий акцент меняется */
section {
  background-repeat: no-repeat;
  background-image:
    radial-gradient(circle at 12% 8%, rgba(219, 234, 254, 0.8), rgba(219, 234, 254, 0) 60%),
    radial-gradient(circle at 90% 94%, rgba(220, 252, 231, 0.75), rgba(220, 252, 231, 0) 60%),
    radial-gradient(circle at 96% 6%, rgba(237, 233, 254, 0.6), rgba(237, 233, 254, 0) 55%);
  background-size: 56% 56%, 52% 52%, 44% 44%;
  background-position: 0 0, 100% 100%, 100% 0;
}
/* акцент варианта «амбер» — снизу-слева */
section[data-marpit-pagination="2"],
section[data-marpit-pagination="5"],
section[data-marpit-pagination="8"],
section[data-marpit-pagination="11"],
section[data-marpit-pagination="14"],
section[data-marpit-pagination="17"],
section[data-marpit-pagination="20"] {
  background-image:
    radial-gradient(circle at 12% 8%, rgba(219, 234, 254, 0.8), rgba(219, 234, 254, 0) 60%),
    radial-gradient(circle at 90% 94%, rgba(220, 252, 231, 0.75), rgba(220, 252, 231, 0) 60%),
    radial-gradient(circle at 8% 94%, rgba(254, 243, 199, 0.6), rgba(254, 243, 199, 0) 55%);
  background-size: 56% 56%, 52% 52%, 44% 44%;
  background-position: 0 0, 100% 100%, 0 100%;
}
/* акцент варианта «фиолетовое» — сверху по центру */
section[data-marpit-pagination="3"],
section[data-marpit-pagination="6"],
section[data-marpit-pagination="9"],
section[data-marpit-pagination="12"],
section[data-marpit-pagination="15"],
section[data-marpit-pagination="18"],
section[data-marpit-pagination="21"] {
  background-image:
    radial-gradient(circle at 12% 8%, rgba(219, 234, 254, 0.8), rgba(219, 234, 254, 0) 60%),
    radial-gradient(circle at 90% 94%, rgba(220, 252, 231, 0.75), rgba(220, 252, 231, 0) 60%),
    radial-gradient(circle at 50% 0%, rgba(237, 233, 254, 0.7), rgba(237, 233, 254, 0) 55%);
  background-size: 56% 56%, 52% 52%, 46% 46%;
  background-position: 0 0, 100% 100%, 50% 0;
}
section:not([data-marpit-pagination]) { background-image: none; }
section::after { color: var(--app-muted); font-size: 12px; }
header, footer { font-size: 12px; color: var(--app-muted); letter-spacing: 0; }

h1 { color: var(--gray-900); font-weight: 700; font-size: 46px; line-height: 1.2; letter-spacing: -0.02em; margin: 0 0 8px; }
h2 { color: var(--gray-900); font-weight: 700; font-size: 34px; line-height: 1.25; letter-spacing: -0.01em; margin: 0 0 16px; }
h3 { color: var(--gray-900); font-weight: 600; font-size: 20px; margin: 0 0 4px; }
strong { color: var(--gray-900); font-weight: 600; }
em { color: var(--app-muted); font-style: normal; }
a { color: var(--app-blue); text-decoration: none; }

.lead { color: var(--app-muted); font-size: 22px; }
.sub { color: var(--app-muted); font-size: 14px; }
.center { text-align: center; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 0 0 30px; }
.grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 0 0 30px; }

/* ============ UI-элементы сайта (light) ============ */

/* Карточка as in app: radius 20, мягкая тень, border gray-200 */
.ui-card {
  background: var(--app-surface); border: 1px solid var(--app-border);
  border-radius: 20px; box-shadow: var(--shadow-card); padding: 18px 20px;
}
.ui-card h3 { margin-top: 0; }
.ui-card ul { margin: 8px 0 0; padding: 0; list-style: none; font-size: 15px; color: var(--app-muted); }
.ui-card li { position: relative; padding: 3px 0 3px 14px; }
.ui-card li::before { content: ""; position: absolute; left: 0; top: 13px; width: 6px; height: 6px; border-radius: 999px; background: var(--app-blue); }

/* Бейдж-пилюля hero (как на лендинге) */
.pill-badge {
  display: inline-block; border: 1px solid var(--app-border); background: var(--app-surface);
  border-radius: 999px; padding: 5px 14px; font-size: 13px; font-weight: 500; color: var(--gray-600);
}

/* Кнопки as in app: variant dark / outline */
.ui-btn { display: inline-flex; align-items: center; justify-content: center; height: 44px; padding: 0 26px; border-radius: 12px; font-size: 16px; font-weight: 600; }
.ui-btn-dark { background: var(--btn-dark-bg); color: #fff; }
.ui-btn-outline { background: var(--app-surface); color: var(--gray-900); border: 1px solid var(--btn-outline-border); }

/* Статусные пилюли as in ProjectCard.statusStyles */
.pill { display: inline-flex; align-items: center; height: 22px; padding: 0 10px; border-radius: 999px; font-size: 12px; font-weight: 500; line-height: 1; }
.pill-planned { background: var(--status-planned-bg); color: var(--status-planned-text); }
.pill-inprogress { background: var(--status-inprogress-bg); color: var(--status-inprogress-text); }
.pill-review { background: var(--status-review-bg); color: var(--status-review-text); }
.pill-completed { background: var(--status-completed-bg); color: var(--status-completed-text); }

/* Жёлтая метка «оценка» — as in badge-amber app */
.fill { background: var(--badge-amber-bg); border-radius: 999px; padding: 1px 10px; color: var(--badge-amber-fg); font-weight: 600; font-size: 14px; }

/* Иконки инлайн, stroke как lucide */
.ico { display: inline-block; background-repeat: no-repeat; background-position: center;
  background-size: contain; vertical-align: -2px; flex-shrink: 0; }
.ico-search { background-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiM5Y2EzYWYiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48Y2lyY2xlIGN4PSIxMSIgY3k9IjExIiByPSI4Ii8+PGxpbmUgeDE9IjIxIiB5MT0iMjEiIHgyPSIxNi42NSIgeTI9IjE2LjY1Ii8+PC9zdmc+"); width: 11px; height: 11px; }
.ico-cal { background-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiM2YjcyODAiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cmVjdCB4PSIzIiB5PSI0IiB3aWR0aD0iMTgiIGhlaWdodD0iMTgiIHJ4PSIyIi8+PGxpbmUgeDE9IjE2IiB5MT0iMiIgeDI9IjE2IiB5Mj0iNiIvPjxsaW5lIHgxPSI4IiB5MT0iMiIgeDI9IjgiIHkyPSI2Ii8+PGxpbmUgeDE9IjMiIHkxPSIxMCIgeDI9IjIxIiB5Mj0iMTAiLz48L3N2Zz4="); width: 11px; height: 11px; }
.ico-users { background-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiM2YjcyODAiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cGF0aCBkPSJNMTYgMjF2LTJhNCA0IDAgMCAwLTQtNEg2YTQgNCAwIDAgMC00IDR2MiIvPjxjaXJjbGUgY3g9IjkiIGN5PSI3IiByPSI0Ii8+PHBhdGggZD0iTTIyIDIxdi0yYTQgNCAwIDAgMC0zLTMuODciLz48cGF0aCBkPSJNMTYgMy4xM2E0IDQgMCAwIDEgMCA3Ljc1Ii8+PC9zdmc+"); width: 12px; height: 12px; }
.ico-filter { background-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiM2YjcyODAiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cG9seWdvbiBwb2ludHM9IjIyIDMgMiAzIDEwIDEyLjQ2IDEwIDE5IDE0IDIxIDE0IDEyLjQ2IDIyIDMiLz48L3N2Zz4="); width: 11px; height: 11px; }

/* ============ Браузерное окно «Список проектов» ============ */
.ui-window { border-radius: 16px; border: 1px solid var(--app-border); background: var(--app-surface); box-shadow: var(--shadow-window); overflow: hidden; }
.win-bar { display: flex; align-items: center; gap: 10px; padding: 9px 14px; border-bottom: 1px solid var(--app-border); }
.win-dots { display: flex; gap: 5px; }
.win-dots i { width: 10px; height: 10px; border-radius: 50%; background: var(--gray-200); }
.win-search { flex: 1; display: flex; align-items: center; gap: 6px; background: var(--gray-50); border-radius: 8px; padding: 4px 10px; color: var(--gray-400); font-size: 11px; }
.win-filters { display: flex; align-items: center; gap: 6px; padding: 8px 14px; border-bottom: 1px solid var(--app-border); }
.chip { display: inline-flex; align-items: center; gap: 4px; border: 1px solid var(--app-border); border-radius: 999px; padding: 3px 10px; font-size: 11px; font-weight: 500; color: var(--gray-600); background: var(--app-surface); }
.win-count { margin-left: auto; color: var(--gray-400); font-size: 11px; }

/* Карточка проекта as in ProjectCard (компактно) */
.cards2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 12px; }
.p-card { display: flex; flex-direction: column; gap: 6px; background: var(--app-surface); border: 1px solid var(--app-border); border-radius: 16px; padding: 11px 13px; box-shadow: var(--shadow-card); }
.p-title { font-size: 14px; font-weight: 700; color: var(--gray-900); line-height: 1.25; }
.p-desc { font-size: 10.5px; color: var(--app-muted); line-height: 1.45; }
.p-prog { font-size: 10px; color: var(--gray-400); }
.p-bar { height: 6px; border-radius: 999px; background: var(--gray-200); overflow: hidden; }
.p-bar i { display: block; height: 100%; background: var(--gray-900); border-radius: 999px; }
.p-row { display: flex; align-items: center; gap: 5px; font-size: 10.5px; color: var(--gray-600); }
.p-foot { display: flex; align-items: center; justify-content: space-between; padding-top: 7px; margin-top: auto; border-top: 1px solid var(--gray-100); }
.p-users { display: inline-flex; align-items: center; gap: 4px; font-size: 10.5px; color: var(--gray-600); }
.avatars { display: flex; }
.avatar { width: 17px; height: 17px; border-radius: 50%; background: var(--gray-200); border: 2px solid #fff; display: inline-flex; align-items: center; justify-content: center; font-size: 8px; font-weight: 600; color: var(--gray-900); margin-left: -5px; }
.avatar:first-child { margin-left: 0; }
.avatarcount { width: 17px; height: 17px; border-radius: 50%; background: var(--gray-200); border: 2px solid #fff; display: inline-flex; align-items: center; justify-content: center; font-size: 8px; font-weight: 600; color: var(--gray-500); margin-left: -5px; }

/* ============ Окно «Канбан» ============ */
.board { border-radius: 16px; border: 1px solid var(--app-border); background: var(--app-surface); box-shadow: var(--shadow-window); overflow: hidden; }
.board-head { display: flex; align-items: center; justify-content: space-between; padding: 9px 14px; border-bottom: 1px solid var(--app-border); font-size: 11px; font-weight: 600; color: var(--gray-900); }
.board-top { color: var(--gray-400); font-weight: 400; }
.board-filter { display: inline-flex; align-items: center; gap: 5px; border: 1px solid var(--app-border); border-radius: 8px; padding: 3px 10px; color: var(--gray-600); font-weight: 500; font-size: 11px; }
.board-cols { display: flex; gap: 10px; padding: 12px; }
.k-col { flex: 1; display: flex; flex-direction: column; border-radius: 12px; }
.k-head { display: flex; align-items: center; gap: 5px; padding: 7px 9px; border-radius: 12px 12px 0 0; }
.k-title { font-size: 12px; font-weight: 700; color: var(--gray-900); margin-right: auto; }
.k-count { border-radius: 999px; padding: 1px 7px; font-size: 10px; background: rgba(255,255,255,0.65); color: var(--gray-600); }
.k-wip { font-size: 9px; color: var(--gray-600); font-variant-numeric: tabular-nums; }
.k-tasks { display: flex; flex-direction: column; gap: 8px; padding: 8px; }
.k-col.k-blue { background: #dbeafe; }  .k-col.k-blue .k-head { background: #bfdbfe; }
.k-col.k-yellow { background: #fef9c3; } .k-col.k-yellow .k-head { background: #fef08a; }
.k-col.k-green { background: #dcfce7; }  .k-col.k-green .k-head { background: #bbf7d0; }

/* Карточка задачи as in KanbanTask */
.k-task { background: var(--app-surface); border: 1px solid var(--app-border); border-radius: 10px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }
.k-task.t-urgent { background: #fef2f2; }
.k-task.t-high { background: #fff7ed; }
.k-task.t-medium { background: #fefce8; }
.k-task.t-low { background: #f0fdf4; }
.k-task.t-default { background: var(--kanban-hl); }
.k-task-row { display: flex; align-items: center; gap: 4px; padding: 6px 8px; }
.task-id { background: var(--app-surface); border-radius: 6px; padding: 1px 6px; font-size: 10px; font-weight: 500; color: var(--gray-900); }
.task-due { display: inline-flex; align-items: center; gap: 4px; background: var(--app-surface); border-radius: 6px; padding: 1px 6px; font-size: 10px; font-weight: 500; color: var(--gray-900); }
.task-due.red { background: #dc2626; color: #fff; }
.task-left { border-radius: 6px; padding: 1px 6px; font-size: 10px; font-weight: 500; }
.task-left.warn { background: #fed7aa; color: #7c2d12; }
.task-left.late { background: #dc2626; color: #fff; }
.k-task-title { font-size: 11px; font-weight: 500; color: var(--gray-900); line-height: 1.35; padding: 0 8px; margin-bottom: 6px; }
.k-task-people { display: flex; gap: 4px; padding: 0 8px 7px; }
.k-avatar { width: 14px; height: 14px; border-radius: 50%; background: var(--gray-300); display: inline-flex; align-items: center; justify-content: center; font-size: 7px; font-weight: 600; color: var(--gray-700); }
.k-tagbar { background: var(--kanban-hl); border-top: 1px solid var(--app-border); padding: 5px 8px; display: flex; gap: 4px; flex-wrap: wrap; }
.k-tag { font-size: 9px; padding: 1px 6px; border-radius: 6px; background: var(--gray-400); color: #fff; }

/* ============ Таблицы ============ */
table { width: 100%; border-collapse: collapse; font-size: 16px; }
th, td { border-bottom: 1px solid var(--app-border); padding: 8px 12px; text-align: left; }
th { color: var(--app-muted); font-weight: 500; }
.yes { display: inline-block; background: var(--status-completed-bg); color: var(--status-completed-text); border-radius: 999px; padding: 2px 10px; font-weight: 600; font-size: 14px; }
.part { display: inline-block; background: var(--badge-amber-bg); color: var(--badge-amber-fg); border-radius: 999px; padding: 2px 10px; font-weight: 600; font-size: 14px; }
.no { color: var(--gray-400); }

/* ============ Цифры ============ */
.stat { color: var(--gray-900); font-weight: 700; font-size: 38px; line-height: 1.1; }
.stat-label { color: var(--app-muted); font-size: 13px; }

/* ============ График роста ============ */
/* SVG отдаём через background-image: Marp экранирует inline <svg> (рендерит как текст). */
.growth-chart { width: 100%; max-width: 900px; height: 336px; margin: 8px auto 0;
  background-repeat: no-repeat; background-position: center; background-size: contain;
  background-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA5MDAgMzYwIiBmb250LWZhbWlseT0iSW50ZXIsIHN5c3RlbS11aSwgc2Fucy1zZXJpZiI+CjxnIGZvbnQtc2l6ZT0iMTQiIGZpbGw9IiM0YjU1NjMiPjxyZWN0IHg9IjcwIiB5PSI0IiB3aWR0aD0iMTQiIGhlaWdodD0iMTQiIHJ4PSIzIiBmaWxsPSIjMjU2M2ViIi8+PHRleHQgeD0iOTAiIHk9IjE2Ij7Rg9GH0LDRgdGC0L3QuNC60Lg8L3RleHQ+PGNpcmNsZSBjeD0iMjEyIiBjeT0iMTEiIHI9IjYiIGZpbGw9IiNmZmZmZmYiIHN0cm9rZT0iIzBmMTcyYSIgc3Ryb2tlLXdpZHRoPSIzIi8+PHRleHQgeD0iMjI0IiB5PSIxNiI+0L/RgNC+0LXQutGC0Ys8L3RleHQ+PC9nPgo8ZyBzdHJva2U9IiNlNWU3ZWIiIHN0cm9rZS13aWR0aD0iMSI+PGxpbmUgeDE9IjcwIiB5MT0iMzEwIiB4Mj0iODMwIiB5Mj0iMzEwIi8+PGxpbmUgeDE9IjcwIiB5MT0iMjU2IiB4Mj0iODMwIiB5Mj0iMjU2Ii8+PGxpbmUgeDE9IjcwIiB5MT0iMjAyIiB4Mj0iODMwIiB5Mj0iMjAyIi8+PGxpbmUgeDE9IjcwIiB5MT0iMTQ4IiB4Mj0iODMwIiB5Mj0iMTQ4Ii8+PGxpbmUgeDE9IjcwIiB5MT0iOTQiIHgyPSI4MzAiIHkyPSI5NCIvPjxsaW5lIHgxPSI3MCIgeTE9IjQwIiB4Mj0iODMwIiB5Mj0iNDAiLz48L2c+CjxnIGZvbnQtc2l6ZT0iMTIiIGZpbGw9IiM5Y2EzYWYiIHRleHQtYW5jaG9yPSJlbmQiPjx0ZXh0IHg9IjU4IiB5PSIzMTQiPjA8L3RleHQ+PHRleHQgeD0iNTgiIHk9IjI2MCI+NTA8L3RleHQ+PHRleHQgeD0iNTgiIHk9IjIwNiI+MTAwPC90ZXh0Pjx0ZXh0IHg9IjU4IiB5PSIxNTIiPjE1MDwvdGV4dD48dGV4dCB4PSI1OCIgeT0iOTgiPjIwMDwvdGV4dD48dGV4dCB4PSI1OCIgeT0iNDQiPjI1MDwvdGV4dD48L2c+CjxnIGZvbnQtc2l6ZT0iMTIiIGZpbGw9IiM5Y2EzYWYiIHRleHQtYW5jaG9yPSJzdGFydCI+PHRleHQgeD0iODQyIiB5PSIzMTQiPjA8L3RleHQ+PHRleHQgeD0iODQyIiB5PSIyMjQiPjEwPC90ZXh0Pjx0ZXh0IHg9Ijg0MiIgeT0iMTM0Ij4yMDwvdGV4dD48dGV4dCB4PSI4NDIiIHk9IjQ0Ij4zMDwvdGV4dD48L2c+CjxnIGZpbGw9IiMyNTYzZWIiPjxyZWN0IHg9IjExNSIgeT0iMTE0LjUiIHdpZHRoPSI1NiIgaGVpZ2h0PSIxOTUuNSIgcng9IjQiLz48cmVjdCB4PSIzMDUiIHk9IjEwOCIgd2lkdGg9IjU2IiBoZWlnaHQ9IjIwMiIgcng9IjQiLz48cmVjdCB4PSI0OTUiIHk9IjcxLjMiIHdpZHRoPSI1NiIgaGVpZ2h0PSIyMzguNyIgcng9IjQiLz48cmVjdCB4PSI2ODUiIHk9IjEwOS4xIiB3aWR0aD0iNTYiIGhlaWdodD0iMjAwLjkiIHJ4PSI0Ii8+PC9nPgo8ZyBmaWxsPSIjMWQ0ZWQ4IiBmb250LXNpemU9IjE0IiBmb250LXdlaWdodD0iNzAwIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj48dGV4dCB4PSIxNDMiIHk9IjEwNiI+MTgxPC90ZXh0Pjx0ZXh0IHg9IjMzMyIgeT0iMTAwIj4xODc8L3RleHQ+PHRleHQgeD0iNTIzIiB5PSI2MyI+MjIxPC90ZXh0Pjx0ZXh0IHg9IjcxMyIgeT0iMTAxIj4xODY8L3RleHQ+PC9nPgo8cG9seWxpbmUgcG9pbnRzPSIxOTUsMTAzIDM4NSw4NSA1NzUsNjcgNzY1LDc2IiBmaWxsPSJub25lIiBzdHJva2U9IiMwZjE3MmEiIHN0cm9rZS13aWR0aD0iMyIvPgo8ZyBmaWxsPSIjZmZmZmZmIiBzdHJva2U9IiMwZjE3MmEiIHN0cm9rZS13aWR0aD0iMyI+PGNpcmNsZSBjeD0iMTk1IiBjeT0iMTAzIiByPSI2Ii8+PGNpcmNsZSBjeD0iMzg1IiBjeT0iODUiIHI9IjYiLz48Y2lyY2xlIGN4PSI1NzUiIGN5PSI2NyIgcj0iNiIvPjxjaXJjbGUgY3g9Ijc2NSIgY3k9Ijc2IiByPSI2Ii8+PC9nPgo8ZyBmaWxsPSIjMGYxNzJhIiBmb250LXNpemU9IjE0IiBmb250LXdlaWdodD0iNzAwIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj48dGV4dCB4PSIxOTUiIHk9Ijg5Ij4yMzwvdGV4dD48dGV4dCB4PSIzODUiIHk9IjcxIj4yNTwvdGV4dD48dGV4dCB4PSI1NzUiIHk9IjUzIj4yNzwvdGV4dD48dGV4dCB4PSI3NjUiIHk9IjYyIj4yNjwvdGV4dD48L2c+CjxnIGZvbnQtc2l6ZT0iMTYiIGZvbnQtd2VpZ2h0PSI2MDAiIGZpbGw9IiM0YjU1NjMiIHRleHQtYW5jaG9yPSJtaWRkbGUiPjx0ZXh0IHg9IjE2NSIgeT0iMzM4Ij4yMDIzPC90ZXh0Pjx0ZXh0IHg9IjM1NSIgeT0iMzM4Ij4yMDI0PC90ZXh0Pjx0ZXh0IHg9IjU0NSIgeT0iMzM4Ij4yMDI1PC90ZXh0Pjx0ZXh0IHg9IjczNSIgeT0iMzM4Ij4yMDI2PC90ZXh0PjwvZz4KPHRleHQgeD0iNDUwIiB5PSIzNTYiIGZvbnQtc2l6ZT0iMTIiIGZpbGw9IiM5Y2EzYWYiIHRleHQtYW5jaG9yPSJtaWRkbGUiPtC70LXQstCw0Y8g0YjQutCw0LvQsCDigJQg0YPRh9Cw0YHRgtC90LjQutC4IMK3INC/0YDQsNCy0LDRjyDRiNC60LDQu9CwIOKAlCDQv9GA0L7QtdC60YLRizwvdGV4dD4KPC9zdmc+Cg=="); }

/* Компактный график на слайде «Целевая аудитория» */
.growth-chart.compact { height: 250px; max-width: 660px; margin-top: 10px; }

/* ============ Скриншоты интерфейса (крупно, по 2 на слайд) ============ */
section.shots { padding: 26px 30px; }
.shot-grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 4px 0 0; }
.shot-grid2 figure { margin: 0; border: 1px solid var(--app-border); border-radius: 16px; overflow: hidden; background: var(--app-surface); box-shadow: var(--shadow-card); }
.shot-grid2 img { display: block; width: 100%; height: auto; }

section.title { background: var(--app-surface); }
section.title::before { content: ""; display: block; height: 6px; background: var(--app-primary); position: absolute; top: 0; left: 0; right: 0; }

/* ============ Титульный слайд: hero с мокапами продукта на фоне ============ */
section.title { position: relative; }
.hero { position: relative; min-height: 100%; }
.hero-back { position: absolute; left: -56px; right: -56px; top: -44px; bottom: -44px; z-index: 0; overflow: hidden; }
.blob { position: absolute; border-radius: 50%; }
.blob.b1 { width: 46%; height: 46%; left: -8%; top: -12%; background: radial-gradient(circle at 35% 35%, #dbeafe, rgba(219,234,254,0.2) 55%, rgba(219,234,254,0)); }
.blob.b2 { width: 50%; height: 50%; right: -10%; bottom: -18%; background: radial-gradient(circle at 60% 60%, #dcfce7, rgba(220,252,231,0.25) 55%, rgba(220,252,231,0)); }
.blob.b3 { width: 40%; height: 40%; right: 16%; top: -6%; background: radial-gradient(circle at 50% 50%, #ede9fe, rgba(237,233,254,0.3) 55%, rgba(237,233,254,0)); }
.deco-win { position: absolute; border-radius: 16px; box-shadow: 0 30px 60px -20px rgba(17, 24, 39, 0.22); }
.w-main { left: -70px; top: 104px; width: 590px; transform: rotate(-2.5deg); }
.w-kanban { right: -92px; top: 158px; width: 545px; transform: rotate(2.2deg); }
.hero-card { position: absolute; z-index: 2; left: 50%; top: 50%; transform: translate(-50%, -50%); width: 640px; text-align: center; background: rgba(255, 255, 255, 0.9); border: 1px solid var(--app-border); border-radius: 28px; box-shadow: 0 40px 80px -28px rgba(17, 24, 39, 0.28); padding: 34px 44px 30px; }
.hero-logo { display: block; width: 128px; margin: 0 auto 10px; }
section.title .hero-card h1 { font-size: 68px; margin: 6px 0 2px; letter-spacing: -0.03em; }
.hero-tag { font-size: 23px; font-weight: 600; color: var(--gray-600); letter-spacing: -0.01em; margin: 2px 0 2px; }
.hero-sub { font-size: 15px; font-weight: 700; color: var(--app-blue); letter-spacing: 0.01em; margin: 8px 0 0; }
.hero-cta { margin-top: 24px; display: flex; justify-content: center; gap: 10px; }
.hero-author { margin-top: 26px; font-size: 15px; font-weight: 600; color: var(--gray-900); }
.hero-goal { display: block; margin: 8px auto 0; max-width: 480px; font-size: 13px; color: var(--app-muted); }

/* ============ Роадмап: двухуровневый нумерованный список ============ */
ol.roadmap { counter-reset: rm; list-style: none; margin: 4px 0 0; padding: 0; }
ol.roadmap > li { counter-increment: rm; position: relative; padding-left: 48px; margin: 0 0 16px; font-size: 19px; font-weight: 700; color: var(--gray-900); }
ol.roadmap > li::before { content: counter(rm); position: absolute; left: 0; top: -2px; width: 32px; height: 32px; border-radius: 10px; background: var(--status-inprogress-bg); color: var(--status-inprogress-text); display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: 700; }
ol.roadmap > li > ol { counter-reset: sub; list-style: none; margin: 10px 0 0; padding: 0; }
ol.roadmap > li > ol > li { counter-increment: sub; position: relative; padding-left: 52px; margin: 6px 0; font-size: 15px; font-weight: 400; color: var(--app-muted); }
ol.roadmap > li > ol > li::before { content: counter(rm) "." counter(sub); position: absolute; left: 0; top: 1px; font-size: 14px; font-weight: 700; color: var(--app-blue); }
</style>

<!-- _paginate: false -->

<!-- _header: "" -->

<!-- _footer: "" -->

<!--
[0:00–0:10] ОТКРЫТИЕ
Привет! Я Антон Афанасьев, основатель EduFlow. Мы делаем платформу, которая собирает проекты, команды и дедлайны в одном месте — для проектного обучения в вузах и для организаторов событий. За три минуты покажу проблему, работающий продукт, бизнес-модель и кейс внедрения в ИТМО.
-->

<div class="hero">
<div class="hero-back">
<div class="blob b1"></div>
<div class="blob b2"></div>
<div class="blob b3"></div>
<div class="ui-window deco-win w-main">
<div class="win-bar">
<div class="win-dots"><i></i><i></i><i></i></div>
<div class="win-search"><span class="ico ico-search"></span> поиск по проектам</div>
</div>
<div class="win-filters">
<span class="chip">Мой этап <span style="color:#9ca3af">▾</span></span>
<span class="chip">Тег <span style="color:#9ca3af">▾</span></span>
<span class="chip">Участник <span style="color:#9ca3af">▾</span></span>
<span class="chip">Срок <span style="color:#9ca3af">▾</span></span>
<span class="win-count">4 проекта</span>
</div>
<div class="cards2">
<div class="p-card">
<div><span class="pill pill-planned">Запланирован</span></div>
<div class="p-title">Хакатон «Университет 2026»</div>
<div class="p-desc">Приём заявок, разбор и отбор команд — в одном проекте.</div>
<div class="p-prog">Прогресс</div>
<div class="p-bar"><i style="width:15%"></i></div>
<div class="p-row"><span class="ico ico-cal"></span> 18 апр · Подготовка</div>
<div class="p-foot">
<span class="p-users"><span class="ico ico-users"></span> 4 участника</span>
<span class="avatars"><span class="avatar">А</span><span class="avatar">М</span><span class="avatar">Т</span><span class="avatarcount">+1</span></span>
</div>
</div>
<div class="p-card">
<div><span class="pill pill-inprogress">В работе</span></div>
<div class="p-title">Редизайн сайта</div>
<div class="p-desc">Обновление главной и раздела с курсами, перенос из старой CMS.</div>
<div class="p-prog">Прогресс</div>
<div class="p-bar"><i style="width:55%"></i></div>
<div class="p-row"><span class="ico ico-cal"></span> 12 фев · Дизайн</div>
<div class="p-foot">
<span class="p-users"><span class="ico ico-users"></span> 3 участника</span>
<span class="avatars"><span class="avatar">А</span><span class="avatar">М</span><span class="avatar">Д</span></span>
</div>
</div>
<div class="p-card">
<div><span class="pill pill-review">На проверке</span></div>
<div class="p-title">Мобильное приложение</div>
<div class="p-desc">Доска, задачи и уведомления в одном приложении для телефона.</div>
<div class="p-prog">Прогресс</div>
<div class="p-bar"><i style="width:85%"></i></div>
<div class="p-row"><span class="ico ico-cal"></span> 28 фев · Разработка</div>
<div class="p-foot">
<span class="p-users"><span class="ico ico-users"></span> 5 участников</span>
<span class="avatars"><span class="avatar">М</span><span class="avatar">Т</span><span class="avatar">Д</span><span class="avatarcount">+2</span></span>
</div>
</div>
<div class="p-card">
<div><span class="pill pill-completed">Выполнен</span></div>
<div class="p-title">Версия 2.0 API</div>
<div class="p-desc">Обновление контрактов и переход на новую схему авторизации.</div>
<div class="p-prog">Прогресс</div>
<div class="p-bar"><i style="width:100%"></i></div>
<div class="p-row"><span class="ico ico-cal"></span> 5 фев · Запуск</div>
<div class="p-foot">
<span class="p-users"><span class="ico ico-users"></span> 2 участника</span>
<span class="avatars"><span class="avatar">Т</span><span class="avatar">И</span></span>
</div>
</div>
</div>
</div>
<div class="board deco-win w-kanban">
<div class="board-head">Хакатон «Университет 2026» <span class="board-top">·</span> <span class="board-top">Подготовка</span>
<span class="board-filter"><span class="ico ico-filter"></span> Фильтры</span>
</div>
<div class="board-cols">
<div class="k-col k-blue">
<div class="k-head"><span class="k-title">Канбан</span><span class="k-count">2</span><span class="k-wip">2/5</span></div>
<div class="k-tasks">
<div class="k-task t-medium">
<div class="k-task-row"><span class="task-id">#1001</span><span class="task-due">6 дн.</span></div>
<div class="k-task-title">Собрать требования к заявке</div>
<div class="k-task-people"><span class="k-avatar">А</span></div>
<div class="k-tagbar"><span class="k-tag">Документы</span></div>
</div>
<div class="k-task t-high">
<div class="k-task-row"><span class="task-id">#1002</span><span class="task-due task-left warn">2 дн.</span></div>
<div class="k-task-title">Согласовать ТЗ с комиссией</div>
<div class="k-task-people"><span class="k-avatar">М</span><span class="k-avatar">Д</span></div>
<div class="k-tagbar"><span class="k-tag">ТЗ</span></div>
</div>
</div>
</div>
<div class="k-col k-yellow">
<div class="k-head"><span class="k-title">В работе</span><span class="k-count">2</span><span class="k-wip">2/3</span></div>
<div class="k-tasks">
<div class="k-task t-urgent">
<div class="k-task-row"><span class="task-id">#2011</span><span class="task-due task-left late">1 дн.</span></div>
<div class="k-task-title">Форма регистрации команд</div>
<div class="k-task-people"><span class="k-avatar">Т</span><span class="k-avatar">О</span></div>
<div class="k-tagbar"><span class="k-tag">Фронтенд</span><span class="k-tag">Дизайн</span></div>
</div>
<div class="k-task t-default">
<div class="k-task-row"><span class="task-id">#2012</span><span class="task-due">5 дн.</span></div>
<div class="k-task-title">Экран списка проектов</div>
<div class="k-task-people"><span class="k-avatar">О</span></div>
<div class="k-tagbar"><span class="k-tag">Фронтенд</span></div>
</div>
</div>
</div>
<div class="k-col k-green">
<div class="k-head"><span class="k-title">Готово</span><span class="k-count">1</span></div>
<div class="k-tasks">
<div class="k-task t-low">
<div class="k-task-row"><span class="task-id">#3011</span></div>
<div class="k-task-title">Роли и доступы для жюри</div>
<div class="k-task-people"><span class="k-avatar">И</span></div>
<div class="k-tagbar"><span class="k-tag">Бэкенд</span></div>
</div>
</div>
</div>
</div>
</div>
</div>
<div class="hero-card">
<img class="hero-logo" src="../../../frontend/public/eduflow.PNG" alt="EduFlow">
<span class="pill-badge">Бесплатно · Данные в России · Отборочный питчинг 2026</span>
<div class="hero-sub">Тренажёр для управления учебными проектами</div>
<div class="hero-tag">Проекты, команды и дедлайны — в одном месте</div>
<div class="hero-cta">
<span class="ui-btn ui-btn-dark">Попробовать бесплатно</span>
<span class="ui-btn ui-btn-outline">Войти</span>
</div>
<div class="hero-author">Афанасьев Антон · orderkworinaa@gmail.com</div>
<em class="hero-goal">Цель на акселератор — первые платящие клиенты: команды, вузы, организаторы событий</em>
</div>
</div>

---

<!--
[0:10–0:45] ПРОБЛЕМА
В проектном обучении одновременно десятки людей и команд. Держать в голове, кто в какой команде и на каком этапе, — невозможно. Людей распределяют вручную, в таблицах и чатах: долго, субъективно и не воспроизводится. Всё разбросано — резюме, отклики, приглашения, роли и статусы живут в переписке, единой картины нет ни у кого. И не видно истории: кто что делал и где сорвался срок, по чатам не восстановишь. А цена ошибки растёт с масштабом — это уже не один проект, а весь поток.
-->

## Проблема

<div class="grid">
<div class="ui-card">
<h3>Людей и команд — десятки</h3>
Держать в голове, кто в какой команде и на каком этапе, физически невозможно.
</div>
<div class="ui-card">
<h3>Распределение вручную</h3>
Подбор по навыкам, интересам и ролям — в таблицах и чатах: долго, субъективно, не воспроизводится.
</div>
<div class="ui-card">
<h3>Всё разбросано</h3>
Резюме, отклики, приглашения, роли и статусы живут в переписке. Единой картины нет ни у кого.
</div>
<div class="ui-card">
<h3>Не видно, что происходило</h3>
Кто что делал, где сорвался срок и что пошло не так — по чатам и таблицам не восстановить.
</div>
</div>

**Цена ошибки растёт с масштабом:** слабый состав, дубли ролей и сорванные сроки — уже во всём потоке, а не в одном проекте.

---

<!--
[0:45–1:07] ЦЕЛЕВАЯ АУДИТОРИЯ
Продукт — для трёх сегментов. Учебные команды и вузы: распределение людей по командам, десятки проектов, оценивание. Организаторы событий: хакатоны и акселераторы, где надо быстро собрать команды, раздать роли жюри и держать дедлайны. Продуктовые команды: доска, этапы и история решений вместо мессенджеров. И это не гипотеза: с 2023 года каждый год 23–27 проектов и 180–220 участников, в 2026 — 26 проектов и 186 участников.
-->

## Целевая аудитория

<div class="grid3">
<div class="ui-card">
<h3>Учебные команды и вузы</h3>
Распределение людей по командам, десятки проектов, оценивание.
</div>
<div class="ui-card">
<h3>Организаторы событий</h3>
Хакатоны и акселераторы: сборка команд, роли жюри, дедлайны.
</div>
<div class="ui-card">
<h3>Продуктовые команды</h3>
Доска, этапы и история решений вместо мессенджеров.
</div>
</div>

**Уже четвёртый год работаем в ФПИН ИТМО (с 2023)** — дальше вузы с проектным обучением и организаторы хакатонов.

<div class="growth-chart compact"></div>

<div class="center"><span class="sub">Участники — столбцы (левая шкала), проекты — линия (правая шкала).</span></div>

---

<!--
[1:07–1:22] КЕЙС ФПИН ИТМО
Мы не гипотеза: тренажер работает в ФПИН ИТМО с 2023 года, сейчас это 4-й год. В 2026 — 26 проектов и 186 участников. Бакалавры проходят «Введение в профессиональную деятельность», магистранты — «Курсовой проект»: магистрант собирает команду, пишет ТЗ и ведёт проект как руководитель и ментор, а бакалавры реализуют. По опросу студенты получили командную работу, погружение в специальность и реальные инструменты — Docker, FastAPI, Figma, iOS.
-->

## Кейс: тренажер в ФПИН ИТМО с 2023 года

<div class="grid" style="grid-template-columns:repeat(4,1fr)">
<div><div class="stat">4</div><div class="stat-label">года в ФПИН ИТМО (с 2023)</div></div>
<div><div class="stat">1</div><div class="stat-label">дисциплина</div></div>
<div><div class="stat">26</div><div class="stat-label">проектов в 2026</div></div>
<div><div class="stat">186</div><div class="stat-label">участников в 2026</div></div>
</div>

**4-й год внедрения (с 2023)** · Бакалавры — «Введение в профессиональную деятельность» (1 курс) · Магистранты — «Курсовой проект»

<div class="grid" style="margin:12px 0 0">
<div class="ui-card">
<h3>Как это работает</h3>
Магистрант собирает команду, пишет ТЗ и ведёт проект как руководитель и ментор — бакалавры реализуют.
</div>
<div class="ui-card">
<h3>Что даёт студентам <span class="sub">(из опроса)</span></h3>
Командная работа · погружение в специальность · реальные инструменты (Docker, FastAPI, Figma, iOS, LLM) · интеграция в профессию и профориентация.
</div>
</div>

<span class="sub">С 2026 — новая система: единый список проектов, канбан, ТЗ и вики, роли и отклики в одном пространстве.</span>

---

<!--
[1:22–1:35] ПРОДУКТ
Вот два реальных экрана. Слева — единый список проектов: поиск, фильтры по этапу, тегу, участнику и сроку, карточки со статусом, прогрессом и командой. Справа — канбан проекта: колонки с WIP-лимитами, задачи с приоритетом, дедлайном и исполнителями. Логика простая: пространство → проект с этапами и командой → доска с задачами, ТЗ и вики.
Если спросят: за одним канбаном могут работать несколько команд — это разные проекты в одном пространстве.
-->

## Продукт

<div class="grid">
<div style="display:flex; flex-direction:column">
<em>Экран 1: единый список проектов</em>
<div class="ui-window" style="margin-top:8px; flex:1">
<div class="win-bar">
<div class="win-dots"><i></i><i></i><i></i></div>
<div class="win-search"><span class="ico ico-search"></span> поиск по проектам</div>
</div>
<div class="win-filters">
<span class="chip">Мой этап <span style="color:#9ca3af">▾</span></span>
<span class="chip">Тег <span style="color:#9ca3af">▾</span></span>
<span class="chip">Участник <span style="color:#9ca3af">▾</span></span>
<span class="chip">Срок <span style="color:#9ca3af">▾</span></span>
<span class="win-count">4 проекта</span>
</div>
<div class="cards2">
<div class="p-card">
<div><span class="pill pill-planned">Запланирован</span></div>
<div class="p-title">Хакатон «Университет 2026»</div>
<div class="p-desc">Приём заявок, разбор и отбор команд — в одном проекте.</div>
<div class="p-prog">Прогресс</div>
<div class="p-bar"><i style="width:15%"></i></div>
<div class="p-row"><span class="ico ico-cal"></span> 18 апр · Подготовка</div>
<div class="p-foot">
<span class="p-users"><span class="ico ico-users"></span> 4 участника</span>
<span class="avatars"><span class="avatar">А</span><span class="avatar">М</span><span class="avatar">Т</span><span class="avatarcount">+1</span></span>
</div>
</div>
<div class="p-card">
<div><span class="pill pill-inprogress">В работе</span></div>
<div class="p-title">Редизайн сайта</div>
<div class="p-desc">Обновление главной и раздела с курсами, перенос из старой CMS.</div>
<div class="p-prog">Прогресс</div>
<div class="p-bar"><i style="width:55%"></i></div>
<div class="p-row"><span class="ico ico-cal"></span> 12 фев · Дизайн</div>
<div class="p-foot">
<span class="p-users"><span class="ico ico-users"></span> 3 участника</span>
<span class="avatars"><span class="avatar">А</span><span class="avatar">М</span><span class="avatar">Д</span></span>
</div>
</div>
<div class="p-card">
<div><span class="pill pill-review">На проверке</span></div>
<div class="p-title">Мобильное приложение</div>
<div class="p-desc">Доска, задачи и уведомления в одном приложении для телефона.</div>
<div class="p-prog">Прогресс</div>
<div class="p-bar"><i style="width:85%"></i></div>
<div class="p-row"><span class="ico ico-cal"></span> 28 фев · Разработка</div>
<div class="p-foot">
<span class="p-users"><span class="ico ico-users"></span> 5 участников</span>
<span class="avatars"><span class="avatar">М</span><span class="avatar">Т</span><span class="avatar">Д</span><span class="avatarcount">+2</span></span>
</div>
</div>
<div class="p-card">
<div><span class="pill pill-completed">Выполнен</span></div>
<div class="p-title">Версия 2.0 API</div>
<div class="p-desc">Обновление контрактов и переход на новую схему авторизации.</div>
<div class="p-prog">Прогресс</div>
<div class="p-bar"><i style="width:100%"></i></div>
<div class="p-row"><span class="ico ico-cal"></span> 5 фев · Запуск</div>
<div class="p-foot">
<span class="p-users"><span class="ico ico-users"></span> 2 участника</span>
<span class="avatars"><span class="avatar">Т</span><span class="avatar">И</span></span>
</div>
</div>
</div>
</div>
</div>
<div style="display:flex; flex-direction:column">
<em>Экран 2: канбан проекта</em>
<div class="board" style="margin-top:8px; flex:1">
<div class="board-head">Хакатон «Университет 2026» <span class="board-top">·</span> <span class="board-top">Подготовка</span>
<span class="board-filter"><span class="ico ico-filter"></span> Фильтры</span>
</div>
<div class="board-cols">
<div class="k-col k-blue">
<div class="k-head"><span class="k-title">Канбан</span><span class="k-count">2</span><span class="k-wip">2/5</span></div>
<div class="k-tasks">
<div class="k-task t-medium">
<div class="k-task-row"><span class="task-id">#1001</span><span class="task-due">6 дн.</span></div>
<div class="k-task-title">Собрать требования к заявке</div>
<div class="k-task-people"><span class="k-avatar">А</span></div>
<div class="k-tagbar"><span class="k-tag">Документы</span></div>
</div>
<div class="k-task t-high">
<div class="k-task-row"><span class="task-id">#1002</span><span class="task-due task-left warn">2 дн.</span></div>
<div class="k-task-title">Согласовать ТЗ с комиссией</div>
<div class="k-task-people"><span class="k-avatar">М</span><span class="k-avatar">Д</span></div>
<div class="k-tagbar"><span class="k-tag">ТЗ</span></div>
</div>
</div>
</div>
<div class="k-col k-yellow">
<div class="k-head"><span class="k-title">В работе</span><span class="k-count">2</span><span class="k-wip">2/3</span></div>
<div class="k-tasks">
<div class="k-task t-urgent">
<div class="k-task-row"><span class="task-id">#2011</span><span class="task-due task-left late">1 дн.</span></div>
<div class="k-task-title">Форма регистрации команд</div>
<div class="k-task-people"><span class="k-avatar">Т</span><span class="k-avatar">О</span></div>
<div class="k-tagbar"><span class="k-tag">Фронтенд</span><span class="k-tag">Дизайн</span></div>
</div>
<div class="k-task t-default">
<div class="k-task-row"><span class="task-id">#2012</span><span class="task-due">5 дн.</span></div>
<div class="k-task-title">Экран списка проектов</div>
<div class="k-task-people"><span class="k-avatar">О</span></div>
<div class="k-tagbar"><span class="k-tag">Фронтенд</span></div>
</div>
</div>
</div>
<div class="k-col k-green">
<div class="k-head"><span class="k-title">Готово</span><span class="k-count">1</span></div>
<div class="k-tasks">
<div class="k-task t-low">
<div class="k-task-row"><span class="task-id">#3011</span></div>
<div class="k-task-title">Роли и доступы для жюри</div>
<div class="k-task-people"><span class="k-avatar">И</span></div>
<div class="k-tagbar"><span class="k-tag">Бэкенд</span></div>
</div>
</div>
</div>
</div>
</div>
</div>
</div>

<span class="sub"> пространство → проект с этапами и командой → доска с задачами, ТЗ и вики. Отклики, приглашения по ссылке и роли уровня проекта уже в продукте.</span>

---

<!--
[1:35–1:37] ИНТЕРФЕЙС · ЭКРАНЫ 1–2
Единый список проектов с поиском и фильтрами; карточки со статусом, прогрессом и командой.
-->
<!-- _class: shots -->

## Интерфейс 

<div class="sub">Экраны 1–2 из 6</div>

<div class="shot-grid2">
<figure><img src="../images/features/shot-1.png" alt="Экран 1"></figure>
<figure><img src="../images/features/shot-2.png" alt="Экран 2"></figure>
</div>

---

<!--
[1:37–1:39] ИНТЕРФЕЙС · ЭКРАНЫ 3–4
Канбан с WIP-лимитами и приоритетами; техзадание с группами требований и согласованием.
-->
<!-- _class: shots -->

## Интерфейс 

<div class="sub">Экраны 3–4 из 6</div>

<div class="shot-grid2">
<figure><img src="../images/features/shot-3.png" alt="Экран 3"></figure>
<figure><img src="../images/features/shot-4.png" alt="Экран 4"></figure>
</div>

---

<!--
[1:39–1:40] ИНТЕРФЕЙС · ЭКРАНЫ 5–6
Вики проекта, история активности и уведомления из всех проектов.
-->
<!-- _class: shots -->

## Интерфейс 

<div class="sub">Экраны 5–6 из 6</div>

<div class="shot-grid2">
<figure><img src="../images/features/shot-5.png" alt="Экран 5"></figure>
<figure><img src="../images/features/shot-6.png" alt="Экран 6"></figure>
</div>

---

<!--
[1:40–1:55] ВОЗМОЖНОСТИ
Три группы возможностей. Команда: пространства по направлениям, поиск проектов и людей, приглашения по ссылке и отклики, роли и права на уровне проекта. Работа: канбан с перетаскиванием, WIP-лимиты и приоритеты, техзадание с согласованием, вики проекта. Контроль: единый список проектов с фильтрами, уведомления из всех проектов и история активности как в GitHub.
-->

## Возможности

<div class="grid3">
<div class="ui-card">
<h3>Команда</h3>
<ul>
<li>Пространства по интересам и направлениям</li>
<li>Поиск проектов и людей в одном поле</li>
<li>Приглашения по ссылке и отклики</li>
<li>Роли и права доступа на уровне проекта</li>
</ul>
</div>
<div class="ui-card">
<h3>Работа</h3>
<ul>
<li>Канбан с перетаскиванием карточек</li>
<li>WIP-лимиты на колонках, приоритеты, подзадачи</li>
<li>Техзадание с группами требований и согласованием</li>
<li>Вики проекта</li>
</ul>
</div>
<div class="ui-card">
<h3>Контроль</h3>
<ul>
<li>Единый список всех проектов с фильтрами</li>
<li>Фильтры по этапу, тегу, участнику и сроку</li>
<li>Уведомления о событиях из всех проектов</li>
<li>История активности как в GitHub: график вклада и лента действий</li>
</ul>
</div>
</div>

**Уже работает:** регистрация с подтверждением e-mail, профиль и портфолио, резюме с навыками, пространства, проекты с этапами, канбан, ТЗ с согласованием и вики.

---

<!--
[1:55–2:05] ЧЕМ ОТЛИЧАЕМСЯ
Прямых конкурентов в нашей нише нет. Зарубежные PBL- — Riipen и Practera — сильны связкой «вуз ↔ компания», но это не рабочий контур команды внутри вуза: нет данных в РФ и нет сегмента событий. Российские аналоги — ProjectsSibsau и ПУТП — это маркетплейс проектов и госпрограмма, а не инструмент команды. Косвенные — универсальные трекеры (Trello, Notion), LMS (Moodle, Blackboard), GitHub Classroom и  событий (Devpost, HackerEarth): каждое закрывает лишь часть процесса. Детальная таблица — в приложении, на Q&A.
-->

## Чем отличаемся

<div class="grid">
<div class="ui-card">
<h3>Прямые аналоги — PBL-</h3>
<ul>
<li><b>Riipen · Practera</b> <span class="sub">(мир, experiential learning)</span><br><span style="color:#16a34a;font-weight:700">＋</span> реальные проекты с компаниями, оценивание, масштаб<br><span style="color:#dc2626;font-weight:700">－</span> не контур вуза, нет данных в РФ, нет событий</li>
<li><b>Project Pals</b> <span class="sub">(США)</span><br><span style="color:#16a34a;font-weight:700">＋</span> заточен под PBL, оценивание, AI<br><span style="color:#dc2626;font-weight:700">－</span> школы (K-12), англоязычный, без канбана и ТЗ</li>
<li><b>ProjectsSibsau · ПУТП</b> <span class="sub">(РФ)</span><br><span style="color:#16a34a;font-weight:700">＋</span> локальные, связь с индустрией и гранты<br><span style="color:#dc2626;font-weight:700">－</span> маркетплейс проектов / госпрограмма, а не рабочий инструмент команды</li>
</ul>
</div>
<div class="ui-card">
<h3>Косвенные — трекеры, LMS, события</h3>
<ul>
<li><b>Trello · Notion · Asana</b> — универсальные трекеры: нет учебного процесса, распределения и оценивания</li>
<li><b>Moodle · Blackboard</b> — про курсы, тяжёлые: без канбана, ТЗ и вики</li>
<li><b>GitHub Classroom</b> — только код и репозитории, без команд, ролей и оценивания</li>
<li><b>Devpost · HackerEarth</b> — только события: сабмиты и жюри, без непрерывной работы команды</li>
</ul>
</div>
</div>

_Соединяем то, что у других разрозненно: команды + проекты + канбан + ТЗ + вики + оценивание — данные в РФ._

---

<!--
[2:05–2:20] БИЗНЕС-МОДЕЛЬ · ПОТОКИ
Три потока выручки. Первый — подписка команд: расширенные лимиты и возможности. Второй — лицензии вузам: места, администрирование и оценивание. Третий — события: оплата за мероприятие. Конкретные цены не называю — валидируем на пилотах. Почему сразу три: бесплатный вход даёт трафик, B2B-лицензии — крупный чек, а события — быстрый первый платящий клиент.
-->

## Бизнес-модель: три потока выручки

<div class="grid3">
<div class="ui-card">
<h3><span class="pill pill-inprogress" style="margin-right:8px">1</span> Подписка команд</h3>
Команды и руководители платят за расширенные лимиты и возможности.
</div>
<div class="ui-card">
<h3><span class="pill pill-review" style="margin-right:8px">2</span> Лицензии вузам</h3>
Вуз платит за места, администрирование и оценивание.
</div>
<div class="ui-card">
<h3><span class="pill pill-planned" style="margin-right:8px">3</span> События</h3>
Хакатоны, акселераторы, олимпиады — оплата за мероприятие.
</div>
</div>

**Почему три сразу:** бесплатный вход (B2C) даёт трафик, B2B-лицензии — крупный чек, события — быстрый первый платящий клиент и валидация спроса.

---

<!--
[2:20–2:30] СТАТУС
Это не идея, а работающий сервис. Продукт: регистрация и профиль с резюме, распределение с откликами и приглашениями, пространства, проекты с этапами, ТЗ и вики. тренажер: 49 таблиц, 181 эндпоинт, 52 права и 4 роли, FastAPI и React, мониторинг, CI и тесты. И главное — тракшн: четвёртый год в ФПИН ИТМО.
-->

## Что уже сделано

<div class="grid">
<div class="ui-card">
<h3>Продукт</h3>
<ul>
<li>Регистрация с подтверждением e-mail, сброс пароля</li>
<li>Профиль: резюме, портфолио, образование, языки</li>
<li>Распределение: резюме и навыки, отклики, вакансии, приглашения по ссылке</li>
<li>Пространства: категории, статусы, настройки, типы проектов</li>
<li>Проекты: этапы, ТЗ с критериями приёмки, канбан, вики, уведомления</li>
</ul>
</div>
<div class="ui-card">
<h3>тренажер</h3>
<div class="grid3" style="gap:10px; margin-bottom:8px">
<div><div class="stat">49</div><div class="stat-label">таблиц PostgreSQL</div></div>
<div><div class="stat">181</div><div class="stat-label">эндпоинт API</div></div>
<div><div class="stat">52</div><div class="stat-label">права, 4 роли</div></div>
</div>
<ul>
<li>FastAPI + SQLAlchemy (async), Alembic-миграции</li>
<li>React 18 + TypeScript + Vite, Docker-деплой</li>
<li>Мониторинг Prometheus + Grafana, CI и тесты</li>
</ul>
Тракшн: уже четвёртый год в ФПИН ИТМО (с 2023) — «Введение в профессиональную деятельность» (бакалавры) и «Курсовой проект» (магистранты). Магистрант набирает команду, пишет ТЗ и ведёт проект, бакалавры реализуют.
</div>
</div>

---

<!--
[2:30–2:37] РОАДМАП
Три линии. Продукт: стабильность после обновления, публичные пространства, архивирование рабочих пространств и оценивание в реальном времени на защите работ. B2B и тренажер: интеграции GitHub и ITMO ID, поддомен и отдельное пространство для компании, лендинг под B2B, пилоты в вузах и биллинг. Оплата: подключение сервиса оплаты (RU/EN).
-->

## Роадмап развития

<ol class="roadmap">
<li><strong>Продукт</strong>
  <ol>
    <li><strong>Стабильность</strong> — багфиксы обновлённой системы, ключевые сценарии до прод-качества</li>
    <li><strong>Публичные пространства</strong> — вступить как руководитель проекта или участник</li>
    <li><strong>Архивирование рабочих пространств</strong> — завершённые пространства уходят из активных, данные сохраняются</li>
    <li><strong>Оценивание</strong> — в реальном времени во время защиты работ</li>
  </ol>
</li>
<li><strong>B2B и тренажер</strong>
  <ol>
    <li><strong>Интеграции</strong> — GitHub, ITMO ID, платёжный провайдер</li>
    <li><strong>B2B-среда</strong> — поддомен компании, отдельное пространство, связанное с платформой</li>
    <li><strong>Продажи</strong> — лендинг под B2B, пилоты в вузах, биллинг</li>
    <li><strong>Качество</strong> — производительность БД на росте данных</li>
  </ol>
</li>
<li><strong>Оплата</strong>
  <ol>
    <li><strong>Платёжный сервис</strong> — подключение сервиса оплаты (RU/EN)</li>
  </ol>
</li>
</ol>

---

<!--
[2:37–2:45] ЦЕЛЬ НА АКСЕЛЕРАТОР
Цель — 10 первых платящих клиентов. Тестирование и масштабирование: 3+ дисциплины ИТМО, 150+ студентов. B2B: 2–3 партнёра — например, другой вуз или 2–3 хакатона; можно начать с пилотного проекта до продажи. От акселератора нужны менторы по B2B-продажам, выход на вузы и организаторов, юридическая и финансовая упаковка.
-->

## Цель на Акселератор: первые платящие клиенты

<div class="grid3">
<div class="ui-card">
<h3>Тестирование</h3>
масштабирование: 3+ дисциплины ИТМО, 150+ студентов
</div>
<div class="ui-card">
<h3>Клиенты</h3>
10 платящих клиентов
</div>
<div class="ui-card">
<h3>B2B</h3>
2–3 партнёра — например, другой вуз или 2–3 хакатона; можно начать с пилотного проекта до продажи
</div>
</div>

**Что нужно от акселератора:** менторы по B2B-продажам, выход на вузы и организаторов событий, юридическая и финансовая упаковка.

---

<!--
[Q&A] КОМАНДА
Нас шесть человек — полный цикл: продукт, фронтенд, бэкенд, аналитика и организация. Контакты в Telegram на слайде — пишите.
-->

## Команда

<div class="grid3">
<div class="ui-card">
<h3>Плешнев Арсений Вадимович</h3>
<span class="sub">@parse_ny</span>
</div>
<div class="ui-card">
<h3>Карагулов Мансур Рустамович</h3>
<span class="sub">@M1lon86</span>
</div>
<div class="ui-card">
<h3>Хан Ахмади Раман</h3>
<span class="sub">@Raman_Oracle</span>
</div>
<div class="ui-card">
<h3>Терещенко Никита Юрьевич</h3>
<span class="sub">@itmo_enjoyer</span>
</div>
<div class="ui-card">
<h3>Москалец Данила Алексеевич</h3>
<span class="sub">@moskaletsd</span>
</div>
<div class="ui-card">
<h3>Грицкевич Константин Олегович</h3>
<span class="sub">@kgritz</span>
</div>
</div>

---

<!--
[2:45] ФИНАЛ
Спасибо! Мы — работающий продукт с четырёхлетним внедрением в ИТМО и понятной моделью монетизации. Готовы отвечать на вопросы.
-->

<div class="center" style="margin-top:24px">

<h2>Спасибо за внимание!</h2>

<div class="hero-sub">Тренажёр для управления учебными проектами</div>

<div class="hero-tag">EduFlow — все проекты в одном списке</div>

<div class="hero-cta">
<span class="ui-btn ui-btn-dark">Попробовать бесплатно</span>
<span class="ui-btn ui-btn-outline">Связаться с командой</span>
</div>

<em class="hero-goal">Демо: lp.fpin-projects.ru · Telegram: @parse_ny · Готовы к вопросам</em>

</div>

---

<!--
ПРИЛОЖЕНИЕ ДЛЯ Q&A — НЕ ПОКАЗЫВАТЬ В 3 МИНУТАХ
Архитектура: бэкенд на FastAPI со слоями api → services → repository, SQLAlchemy async, Alembic и Unit of Work. Фронтенд — React 18, TypeScript, Vite, TanStack Query. Инфраструктура — PostgreSQL, Docker, nginx edge, CI/CD и мониторинг Prometheus + Grafana. Итого 49 таблиц, 181 эндпоинт, 21 модуль API и 36 страниц.
-->

<!-- _header: "Приложение · Q&A" -->

## Приложение: архитектура

<div class="grid3">
<div class="ui-card">
<h3>Backend</h3>
FastAPI, Python 3.14+, слои api → services → repository<br>
SQLAlchemy (async), Alembic, UoW
</div>
<div class="ui-card">
<h3>Frontend</h3>
React 18 + TypeScript<br>
Vite, TanStack Query, Axios<br>
Tailwind + shadcn/ui
</div>
<div class="ui-card">
<h3>Инфраструктура</h3>
PostgreSQL 15, Docker<br>
Nginx edge, CI/CD<br>
Prometheus + Grafana
</div>
</div>

**49 таблиц** · **181 эндпоинт** · 21 модуль API / 36 страниц. Модули: аутентификация, профиль/резюме, пространства, проекты, канбан, ТЗ, вики, идеи, уведомления, аудит, админ-панель, лендинг (ru/en).

---

<!-- _header: "Приложение · Q&A" -->

<!--
Три независимых слоя доступа: глобальная роль (admin/teacher/manager/member, 52 права), роль в пространстве и права создателя. Права выдаются декларативно через permission_required("entity:action"), раздел /admin/* — только для глобального админа.
-->

## Приложение: роли и права

Три независимых слоя доступа:

1. **Глобальная роль** — `admin` / `teacher` / `manager` / `member`, 52 права.
2. **Роль в пространстве** — назначается ссылкой-приглашением или вручную.
3. **Права создателя** — «кто создал, тот владелец», поверх ролей.

Права выдаются декларативно (`permission_required("entity:action")`) — не в коде обработчиков. `/admin/*` — только глобальный админ.

---

<!-- _header: "Приложение · Q&A" -->

<!--
Данные хранятся на сервере в России. JWT-сессии, сброс пароля по одноразовому токену, подтверждение e-mail, аудит действий и история изменений задач, разграничение доступа по роли и владельцу объекта.
-->

## Приложение: безопасность и данные

- Данные хранятся на сервере в России.
- JWT-сессии, сброс пароля по одноразовому токену, подтверждение e-mail.
- Аудит действий пользователей и история изменений задач.
- Разграничение доступа: роль + владелец объекта.

---

<!-- _header: "Приложение · Q&A" -->

<!--
Заготовки ответов на частые вопросы трекера: почему не Notion/Trello, как зарабатываем, кто первый платящий клиент, данные и 152-ФЗ, кто платит, почему мы, юнит-экономика, что за 3 месяца. Держим под рукой, чтобы отвечать без пауз.
-->

## Приложение: заготовки ответов

| Вопрос трекера                          | Ответ                                                                                                                                        |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Почему не Notion/Trello?                     | Они универсальны; у нас учебный процесс, роли и оценивание из коробки                    |
| Как зарабатываете?                   | Три потока: подписка команд + лицензии вузам + оплата за события                               |
| Кто первый платящий клиент?   | Быстрее всего — организатор события; крупный чек — вуз                                               |
| Что с данными и 152-ФЗ?                | Хостинг в РФ, аудит действий, разграничение доступа                                                    |
| Кто платит — студент или вуз? | Обе модели: B2C-подписка и B2B-лицензия на организацию                                                     |
| Почему вы?                                   | Работающий продукт на ИТМО + понимание процесса изнутри                                            |
| Юнит-экономика?                         | <span class="fill">оценка — уточняем на пилотах</span>                                     |
| Что за 3 месяца?                          | Пилоты в вузах, первые платящие, биллинг, распределение по командам, оценивание |

| Чем лучше Riipen / Practera? | Они про связку «вуз ↔ компания» и за рубежом; мы — рабочий контур команды внутри вуза, данные в РФ, есть сегмент событий |

---

<!-- _header: "Приложение · Q&A" -->

<!--
Сравнение по критериям. Зарубежные PBL- (Riipen/Practera) выигрывают в связке с компаниями, но не дают контура команды внутри вуза и не хостятся в РФ. Российские аналоги — маркетплейс проектов и госпрограмма. Косвенные — трекеры и LMS — не покрывают распределение по командам, канбан+ТЗ+вики и оценивание одновременно. Полное совпадение по всем критериям — только у EduFlow.
-->

## Приложение: сравнение с конкурентами

| Критерий | EduFlow | Riipen / Practera | Trello / Notion | Moodle / Blackboard | GitHub Classroom |
| --- | --- | --- | --- | --- | --- |
| Проектный учебный процесс | <span class="yes">Да</span> | <span class="yes">Да</span> | <span class="no">Нет</span> | <span class="part">Частично</span> | <span class="no">Нет</span> |
| Распределение людей по командам | <span class="yes">Да</span> | <span class="part">Частично</span> | <span class="no">Нет</span> | <span class="no">Нет</span> | <span class="no">Нет</span> |
| Канбан + ТЗ + вики | <span class="yes">Да</span> | <span class="no">Нет</span> | <span class="part">По частям</span> | <span class="no">Нет</span> | <span class="part">Частично</span> |
| Оценивание преподавателем | <span class="part">В роадмапе</span> | <span class="yes">Да</span> | <span class="no">Нет</span> | <span class="part">Да, тяжёлое</span> | <span class="no">Нет</span> |
| Данные в РФ | <span class="yes">Да</span> | <span class="no">Нет</span> | <span class="no">Нет</span> | <span class="no">Зависит</span> | <span class="no">Нет</span> |
| Сегмент событий (хакатоны) | <span class="yes">Да</span> | <span class="no">Нет</span> | <span class="part">Частично</span> | <span class="no">Нет</span> | <span class="no">Нет</span> |
