<COMPRESSED>
# Mirra — архитектурные решения и структура данных

Дополняет `Mirra_концепция.md`. Здесь — технические решения: структура профиля, типы видимости, границы хранения.

## Ключевая абстракция: каждое поле — обёртка

Замок висит на каждом подпункте, поэтому каждое значение хранится вместе с видимостью:

```json
{
  "value": "текст или значение",
  "visibility": "public | private",
  "source": "self | imported | inferred"
}
```

- **public** — видно всем, включая рекрутеров.
- **private** — видно только владельцу.
- **source** — откуда взято: сам рассказал (`self`) / импортировал из hh или соцсети (`imported`) / вывела система (`inferred`). Поле — ключ к режиму «Зеркало» и к «зазору» (self vs inferred). В MVP можно не заполнять, но заложить в схему сразу.

Пустое поле не рендерится на странице.

## Корневая структура

```json
{
  "id": "uuid",
  "ownerId": "uuid",
  "basics": { },
  "tabs": {
    "resume": {},
    "interests": {},
    "personality": {},
    "relationships": {},
    "projects": {}
  },
  "tags": [],
  "settings": {},
  "meta": { "createdAt": "", "updatedAt": "" }
}
```

---

## Вкладка 1 — Резюме (`resume`)

```json
{
  "headline":         { "value": "", "visibility": "public" },
  "specialty":        { "value": "", "visibility": "public" },
  "responsibilities": [ { "value": "", "visibility": "public" } ],
  "achievements":     [ { "value": "", "visibility": "public" } ],
  "tools":            [ { "value": "", "visibility": "public" } ],
  "biggestWin":       { "value": "", "visibility": "public" },
  "disliked":         { "value": "", "visibility": "private" },
  "leaveReason":      { "value": "", "visibility": "private" },
  "roleSpecific": [
    { "key": "", "value": "", "visibility": "private" }
  ],
  "experience": [
    { "company": "", "role": "", "period": "", "description": "", "visibility": "public" }
  ],
  "education": [
    { "institution": "", "degree": "", "year": "", "visibility": "public" }
  ],
  "skills":     [ { "value": "", "visibility": "public" } ],
  "languages":  [ { "lang": "", "level": "", "visibility": "public" } ]
}
```

`roleSpecific` — свободный список key-value: «специфичное по специальности» у всех разное (руководителю — число подчинённых, разработчику — стек).

## Вкладка 2 — Интересы (`interests`)

```json
{
  "books":    [ { "value": "", "visibility": "public" } ],
  "films":    [ { "value": "", "visibility": "public" } ],
  "series":   [ { "value": "", "visibility": "public" } ],
  "music":    [ { "value": "", "visibility": "public" } ],
  "hobbies":  [ { "value": "", "visibility": "public" } ],
  "likes":    [ { "value": "", "visibility": "public" } ],
  "dislikes": [ { "value": "", "visibility": "private" } ]
}
```

`likes`/`dislikes` — прямой источник для облака тегов (зелёное/красное).

## Вкладка 3 — Личность (`personality`)

```json
{
  "traits":      [ { "value": "", "visibility": "public" } ],
  "strengths":   [ { "value": "", "visibility": "public" } ],
  "weaknesses":  [ { "value": "", "visibility": "private" } ],
  "values":      [ { "value": "", "visibility": "public" } ],
  "motivation":  { "value": "", "visibility": "private" },
  "tests":       [ { "name": "", "result": "", "visibility": "private" } ]
}
```

`tests` — только `name` + `result` текстом, вписывает сам пользователь. Чужие методики (DISC/MBTI и др.) не встраивать без лицензии.

## Вкладка 4 — Отношения (`relationships`)

```json
[
  {
    "label":        { "value": "", "visibility": "private" },
    "relationType": { "value": "", "visibility": "public" },
    "description":  { "value": "", "visibility": "private" }
  }
]
```

По умолчанию — только роли («мама», «партнёр», «друг»), без имён. Имена — `private`. Защищает владельца и третьих лиц.

## Вкладка 5 — Проекты (`projects`)

```json
[
  {
    "name":        { "value": "", "visibility": "public" },
    "description": { "value": "", "visibility": "public" },
    "status":      { "value": "", "visibility": "public" },
    "role":        { "value": "", "visibility": "public" },
    "link":        { "value": "", "visibility": "public" },
    "tags":        [ { "value": "", "visibility": "public" } ]
  }
]
```

`status` — фиксированный набор: `активный | завершён | идея`.

---

## Облако тегов (`tags`)

Плоский список; часть тегов подтягивается автоматически из вкладок.

```json
[
  { "text": "", "category": "interest", "visibility": "public", "weight": 0.5 }
]
```

Категории → цвета:

| category | Цвет | Смысл |
|----------|------|-------|
| `like` | зелёное | нравится |
| `dislike` | красное | не нравится |
| `interest` | фиолетовое | зона интересов |
| `skill` | синее | навыки |
| `value` | жёлтое | ценности |

Анимация «одни уплывают, другие всплывают» — рендер, а не данные. Значимость — поле `weight` (0–1), добавить позже, когда появятся данные.

---

## Границы хранения

| Сущность | Где хранится | Почему |
|----------|--------------|--------|
| **Секреты** | локально на стороне клиента, зашифровано | не на сервере, не в API — по требованию |
| **Зеркало** | нигде как данные | вычисляемая проекция публичных полей, не хранимое поле |
| **Баланс / кошелёк** | отдельная сущность (billing) | не смешивать профиль и деньги |
| **Гостевой счёт** | в `settings` профиля | настройка владельца |

---

## Дефолты видимости

| Поле | По умолчанию |
|------|--------------|
| Имя, кредо, специальность | public |
| Обязанности, достижения, инструменты, опыт, образование | public |
| Причина ухода, «что не нравилось», roleSpecific | private |
| Интересы (книги/фильмы/музыка/хобби) | public |
| Личность: traits, strengths, values | public |
| Личность: weaknesses, motivation, tests | private |
| **Отношения — вся вкладка** | private |
| Проекты | public |

Человек меняет замок одним кликом; «безопасные» дефолты защищают от утечки личного по невнимательности.

---

## Открытые архитектурные вопросы (не решены)

- Минимальный веб-стек: что можно без бекенда (как у резюме на GitHub Pages), а где нужен сервер (хранение портрета, платный доступ).
- Выбор биллинга (CloudPayments / ЮKassa / Paddle / Lemon Squeezy) в зависимости от гео пользователей.
- Шифрование и формат хранения «Секретов» на стороне клиента.
- Как индексировать профили для поиска/сопоставления, если часть полей private (private не участвует в поиске).
</COMPRESSED>