# News API

[![CI](https://github.com/zyll11/news-api/actions/workflows/ci.yml/badge.svg)](https://github.com/zyll11/news-api/actions/workflows/ci.yml)

Асинхронный REST API новостного портала на FastAPI: новости, комментарии, ролевая модель,
JWT-аутентификация с ротацией refresh-токенов, вход через GitHub OAuth и кэширование в Redis.

Проект вырос из учебной лабораторной по веб-разработке (ИТМО) и был переписан с упором на
безопасность, асинхронность и тестируемость.

## Возможности

- **Аутентификация**: регистрация, вход по email/паролю, короткоживущий access JWT
  и непрозрачный refresh-токен с ротацией при каждом обновлении.
- **Защита сессий**: в БД хранится только SHA-256 хэш refresh-токена; повторное использование
  уже ротированного токена расценивается как кража и отзывает все сессии пользователя;
  список активных сессий (устройство, IP), выход с одного или со всех устройств,
  лимит одновременных сессий.
- **Вход через GitHub** (OAuth 2.0 authorization code): одноразовый `state` в Redis против CSRF,
  привязка к существующему аккаунту только по подтверждённому email.
- **Ролевая модель**: читатель, автор, администратор. Правила доступа собраны в одном модуле,
  а не размазаны по эндпоинтам.
- **Защита от перебора паролей**: лимит неудачных попыток входа на пару IP + email
  (Redis, ответ `429` с `Retry-After`); одинаковые ответ и время для несуществующего email
  и неверного пароля.
- **Кэш новостей в Redis**: read-through кэш карточек и страниц списка, инвалидация при
  изменениях через версионирование ключей; при недоступности Redis API продолжает работать.
- Пагинация, единый формат ошибок, health/readiness-проверки, логирование запросов
  с `X-Request-ID` (без тел и токенов).

## Стек

Python 3.11+ · FastAPI · SQLAlchemy 2.0 (async) · asyncpg · PostgreSQL · Alembic · Redis ·
Pydantic v2 · PyJWT · Argon2 · httpx · pytest · Docker Compose · GitHub Actions · Ruff

## Архитектура

```mermaid
flowchart LR
    C[Клиент] --> R[Роутеры /api/v1]
    R --> D[Зависимости: сессия БД, текущий пользователь]
    R --> S[Сервисы: auth, news, comments, users]
    S --> P[Политики доступа]
    S --> Rep[Репозитории]
    S --> Cache[(Redis: кэш, rate limit, OAuth state)]
    S --> GH[GitHub OAuth]
    Rep --> DB[(PostgreSQL)]
```

```
app/
├── api/            # роутеры и зависимости FastAPI (HTTP-слой, без бизнес-логики)
├── core/           # настройки, безопасность, ошибки, логирование
├── db/             # базовая модель, движок и фабрика сессий
├── models/         # ORM-модели
├── repositories/   # доступ к данным
├── schemas/        # Pydantic-схемы запросов и ответов
├── services/       # бизнес-логика, кэш, rate limit, клиент GitHub
├── cli.py          # create-admin, seed
└── main.py         # фабрика приложения
alembic/            # миграции
tests/              # pytest + httpx, ~60 тестов
```

Сервисы получают зависимости через конструктор, а приложение собирается фабрикой
`create_app()`. Поэтому в тестах БД, Redis и GitHub подменяются без патчей.

## Быстрый старт (Docker)

```bash
python scripts/init_env.py        # создаёт .env со случайными секретами
docker compose up --build -d
docker compose exec api python -m app.cli seed   # демо-данные (необязательно)
```

Документация API: http://localhost:8000/docs

Демо-пользователи после `seed` (пароль `Password123`): `admin@example.com` (админ),
`alice@example.com` (автор), `bob@example.com` (читатель). Своего администратора можно
создать командой `python -m app.cli create-admin --email you@example.com`.

## Локальная разработка

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python scripts/init_env.py
docker compose up -d db redis       # Postgres на localhost:5433, Redis на 6380
alembic upgrade head
uvicorn app.main:create_app --factory --reload
```

## Тесты и линтер

```bash
pytest --cov                     # по умолчанию SQLite в памяти, сервисы не нужны
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5433/test pytest   # на PostgreSQL
ruff check . && ruff format --check .
```

В CI тесты запускаются на PostgreSQL и SQLite, а также проверяется, что миграции
применяются и соответствуют моделям (`alembic check`).

## Основные эндпоинты

| Метод | Путь | Доступ |
|---|---|---|
| POST | `/api/v1/auth/register` | все |
| POST | `/api/v1/auth/login` | все |
| POST | `/api/v1/auth/refresh` | по refresh-токену |
| POST | `/api/v1/auth/logout`, `/logout-all` | по токену |
| GET, DELETE | `/api/v1/auth/sessions[/{id}]` | владелец |
| GET | `/api/v1/auth/github/login`, `/github/callback` | все |
| GET, PATCH | `/api/v1/users/me` | авторизованный |
| GET | `/api/v1/users` | админ |
| PATCH | `/api/v1/users/{id}/roles` | админ |
| GET | `/api/v1/news`, `/news/{id}` | все |
| POST | `/api/v1/news` | автор, админ |
| PATCH, DELETE | `/api/v1/news/{id}` | владелец, админ |
| GET | `/api/v1/news/{id}/comments` | все |
| POST | `/api/v1/news/{id}/comments` | авторизованный |
| PATCH, DELETE | `/api/v1/comments/{id}` | владелец, админ |
| GET | `/health`, `/health/ready` | все |

Ошибки возвращаются в едином формате:
`{"error": {"code": "not_found", "message": "News not found"}}`.

## Решения по безопасности

- Пароли хэшируются Argon2id; хэш автоматически обновляется при смене параметров.
- Access-токен живёт 15 минут, содержит `type` и `jti`; токены другого типа отклоняются.
- Refresh-токен непрозрачный (не JWT), хранится только его хэш: утечка БД не даёт
  действующих токенов.
- Ротация refresh-токена при каждом использовании и обнаружение повторного использования;
  конкурентные обновления одного токена сериализуются `SELECT ... FOR UPDATE`.
- Секреты только из окружения; приложение не запустится с `JWT_SECRET` короче 32 символов.
- Rate limiter работает в режиме fail-open: при падении Redis вход не блокируется,
  событие пишется в лог (компромисс в пользу доступности).
- Внутренние ошибки не раскрываются клиенту, а стек-трейс уходит только в лог.

## Лицензия

MIT
