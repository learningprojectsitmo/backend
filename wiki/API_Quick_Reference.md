# API Quick Reference — Быстрая справка

Краткая шпаргалка по всем эндпоинтам для фронтенд-разработчиков.

---

## 🔐 Авторизация

### Регистрация и вход

```http
# Регистрация (открытый)
POST /v1/users/
Body: { email, password_string, first_name, middle_name, role }

# Вход (открытый)
POST /v1/auth/login
Body: { email, password }
→ Returns: { access_token, refresh_token }

# Обновить токен (открытый)
POST /v1/auth/refresh
Body: { refresh_token }
→ Returns: { access_token }

# Текущий пользователь (auth)
GET /v1/users/me
→ Returns: UserFull
```

---

## 👥 Пользователи

```http
# Список пользователей (auth)
GET /v1/users/?page=1&limit=10

# Пользователь по ID (auth)
GET /v1/users/{user_id}

# Обновить пользователя (auth)
PATCH /v1/users/{user_id}
Body: { first_name?, last_name?, role?, ... }

# Удалить пользователя (auth)
DELETE /v1/users/{user_id}
```

---

## 🎯 Типы проектов

```http
# Все типы (auth, any role)
GET /v1/defense/project-types
→ Returns: { items: [ProjectTypeFull] }

# Создать тип (auth, teacher only)
POST /v1/defense/project-types
Body: { name, description? }
→ Returns: ProjectTypeFull
```

---

## 📅 Дни защиты

```http
# Список дней (auth, any role)
GET /v1/defense/days?page=1&limit=10
→ Returns: { items, total, page, limit, total_pages }

# День по ID (auth, any role)
GET /v1/defense/days/{day_id}
→ Returns: DefenseDayFull

# Создать день (auth, teacher only)
POST /v1/defense/days
Body: { date, max_slots, first_slot_time }
→ Returns: DefenseDayFull
```

---

## ⏰ Слоты защиты

```http
# Список слотов с фильтрами (auth, any role)
GET /v1/defense/slots?page=1&limit=10&date=2026-03-15&project_type_id=1
→ Returns: { items: [DefenseSlotListItem], total, page, limit, total_pages }

# Слот по ID (auth, any role)
GET /v1/defense/slots/{slot_id}
→ Returns: DefenseSlotFull

# Создать слот (auth, teacher only)
POST /v1/defense/slots
Body: { defense_day_id, slot_index, title, project_type_id, location?, capacity }
→ Returns: DefenseSlotFull

# Записаться на слот (auth, any role)
POST /v1/defense/slots/{slot_id}/register
Body: {}
→ Returns: DefenseRegistrationFull
```

---

## 📋 Типичные заголовки

```http
# Для всех защищенных эндпоинтов
Authorization: Bearer {access_token}

# Для POST/PATCH запросов
Content-Type: application/json
```

---

## 🔑 Роли и права

| Действие | Student | Teacher |
|----------|---------|---------|
| Просмотр типов/дней/слотов | ✅ | ✅ |
| Создать тип проекта | ❌ | ✅ |
| Создать день защиты | ❌ | ✅ |
| Создать слот | ❌ | ✅ |
| Записаться на слот | ✅ | ✅ |

---

## ⚠️ Коды ошибок

| Код | Значение | Причина |
|-----|----------|---------|
| 400 | Bad Request | Неверные данные, слот заполнен, дубликат |
| 401 | Unauthorized | Токен не передан/недействителен/истек |
| 403 | Forbidden | Недостаточно прав (не teacher) |
| 404 | Not Found | Ресурс не найден |
| 422 | Unprocessable Entity | Неверный формат данных (Pydantic) |

---

## 💻 Примеры fetch

### Создать тип проекта (teacher)
```javascript
fetch('/v1/defense/project-types', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    name: 'course',
    description: 'Курсовая работа'
  })
})
```

### Создать день защиты (teacher)
```javascript
fetch('/v1/defense/days', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    date: '2026-03-15',
    max_slots: 10,
    first_slot_time: '10:00:00'
  })
})
```

### Создать слот (teacher)
```javascript
fetch('/v1/defense/slots', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    defense_day_id: 1,
    slot_index: 0,
    title: 'Защита курсовых',
    project_type_id: 1,
    location: 'Ауд. 101',
    capacity: 5
  })
})
```

### Получить слоты с фильтрами
```javascript
fetch('/v1/defense/slots?date=2026-03-15&project_type_id=1', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
})
```

### Записаться на слот (student)
```javascript
fetch('/v1/defense/slots/1/register', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({})
})
```

---

## 🎯 Типичные сценарии

### 1. Полный цикл: Преподаватель создает расписание

```javascript
// 1. Создать тип проекта
const type = await createProjectType({ name: 'course', ... });

// 2. Создать день
const day = await createDefenseDay({ date: '2026-03-15', ... });

// 3. Создать несколько слотов
for (let i = 0; i < 3; i++) {
  await createSlot({
    defense_day_id: day.id,
    slot_index: i,
    project_type_id: type.id,
    ...
  });
}
```

### 2. Студент записывается на защиту

```javascript
// 1. Получить типы проектов
const types = await getProjectTypes();

// 2. Отфильтровать слоты
const slots = await getSlots({
  date: '2026-03-15',
  project_type_id: 1
});

// 3. Записаться
await registerToSlot(slots[0].id);
```

---

## 📊 Основные типы данных

### ProjectTypeFull
```typescript
{
  id: number;
  name: string;
  description: string | null;
  created_at: string;
}
```

### DefenseDayFull
```typescript
{
  id: number;
  date: string;          // "2026-03-15"
  max_slots: number;
  first_slot_time: string; // "10:00:00"
  created_at: string;
  updated_at: string;
}
```

### DefenseSlotFull
```typescript
{
  id: number;
  defense_day_id: number;
  slot_index: number;
  title: string;
  project_type: {
    id: number;
    name: string;
  };
  start_at: string;      // ISO 8601
  end_at: string;        // ISO 8601
  location: string | null;
  capacity: number;
  created_at: string;
  updated_at: string;
}
```

### DefenseRegistrationFull
```typescript
{
  id: number;
  slot_id: number;
  user_id: number;
  created_at: string;
}
```

### UserFull
```typescript
{
  id: number;
  email: string;
  first_name: string;
  middle_name: string;
  last_name: string | null;
  isu_number: number | null;
  tg_nickname: string | null;
  role: "student" | "teacher";
}
```

---

## 🔗 Полная документация

- [API_Defense_System.md](./API_Defense_System.md) — Подробная документация системы защиты
- [API_Users_Auth.md](./API_Users_Auth.md) — Подробная документация авторизации

---

**Base URL:** `http://localhost:8000`  
**API Version:** v1  
**Last Updated:** 2026-02-14
