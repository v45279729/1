# МебельОрг, вариант 5

Desktop-приложение для демонстрационного экзамена: Python + PyQt6 + MySQL.

## Что реализовано

- Авторизация по пользователям из БД.
- Роли: гость, авторизированный клиент, менеджер, администратор.
- Просмотр товаров для всех ролей.
- Поиск, сортировка и фильтрация товаров для менеджера и администратора.
- Подсветка товаров:
  - скидка больше 15%: `#008080`;
  - нет на складе: серый фон.
- Отображение старой и итоговой цены при скидке.
- Добавление, редактирование и удаление товаров для администратора.
- Запрет удаления товара, если он есть в заказе.
- Просмотр заказов для менеджера и администратора.
- Добавление, редактирование и удаление заказов для администратора.
- Импорт исходных Excel-файлов и изображений варианта 5.

## Установка

Открыть PowerShell в папке `mebelorg_app`:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Создать файл настроек подключения:

```powershell
copy .env.example .env
notepad .env
```

В `.env` указать логин и пароль MySQL. Пример:

```text
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=ваш_пароль
MYSQL_DATABASE=mebelorg
```

## Создание БД и импорт данных

MySQL Server должен быть запущен.

```powershell
python scripts/import_data.py
```

Скрипт создаст базу `mebelorg`, таблицы и загрузит данные из ресурсов В5.

## Запуск приложения

```powershell
python -m app.main
```

## Примеры учетных записей

Администратор:

```text
login: 94d5ous@gmail.com
password: uzWC67
```

Менеджер:

```text
login: ptec8ym@yahoo.com
password: LdNyos
```

Авторизированный клиент:

```text
login: yzls62@outlook.com
password: JlFRCZ
```

Также на экране входа есть кнопка входа в роли гостя.

## Файлы проекта

- `app/main.py` - PyQt6-интерфейс.
- `app/repositories.py` - запросы к БД и бизнес-правила.
- `app/db.py` - подключение к MySQL.
- `sql/schema.sql` - SQL-скрипт базы данных.
- `scripts/import_data.py` - импорт исходных данных.
- `resources/import` - исходные файлы варианта 5.
- `resources/product_images` - рабочая папка изображений товаров.
