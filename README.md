# FastAPI CRUD с SQLAlchemy, BackgroundTasks и Redis Caching

## Описание проекта

Полнофункциональное FastAPI приложение для управления студентами с интеграцией:
- ✅ SQLAlchemy для работы с БД (SQLite)
- ✅ BackgroundTasks для асинхронных операций (импорт CSV, массовое удаление)
- ✅ Redis для кеширования результатов GET запросов
- ✅ OAuth2 аутентификация и авторизация (роли: reader, admin)

## Требования

- Python 3.8+
- Redis (для кеширования)

## Установка зависимостей

```bash
pip install -r requirements.txt
```

## Запуск Redis (обязательно перед запуском приложения)

### На Windows (если установлен Redis):
```bash
redis-server
```

### Или используйте Docker:
```bash
docker run -p 6379:6379 redis:latest
```

## Запуск приложения

```bash
uvicorn my_api:app --reload --port 8000
```

Приложение будет доступно по адресу: `http://localhost:8000`

## Документация API

Swagger UI: `http://localhost:8000/docs`
ReDoc: `http://localhost:8000/redoc`

## Основные эндпоинты

### Аутентификация

- `POST /auth/register` - Регистрация нового пользователя
- `POST /auth/login` - Вход в систему (получение токена)
- `POST /auth/logout` - Выход из системы

### CRUD операции

- `GET /students` - Получить всех студентов (с кешированием, требуется аутентификация)
- `GET /students/{id}` - Получить студента по ID
- `POST /students` - Создать нового студента (требуется роль admin)
- `PUT /students/{id}` - Обновить данные студента (требуется роль admin)
- `DELETE /students/{id}` - Удалить студента (требуется роль admin)

### Фоновые задачи

- `POST /import-csv` - Загрузить студентов из CSV файла (фоновая задача, требуется роль admin)
  
  Параметры:
  - `csv_path` - путь к CSV файлу
  
  CSV должен содержать колонки: `Фамилия, Имя, Факультет, Курс, Оценка`

- `POST /delete-students` - Удалить студентов по списку ID (фоновая задача, требуется роль admin)
  
  Параметры:
  - `student_ids` - список ID студентов для удаления

### Аналитика (с кешированием)

- `GET /students-by-faculty/{faculty_name}` - Получить студентов по факультету
- `GET /average-grade/{faculty_name}` - Получить среднюю оценку по факультету
- `GET /low-grades?course_name=...&min_grade=30` - Получить студентов с низкими оценками

## Пример использования

### 1. Регистрация пользователя

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin_user",
    "password": "admin123",
    "role": "admin"
  }'
```

### 2. Вход в систему

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin_user&password=admin123"
```

### 3. Импорт CSV (фоновая задача)

```bash
curl -X POST http://localhost:8000/import-csv \
  -H "Authorization: Bearer <YOUR_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"csv_path": "students.csv"}'
```

### 4. Получить всех студентов (с кешем)

```bash
curl -X GET http://localhost:8000/students \
  -H "Authorization: Bearer <YOUR_TOKEN>"
```

### 5. Удалить студентов по списку (фоновая задача)

```bash
curl -X POST http://localhost:8000/delete-students \
  -H "Authorization: Bearer <YOUR_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"student_ids": [1, 2, 3]}'
```

## Кеширование

Результаты всех GET запросов кешируются в Redis на 300 секунд (5 минут).
При выполнении операций CREATE, UPDATE, DELETE кеш автоматически очищается.

## Слои безопасности

- OAuth2 аутентификация со токенами
- Разделение ролей:
  - `reader` - только просмотр данных
  - `admin` - полный доступ (создание, редактирование, удаление)

## Структура БД

**Таблица: students**

| Поле | Тип | Описание |
|------|-----|---------|
| id | Integer | Первичный ключ |
| last_name | String | Фамилия |
| first_name | String | Имя |
| faculty | String | Факультет |
| course | String | Курс/Предмет |
| grade | Float | Оценка |

## Логирование

Фоновые задачи логируют свой прогресс в консоль:
- Успешная загрузка CSV: "Успешно загружено N студентов..."
- Успешное удаление: "Успешно удалено N студентов..."

## Примечания

- Кеш Redis должен быть доступен по адресу `localhost:6379`
- CSV файл должен содержать правильные названия колонок на русском
- Оценки должны быть числовыми значениями
- При ошибке в фоновой задаче будет выведено сообщение об ошибке в логах

