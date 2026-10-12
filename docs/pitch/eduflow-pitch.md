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
Дизайн слайдов повторяет UI сайта (frontend/src/index.css, ProjectCard, KanbanTask,
column-styles, Button). Мокапы нарисованы CSS-компонентами — вставлять скриншоты не нужно.
Оценочные цифры помечены «оценка (уточнить)» — заменить на реальные перед выступлением.
Тайминг: слайды 1–13 = 3 минуты. Всё после «Приложение» — только для Q&A, не показывать.
-->

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
section[data-marpit-pagination="17"] {
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
section[data-marpit-pagination="15"] {
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
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }

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
.hero-cta { margin-top: 24px; display: flex; justify-content: center; gap: 10px; }
.hero-author { margin-top: 26px; font-size: 15px; font-weight: 600; color: var(--gray-900); }
.hero-goal { display: block; margin: 8px auto 0; max-width: 480px; font-size: 13px; color: var(--app-muted); }
</style>

<!-- _paginate: false -->
<!-- _header: "" -->
<!-- _footer: "" -->
<!--
[0:00–0:10] Открытие. Как хиро лендинга: бейдж, слоган, кнопки. Сразу назвать цель.
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
[0:10–0:50] ПРОБЛЕМА. Три карточки в стиле сайта. Рассказывать, не читать.
-->

## Проблема

<div class="grid3">
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
</div>

**Цена ошибки растёт с масштабом:** слабый состав, дубли ролей и сорванные сроки — уже во всём потоке, а не в одном проекте.

---

<!--
[0:50–1:05] РЫНОК И ЦА. Три сегмента-карточки, first market. Цифры — оценка.
-->

## Кому и какой рынок

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

**First market — ИТМО.** Дальше — вузы с проектным обучением и организаторы хакатонов.

<span class="fill">Оценка (уточнить): TAM — ≈1 200 вузов РФ ≈10–15 млрд ₽/год · SAM — ≈300 вузов ≈1,5–2 млрд ₽ · SOM — ИТМО + 2–3 пилота ≈10–20 млн ₽</span>

---

<!--
[1:05–1:30] ПРОДУКТ. Два реальных экрана, нарисованные UI-элементами сайта.
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

<span class="sub">**Как это работает:** пространство → проект с этапами и командой → доска с задачами, ТЗ и вики. Отклики, приглашения по ссылке и роли уровня проекта уже в продукте.</span>

---

<!--
[1:30–1:50] ВОЗМОЖНОСТИ. Три группы, стиль сайта, маркеры-точки как в списках функций.
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
<li>История изменений и аудит действий</li>
</ul>
</div>
</div>

**Уже работает:** регистрация с подтверждением e-mail, профиль и портфолио, резюме с навыками, пространства, проекты с этапами, канбан, ТЗ с согласованием и вики.

---

<!--
[1:50–2:05] КОНКУРЕНТЫ. Таблица, «да/нет» — пилюли как статусы в приложении.
-->

## Чем отличаемся

| Критерий | EduFlow | Trello / Notion | Moodle / Blackboard |
|---|---|---|---|
| Проектный учебный процесс | <span class="yes">Да</span> | <span class="no">Нет</span> | <span class="part">Частично</span> |
| Распределение людей по командам | <span class="yes">Да</span> | <span class="no">Нет</span> | <span class="no">Нет</span> |
| Роли и права на уровне проекта | <span class="yes">Да</span> | <span class="no">Базовые</span> | <span class="no">Курсовые</span> |
| Оценивание преподавателем | <span class="part">В роадмапе</span> | <span class="no">Нет</span> | <span class="no">Да, тяжёлое</span> |
| Единый список + канбан + ТЗ + вики | <span class="yes">Да</span> | <span class="no">По частям</span> | <span class="no">Нет</span> |
| Данные в РФ | <span class="yes">Да</span> | <span class="no">Нет</span> | <span class="no">Зависит</span> |

_Мы — вертикальное решение под проектное обучение, а не универсальный таск-трекер._

---

<!--
[2:05–2:20] БИЗНЕС-МОДЕЛЬ · ПОТОКИ. Три потока (гибрид). Цены — оценка.
-->

## Бизнес-модель: три потока выручки

<div class="grid3">
<div class="ui-card">
<h3><span class="pill pill-inprogress" style="margin-right:8px">1</span> Подписка команд</h3>
Команды и руководители платят за расширенные лимиты и возможности.
<p style="margin:10px 0 0"><span class="fill">≈490 ₽/мес за команду (уточнить)</span></p>
</div>
<div class="ui-card">
<h3><span class="pill pill-review" style="margin-right:8px">2</span> Лицензии вузам</h3>
Вуз платит за места, администрирование и оценивание.
<p style="margin:10px 0 0"><span class="fill">от 150 000 ₽/год за вуз (уточнить)</span></p>
</div>
<div class="ui-card">
<h3><span class="pill pill-planned" style="margin-right:8px">3</span> События</h3>
Хакатоны, акселераторы, олимпиады — оплата за мероприятие.
<p style="margin:10px 0 0"><span class="fill">от 50 000 ₽ за событие (уточнить)</span></p>
</div>
</div>

**Почему три сразу:** бесплатный вход (B2C) даёт трафик, B2B-лицензии — крупный чек, события — быстрый первый платящий клиент и валидация спроса.

---

<!--
[2:20–2:35] БИЗНЕС-МОДЕЛЬ · ТАРИФЫ. Пакеты + воронка.
-->

## Бизнес-модель: тарифы

| Пакет | Для кого | Что входит | Цена |
|---|---|---|---|
| **Free** | команды, студенты | пространства, проекты, канбан, ТЗ, вики | **0 ₽** |
| **Team** | руководители, продукт | расширенные лимиты, приватные пространства, приоритет | <span class="fill">≈490 ₽/мес</span> |
| **Вуз** | вуз, факультет | места, администрирование, оценивание, SSO | <span class="fill">от 150 000 ₽/год</span> |
| **Событие** | хакатон, акселератор | проект на событие, роли жюри, дедлайны | <span class="fill">от 50 000 ₽</span> |

_Воронка:_ **Free → Team (B2C) → Вуз / Событие (B2B).**

---

<!--
[2:35–2:50] БИЗНЕС-МОДЕЛЬ · ЮНИТ-ЭКОНОМИКА + ВОРОНКА + GTM.
-->

## Бизнес-модель: юнит-экономика и воронка

<div class="grid">
<div class="ui-card">
<h3>Воронка</h3>
Регистрация → активная команда → платящий клиент
<ul>
<li><strong>Free</strong> — минус ограничений на входе</li>
<li><strong>Team</strong> — подписка команды</li>
<li><strong>Вуз / Событие</strong> — B2B-лицензия</li>
</ul>
</div>
<div class="ui-card">
<h3>Метрики <span class="sub">(оценка — уточнить)</span></h3>
<ul>
<li>ARPU: <span class="fill">…</span></li>
<li>CAC: <span class="fill">…</span></li>
<li>LTV: <span class="fill">…</span></li>
<li>LTV / CAC: <span class="fill">…</span></li>
<li>Payback: <span class="fill">… мес</span></li>
</ul>
</div>
</div>

**Каналы первых продаж:** пилот в ИТМО → преподаватели-амбассадоры → организаторы хакатонов → выход в другие вузы.

---

<!--
[2:50–3:00] СТАТУС. Продукт не идея, а работающий сервис. Цифры в стиле сайта.
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
<h3>Платформа</h3>
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
Тракшн: <span class="fill">оценка — пилот на 1–2 факультетах ИТМО, первые команды (уточнить)</span>
</div>
</div>

---

<!--
[3:00–3:05] РОАДМАП. Сжато, 5 пунктов, стиль сайта.
-->

## Роадмап развития

<div class="grid" style="grid-template-columns:1fr 1fr">
<div>
<ul class="ui-card" style="list-style:none; margin:0">
<li><strong>Стабильность</strong> — ключевые сценарии до прод-качества</li>
<li><strong>Распределение по командам</strong> — подбор по навыкам и ролям, автораспределение</li>
<li><strong>Оценивание</strong> — от критериев приёмки к оценке преподавателя</li>
</ul>
</div>
<div>
<ul class="ui-card" style="list-style:none; margin:0">
<li><strong>Интеграции</strong> — GitHub, ITMO ID, платёжный провайдер</li>
<li><strong>Продажи</strong> — лендинг под B2B, пилоты в вузах, биллинг</li>
<li><strong>Качество</strong> — производительность БД на росте данных</li>
</ul>
</div>
</div>

---

<!--
[3:05–3:12] ЦЕЛЬ НА АКСЕЛЕРАТОР. Первые платящие клиенты.
-->

## Цель на Акселератор: первые платящие клиенты

<div class="grid3">
<div class="ui-card">
<h3>Клиенты</h3>
<span class="fill">3–5 платящих: 2 вуза + 3 события (уточнить)</span>
</div>
<div class="ui-card">
<h3>Выручка</h3>
первый <span class="fill">MRR … (уточнить)</span>
</div>
<div class="ui-card">
<h3>Валидация</h3>
<span class="fill">пилот в 3 дисциплинах ИТМО, 150+ студентов (уточнить)</span>
</div>
</div>

**Что нужно от акселератора:** менторы по B2B-продажам, выход на вузы и организаторов событий, юридическая и финансовая упаковка.

---

<!--
[3:12–3:15] ФИНАЛ. Слоган, кнопки, контакты.
-->

<div class="center" style="margin-top:60px">

<h1 style="margin-bottom:24px">Спасибо! Вопросы?</h1>

<div style="margin-top:24px">
<span class="ui-btn ui-btn-dark">Попробовать бесплатно</span>
<span class="ui-btn ui-btn-outline" style="margin-left:10px">Войти</span>
</div>

<p style="margin-top:36px; font-weight:600">Афанасьев Антон · orderkworinaa@gmail.com</p>

</div>

---
<!--
=== ПРИЛОЖЕНИЕ ДЛЯ Q&A — НЕ ПОКАЗЫВАТЬ В 3 МИНУТАХ ===
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
| Как зарабатываете? | Три потока: подписка команд + лицензии вузам + оплата за события |
| Кто первый платящий клиент? | Быстрее всего — организатор события; крупный чек — вуз |
| Что с данными и 152-ФЗ? | Хостинг в РФ, аудит действий, разграничение доступа |
| Кто платит — студент или вуз? | Обе модели: B2C-подписка и B2B-лицензия на организацию |
| Почему вы? | Работающий продукт на ИТМО + понимание процесса изнутри |
| Юнит-экономика? | <span class="fill">оценка — см. слайд «юнит-экономика» (уточнить)</span> |
| Что за 3 месяца? | Пилоты в вузах, первые платящие, биллинг, распределение по командам, оценивание |