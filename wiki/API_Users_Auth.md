# API Документация: Пользователи и Авторизация

## 📋 Содержание

1. [Обзор](#обзор)
2. [Роли пользователей](#роли-пользователей)
3. [Процесс авторизации](#процесс-авторизации)
4. [API Эндпоинты](#api-эндпоинты)
   - [Регистрация](#регистрация)
   - [Авторизация](#авторизация)
   - [Управление пользователями](#управление-пользователей)
5. [Схемы данных](#схемы-данных)
6. [Работа с токенами](#работа-с-токенами)
7. [Коды ошибок](#коды-ошибок)
8. [Примеры использования](#примеры-использования)

---

## 🎯 Обзор

Система использует **JWT (JSON Web Tokens)** для аутентификации и авторизации.

### Основные возможности:
- ✅ Регистрация новых пользователей
- ✅ Вход в систему (получение токена)
- ✅ Обновление токена (refresh)
- ✅ Управление пользователями (просмотр, обновление)
- ✅ Ролевая модель (студент/преподаватель)

---

## 👥 Роли пользователей

### Student (Студент)
**Поле в БД:** `role: "student"`

**Права:**
- ✅ Просмотр слотов защиты
- ✅ Запись на защиту
- ✅ Просмотр своего профиля
- ❌ Создание дней/слотов защиты
- ❌ Создание типов проектов

---

### Teacher (Преподаватель)
**Поле в БД:** `role: "teacher"`

**Права:**
- ✅ Все права студента
- ✅ Создание типов проектов
- ✅ Создание дней защиты
- ✅ Создание слотов защиты
- ✅ Просмотр списка всех пользователей

---

## 🔐 Процесс авторизации

### Схема работы с токенами

```
1. Пользователь отправляет email + password
           ↓
2. Сервер проверяет данные
           ↓
3. Сервер возвращает access_token + refresh_token
           ↓
4. Клиент сохраняет токены (localStorage/cookies)
           ↓
5. Клиент добавляет access_token в заголовок Authorization
           ↓
6. Когда access_token истекает → используем refresh_token
```

### Время жизни токенов

- **Access Token:** 30 минут (для запросов к API)
- **Refresh Token:** 7 дней (для обновления access token)

---

## 🚀 API Эндпоинты

**Base URL:** `http://localhost:8000/v1`

### Регистрация

#### 1. Создать пользователя (Регистрация)

```http
POST /v1/users/
```

**Авторизация:** Не требуется (открытый эндпоинт)

**Тело запроса:**
```json
{
  "email": "student@example.com",
  "password_string": "securePassword123",
  "first_name": "Иван",
  "middle_name": "Петрович",
  "last_name": "Иванов",
  "isu_number": 312345,
  "role": "student"
}
```

**Поля:**
- `email` (string, required) — Email пользователя (уникальный)
- `password_string` (string, required) — Пароль (минимум 8 символов)
- `first_name` (string, required) — Имя
- `middle_name` (string, required) — Отчество
- `last_name` (string, optional) — Фамилия
- `isu_number` (integer, optional) — Номер ИСУ
- `role` (string, optional, default="student") — Роль: `"student"` или `"teacher"`

**Ответ (201 Created):**
```json
{
  "id": 1,
  "email": "student@example.com",
  "first_name": "Иван",
  "middle_name": "Петрович",
  "last_name": "Иванов",
  "isu_number": 312345,
  "tg_nickname": null,
  "role": "student"
}
```

**Ошибки:**
- `400` — Email уже используется
- `422` — Неверный формат данных (невалидный email, короткий пароль и т.д.)

**Пример (JavaScript):**
```javascript
const response = await fetch('http://localhost:8000/v1/users/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    email: 'student@example.com',
    password_string: 'securePassword123',
    first_name: 'Иван',
    middle_name: 'Петрович',
    last_name: 'Иванов',
    isu_number: 312345,
    role: 'student'
  })
});

const user = await response.json();
console.log('Пользователь создан:', user.id);
```

---

### Авторизация

#### 2. Вход в систему (Login)

```http
POST /v1/auth/login
```

**Авторизация:** Не требуется

**Тело запроса:**
```json
{
  "email": "student@example.com",
  "password": "securePassword123"
}
```

**Ответ:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Ошибки:**
- `401` — Неверный email или пароль

**Пример (JavaScript):**
```javascript
async function login(email, password) {
  const response = await fetch('http://localhost:8000/v1/auth/login', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ email, password })
  });
  
  if (!response.ok) {
    throw new Error('Неверный email или пароль');
  }
  
  const data = await response.json();
  
  // Сохранить токены
  localStorage.setItem('access_token', data.access_token);
  localStorage.setItem('refresh_token', data.refresh_token);
  
  return data;
}

// Использование
try {
  const tokens = await login('student@example.com', 'securePassword123');
  console.log('Вход выполнен успешно');
} catch (error) {
  console.error('Ошибка входа:', error.message);
}
```

---

#### 3. Обновить токен (Refresh)

```http
POST /v1/auth/refresh
```

**Авторизация:** Не требуется (используется refresh_token)

**Тело запроса:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Ответ:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Ошибки:**
- `401` — Refresh token недействителен или истек

**Пример (JavaScript):**
```javascript
async function refreshAccessToken() {
  const refreshToken = localStorage.getItem('refresh_token');
  
  if (!refreshToken) {
    throw new Error('Refresh token не найден');
  }
  
  const response = await fetch('http://localhost:8000/v1/auth/refresh', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      refresh_token: refreshToken
    })
  });
  
  if (!response.ok) {
    // Refresh token истек, нужно заново войти
    localStorage.clear();
    window.location.href = '/login';
    return;
  }
  
  const data = await response.json();
  localStorage.setItem('access_token', data.access_token);
  
  return data.access_token;
}
```

---

### Управление пользователями

#### 4. Получить текущего пользователя

```http
GET /v1/users/me
```

**Авторизация:** Требуется

**Ответ:**
```json
{
  "id": 1,
  "email": "student@example.com",
  "first_name": "Иван",
  "middle_name": "Петрович",
  "last_name": "Иванов",
  "isu_number": 312345,
  "tg_nickname": null,
  "role": "student"
}
```

**Пример (JavaScript):**
```javascript
async function getCurrentUser() {
  const token = localStorage.getItem('access_token');
  
  const response = await fetch('http://localhost:8000/v1/users/me', {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  
  if (response.status === 401) {
    // Токен истек, попробовать обновить
    await refreshAccessToken();
    return getCurrentUser(); // Повторить запрос
  }
  
  return await response.json();
}
```

---

#### 5. Получить список пользователей

```http
GET /v1/users/?page=1&limit=10
```

**Авторизация:** Требуется

**Query параметры:**
- `page` (integer, default=1) — Номер страницы
- `limit` (integer, default=10, max=100) — Количество элементов

**Ответ:**
```json
{
  "items": [
    {
      "id": 1,
      "email": "student@example.com",
      "first_name": "Иван",
      "middle_name": "Петрович",
      "last_name": "Иванов",
      "isu_number": 312345,
      "tg_nickname": null,
      "role": "student"
    },
    {
      "id": 2,
      "email": "teacher@example.com",
      "first_name": "Петр",
      "middle_name": "Сергеевич",
      "last_name": "Петров",
      "isu_number": 100001,
      "tg_nickname": "@teacher",
      "role": "teacher"
    }
  ],
  "total": 25,
  "page": 1,
  "limit": 10,
  "total_pages": 3
}
```

---

#### 6. Получить пользователя по ID

```http
GET /v1/users/{user_id}
```

**Авторизация:** Требуется

**Ответ:**
```json
{
  "id": 1,
  "email": "student@example.com",
  "first_name": "Иван",
  "middle_name": "Петрович",
  "last_name": "Иванов",
  "isu_number": 312345,
  "tg_nickname": null,
  "role": "student"
}
```

**Ошибки:**
- `404` — Пользователь не найден

---

#### 7. Обновить пользователя

```http
PATCH /v1/users/{user_id}
```

**Авторизация:** Требуется

**Тело запроса (все поля опциональны):**
```json
{
  "first_name": "Иван",
  "last_name": "Иванов",
  "tg_nickname": "@ivan_ivanov",
  "role": "teacher"
}
```

**Ответ:**
```json
{
  "id": 1,
  "email": "student@example.com",
  "first_name": "Иван",
  "middle_name": "Петрович",
  "last_name": "Иванов",
  "isu_number": 312345,
  "tg_nickname": "@ivan_ivanov",
  "role": "teacher"
}
```

**Ошибки:**
- `404` — Пользователь не найден

---

#### 8. Удалить пользователя

```http
DELETE /v1/users/{user_id}
```

**Авторизация:** Требуется

**Ответ (204 No Content):** Пустой ответ

**Ошибки:**
- `404` — Пользователь не найден

---

## 📊 Схемы данных

### UserCreate (Регистрация)

```typescript
{
  email: string;              // Email (уникальный)
  password_string: string;    // Пароль (минимум 8 символов)
  first_name: string;         // Имя
  middle_name: string;        // Отчество
  last_name?: string;         // Фамилия (опционально)
  isu_number?: number;        // Номер ИСУ (опционально)
  role?: "student" | "teacher"; // Роль (default: "student")
}
```

### UserFull (Полная информация)

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

### UserUpdate (Обновление)

```typescript
{
  email?: string;
  first_name?: string;
  middle_name?: string;
  last_name?: string;
  isu_number?: number;
  tg_nickname?: string;
  role?: "student" | "teacher";
}
```

### AuthRequest (Вход)

```typescript
{
  email: string;
  password: string;
}
```

### TokenPair (Токены)

```typescript
{
  access_token: string;
  refresh_token?: string;  // Только при логине
  token_type: "bearer";
}
```

---

## 🔑 Работа с токенами

### Добавление токена в запросы

**Все защищенные эндпоинты требуют заголовок:**

```http
Authorization: Bearer <access_token>
```

**Пример:**
```javascript
const token = localStorage.getItem('access_token');

fetch('/v1/users/me', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
});
```

---

### Автоматическое обновление токена

Создайте wrapper для fetch с автоматическим обновлением токена:

```javascript
async function apiRequest(url, options = {}) {
  const token = localStorage.getItem('access_token');
  
  // Добавить токен к запросу
  const headers = {
    ...options.headers,
    'Authorization': `Bearer ${token}`
  };
  
  let response = await fetch(url, { ...options, headers });
  
  // Если 401 - токен истек
  if (response.status === 401) {
    console.log('Token expired, refreshing...');
    
    // Попытаться обновить токен
    const newToken = await refreshAccessToken();
    
    if (newToken) {
      // Повторить запрос с новым токеном
      headers.Authorization = `Bearer ${newToken}`;
      response = await fetch(url, { ...options, headers });
    } else {
      // Refresh token тоже истек - перенаправить на логин
      window.location.href = '/login';
      return;
    }
  }
  
  return response;
}

// Использование
const response = await apiRequest('/v1/users/me');
const user = await response.json();
```

---

### Interceptor для Axios (если используете)

```javascript
import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000'
});

// Request interceptor
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    
    // Если 401 и это не повторный запрос
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      
      try {
        const newToken = await refreshAccessToken();
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return api(originalRequest);
      } catch (refreshError) {
        // Refresh failed, redirect to login
        localStorage.clear();
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }
    
    return Promise.reject(error);
  }
);

export default api;

// Использование
import api from './api';

const user = await api.get('/v1/users/me');
```

---

## ⚠️ Коды ошибок

### 400 Bad Request
**Причины:**
- Email уже используется
- Неверный формат данных

**Пример:**
```json
{
  "detail": "User with this email already exists"
}
```

---

### 401 Unauthorized
**Причины:**
- Неверный email или пароль (при логине)
- Токен не передан или недействителен
- Токен истек

**Решение:**
1. При логине: проверить правильность email/пароля
2. При запросе: проверить что токен передан в заголовке
3. Если токен истек: использовать refresh token

---

### 403 Forbidden
**Причина:** Недостаточно прав

**Пример:** Студент пытается создать день защиты

**Сообщение:**
```json
{
  "detail": "Only teachers can perform this action"
}
```

---

### 404 Not Found
**Причина:** Пользователь не найден

---

### 422 Unprocessable Entity
**Причина:** Неверный формат данных

**Пример:**
```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "value_error.email"
    },
    {
      "loc": ["body", "password_string"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## 💻 Примеры использования

### Полный цикл авторизации

```javascript
// 1. Регистрация
async function register(userData) {
  const response = await fetch('http://localhost:8000/v1/users/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(userData)
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail);
  }
  
  return await response.json();
}

// 2. Вход
async function login(email, password) {
  const response = await fetch('http://localhost:8000/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  });
  
  if (!response.ok) {
    throw new Error('Неверный email или пароль');
  }
  
  const tokens = await response.json();
  
  localStorage.setItem('access_token', tokens.access_token);
  localStorage.setItem('refresh_token', tokens.refresh_token);
  
  return tokens;
}

// 3. Получить текущего пользователя
async function getCurrentUser() {
  const token = localStorage.getItem('access_token');
  
  const response = await fetch('http://localhost:8000/v1/users/me', {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  
  if (!response.ok) {
    throw new Error('Не удалось получить данные пользователя');
  }
  
  return await response.json();
}

// 4. Обновить токен
async function refreshToken() {
  const refreshToken = localStorage.getItem('refresh_token');
  
  const response = await fetch('http://localhost:8000/v1/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken })
  });
  
  if (!response.ok) {
    // Refresh token истек - перелогин
    logout();
    window.location.href = '/login';
    return null;
  }
  
  const data = await response.json();
  localStorage.setItem('access_token', data.access_token);
  
  return data.access_token;
}

// 5. Выход
function logout() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  window.location.href = '/login';
}

// ИСПОЛЬЗОВАНИЕ
try {
  // Регистрация студента
  await register({
    email: 'student@example.com',
    password_string: 'securePass123',
    first_name: 'Иван',
    middle_name: 'Петрович',
    role: 'student'
  });
  
  // Вход
  await login('student@example.com', 'securePass123');
  
  // Получить данные пользователя
  const user = await getCurrentUser();
  console.log('Добро пожаловать,', user.first_name);
  console.log('Ваша роль:', user.role);
  
} catch (error) {
  console.error('Ошибка:', error.message);
}
```

---

### React Hook для авторизации

```javascript
import { useState, useEffect } from 'react';

function useAuth() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    checkAuth();
  }, []);
  
  async function checkAuth() {
    const token = localStorage.getItem('access_token');
    
    if (!token) {
      setLoading(false);
      return;
    }
    
    try {
      const response = await fetch('http://localhost:8000/v1/users/me', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
      } else if (response.status === 401) {
        // Попытаться обновить токен
        const newToken = await refreshToken();
        if (newToken) {
          await checkAuth(); // Повторить проверку
        }
      }
    } catch (error) {
      console.error('Auth check failed:', error);
    } finally {
      setLoading(false);
    }
  }
  
  async function login(email, password) {
    const response = await fetch('http://localhost:8000/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    
    if (!response.ok) {
      throw new Error('Неверный email или пароль');
    }
    
    const tokens = await response.json();
    localStorage.setItem('access_token', tokens.access_token);
    localStorage.setItem('refresh_token', tokens.refresh_token);
    
    await checkAuth();
  }
  
  function logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    setUser(null);
  }
  
  return {
    user,
    loading,
    login,
    logout,
    isAuthenticated: !!user,
    isTeacher: user?.role === 'teacher',
    isStudent: user?.role === 'student'
  };
}

// Использование в компоненте
function App() {
  const { user, loading, isTeacher, login, logout } = useAuth();
  
  if (loading) {
    return <div>Загрузка...</div>;
  }
  
  if (!user) {
    return <LoginForm onLogin={login} />;
  }
  
  return (
    <div>
      <h1>Привет, {user.first_name}!</h1>
      <p>Роль: {user.role}</p>
      
      {isTeacher && (
        <button>Создать день защиты</button>
      )}
      
      <button onClick={logout}>Выйти</button>
    </div>
  );
}
```

---

### Protected Route (React Router)

```javascript
import { Navigate } from 'react-router-dom';
import { useAuth } from './useAuth';

function ProtectedRoute({ children, requireTeacher = false }) {
  const { user, loading } = useAuth();
  
  if (loading) {
    return <div>Загрузка...</div>;
  }
  
  if (!user) {
    return <Navigate to="/login" />;
  }
  
  if (requireTeacher && user.role !== 'teacher') {
    return <Navigate to="/forbidden" />;
  }
  
  return children;
}

// Использование
<Routes>
  <Route path="/login" element={<LoginPage />} />
  
  <Route 
    path="/profile" 
    element={
      <ProtectedRoute>
        <ProfilePage />
      </ProtectedRoute>
    } 
  />
  
  <Route 
    path="/admin/create-defense-day" 
    element={
      <ProtectedRoute requireTeacher>
        <CreateDefenseDayPage />
      </ProtectedRoute>
    } 
  />
</Routes>
```

---

## 💡 Рекомендации

### 1. Безопасное хранение токенов

**Варианты:**

1. **localStorage** (простой, но менее безопасный)
```javascript
localStorage.setItem('access_token', token);
```

2. **httpOnly cookies** (более безопасно, но требует настройки на бэкенде)
```javascript
// Backend должен установить cookie при логине
// Frontend автоматически отправляет cookie с каждым запросом
```

3. **sessionStorage** (токен удаляется при закрытии вкладки)
```javascript
sessionStorage.setItem('access_token', token);
```

**Рекомендация:** Для продакшна использовать httpOnly cookies.

---

### 2. Проверка роли на фронтенде

```javascript
function canCreateDefenseDay(user) {
  return user && user.role === 'teacher';
}

// В компоненте
{canCreateDefenseDay(user) && (
  <button onClick={createDefenseDay}>
    Создать день защиты
  </button>
)}
```

**Важно:** Проверка на фронтенде только для UX. Бэкенд всегда проверяет права дополнительно!

---

### 3. Обработка истекших токенов

```javascript
// Создать глобальный обработчик
window.addEventListener('tokenExpired', () => {
  // Показать уведомление
  alert('Сессия истекла. Пожалуйста, войдите снова.');
  
  // Перенаправить на логин
  window.location.href = '/login';
});

// Использовать в API wrapper
if (response.status === 401) {
  window.dispatchEvent(new Event('tokenExpired'));
}
```

---

## 🔗 Связанные документы

- [API_Defense_System.md](./API_Defense_System.md) — Система записи на защиту
- [README.md](../README.md) — Основная документация проекта

---

**Дата создания:** 2026-02-14  
**Версия API:** v1  
**Автор:** Backend Team
