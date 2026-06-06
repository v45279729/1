from __future__ import annotations

from datetime import date
from typing import Any

from app.db import Database


# Белый список справочников, которые разрешено читать через общий метод get_options.
LOOKUP_TABLES = {
    "categories": "categories",
    "manufacturers": "manufacturers",
    "suppliers": "suppliers",
    "units": "units",
    "order_statuses": "order_statuses",
}


class Repository:
    # Репозиторий хранит все SQL-запросы и бизнес-правила отдельно от PyQt-интерфейса.
    def __init__(self, database: Database) -> None:
        self.database = database

    # Авторизация сверяет логин и пароль с пользователями из импортированной БД.
    def authenticate(self, login: str, password: str) -> dict | None:
        return self.database.fetch_one(
            """
            SELECT u.id, u.full_name, u.login, r.name AS role_name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE u.login = %s AND u.password = %s
            """,
            (login, password),
        )

    # Общий метод для выпадающих списков: категории, поставщики, статусы и т.д.
    def get_options(self, table_key: str) -> list[dict]:
        table = LOOKUP_TABLES[table_key]
        return self.database.fetch_all(f"SELECT id, name FROM {table} ORDER BY name")

    # Для заказов выбираются только пользователи с ролью авторизированного клиента.
    def get_customers(self) -> list[dict]:
        return self.database.fetch_all(
            """
            SELECT u.id, u.full_name AS name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE r.name = 'Авторизированный клиент'
            ORDER BY u.full_name
            """
        )

    def list_products(
        self,
        search: str = "",
        discount_filter: str = "all",
        sort_mode: str = "none",
    ) -> list[dict]:
        # Фильтр, поиск и сортировка собираются динамически, чтобы применять их совместно.
        where_parts: list[str] = []
        params: list[Any] = []

        for token in search.lower().split():
            # Поиск идет по всем текстовым данным товара и поддерживает несколько слов.
            where_parts.append(
                """
                LOWER(CONCAT_WS(' ', p.article, p.name, p.description,
                    c.name, m.name, s.name, u.name)) LIKE %s
                """
            )
            params.append(f"%{token}%")

        # Диапазоны скидок соответствуют требованиям проекта.
        if discount_filter == "0_10":
            where_parts.append("p.discount_percent >= 0 AND p.discount_percent < 11")
        elif discount_filter == "11_14":
            where_parts.append("p.discount_percent >= 11 AND p.discount_percent < 15")
        elif discount_filter == "15_plus":
            where_parts.append("p.discount_percent >= 15")

        # В ORDER BY попадают только заранее разрешенные режимы сортировки.
        sort_sql = {
            "price_asc": "p.price ASC, p.id ASC",
            "price_desc": "p.price DESC, p.id ASC",
            "stock_asc": "p.stock_quantity ASC, p.id ASC",
            "stock_desc": "p.stock_quantity DESC, p.id ASC",
        }.get(sort_mode, "p.id ASC")

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        return self.database.fetch_all(
            f"""
            SELECT
                p.id,
                p.article,
                p.name,
                p.price,
                p.discount_percent,
                p.stock_quantity,
                p.description,
                p.photo_path,
                u.name AS unit_name,
                c.name AS category_name,
                m.name AS manufacturer_name,
                s.name AS supplier_name,
                ROUND(p.price * (1 - p.discount_percent / 100), 2) AS final_price
            FROM products p
            JOIN units u ON u.id = p.unit_id
            JOIN categories c ON c.id = p.category_id
            JOIN manufacturers m ON m.id = p.manufacturer_id
            JOIN suppliers s ON s.id = p.supplier_id
            {where_sql}
            ORDER BY {sort_sql}
            """,
            params,
        )

    # Возвращает все поля товара для заполнения формы редактирования.
    def get_product(self, product_id: int) -> dict | None:
        return self.database.fetch_one(
            """
            SELECT
                p.id,
                p.article,
                p.name,
                p.unit_id,
                p.price,
                p.supplier_id,
                p.manufacturer_id,
                p.category_id,
                p.discount_percent,
                p.stock_quantity,
                p.description,
                p.photo_path
            FROM products p
            WHERE p.id = %s
            """,
            (product_id,),
        )

    # Один метод используется и для добавления, и для редактирования товара.
    def save_product(self, data: dict) -> int:
        if data.get("id"):
            self.database.execute(
                """
                UPDATE products
                SET article = %s,
                    name = %s,
                    unit_id = %s,
                    price = %s,
                    supplier_id = %s,
                    manufacturer_id = %s,
                    category_id = %s,
                    discount_percent = %s,
                    stock_quantity = %s,
                    description = %s,
                    photo_path = %s
                WHERE id = %s
                """,
                (
                    data["article"],
                    data["name"],
                    data["unit_id"],
                    data["price"],
                    data["supplier_id"],
                    data["manufacturer_id"],
                    data["category_id"],
                    data["discount_percent"],
                    data["stock_quantity"],
                    data["description"],
                    data["photo_path"],
                    data["id"],
                ),
            )
            return int(data["id"])

        return self.database.execute(
            """
            INSERT INTO products (
                article, name, unit_id, price, supplier_id, manufacturer_id,
                category_id, discount_percent, stock_quantity, description, photo_path
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                data["article"],
                data["name"],
                data["unit_id"],
                data["price"],
                data["supplier_id"],
                data["manufacturer_id"],
                data["category_id"],
                data["discount_percent"],
                data["stock_quantity"],
                data["description"],
                data["photo_path"],
            ),
        )

    # Удалять товар нельзя, если на него есть ссылка в позициях заказа.
    def delete_product(self, product_id: int) -> None:
        row = self.database.fetch_one(
            "SELECT COUNT(*) AS total FROM order_items WHERE product_id = %s",
            (product_id,),
        )
        if row and row["total"] > 0:
            raise ValueError("Товар присутствует в заказе, поэтому удалить его нельзя.")
        self.database.execute("DELETE FROM products WHERE id = %s", (product_id,))

    # Список заказов собирается с адресом, клиентом, статусом и строкой позиций.
    def list_orders(self) -> list[dict]:
        return self.database.fetch_all(
            """
            SELECT
                o.id,
                o.order_date,
                o.delivery_date,
                pp.address AS pickup_address,
                u.full_name AS customer_name,
                o.receive_code,
                os.name AS status_name,
                COALESCE(
                    GROUP_CONCAT(CONCAT(p.article, ', ', oi.quantity)
                        ORDER BY oi.id SEPARATOR '; '),
                    ''
                ) AS items
            FROM orders o
            JOIN pickup_points pp ON pp.id = o.pickup_point_id
            JOIN order_statuses os ON os.id = o.status_id
            LEFT JOIN users u ON u.id = o.customer_id
            LEFT JOIN order_items oi ON oi.order_id = o.id
            LEFT JOIN products p ON p.id = oi.product_id
            GROUP BY o.id, o.order_date, o.delivery_date, pp.address,
                u.full_name, o.receive_code, os.name
            ORDER BY o.id
            """
        )

    # Данные конкретного заказа нужны форме редактирования.
    def get_order(self, order_id: int) -> dict | None:
        order = self.database.fetch_one(
            """
            SELECT id, order_date, delivery_date, pickup_point_id,
                customer_id, receive_code, status_id
            FROM orders
            WHERE id = %s
            """,
            (order_id,),
        )
        if not order:
            return None

        order["items"] = self.database.fetch_all(
            """
            SELECT p.article, oi.quantity
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            WHERE oi.order_id = %s
            ORDER BY oi.id
            """,
            (order_id,),
        )
        return order

    # Новый код получения продолжается от максимального существующего значения.
    def get_next_receive_code(self) -> int:
        row = self.database.fetch_one(
            "SELECT COALESCE(MAX(receive_code), 900) + 1 AS next_code FROM orders"
        )
        return int(row["next_code"] if row else 901)

    # Заказ и его позиции сохраняются в одной транзакции, чтобы не получить "половину" заказа.
    def save_order(self, data: dict, items: list[tuple[str, int]]) -> int:
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor(dictionary=True)
            product_items: list[tuple[int, int]] = []
            for article, quantity in items:
                cursor.execute("SELECT id FROM products WHERE article = %s", (article,))
                product = cursor.fetchone()
                if not product:
                    raise ValueError(f"Товар с артикулом {article} не найден.")
                product_items.append((int(product["id"]), quantity))

            if data.get("id"):
                order_id = int(data["id"])
                cursor.execute(
                    """
                    UPDATE orders
                    SET order_date = %s,
                        delivery_date = %s,
                        pickup_point_id = %s,
                        customer_id = %s,
                        receive_code = %s,
                        status_id = %s
                    WHERE id = %s
                    """,
                    (
                        data["order_date"],
                        data["delivery_date"],
                        data["pickup_point_id"],
                        data["customer_id"],
                        data["receive_code"],
                        data["status_id"],
                        order_id,
                    ),
                )
                cursor.execute("DELETE FROM order_items WHERE order_id = %s", (order_id,))
            else:
                cursor.execute(
                    """
                    INSERT INTO orders (
                        order_date, delivery_date, pickup_point_id,
                        customer_id, receive_code, status_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        data["order_date"],
                        data["delivery_date"],
                        data["pickup_point_id"],
                        data["customer_id"],
                        data["receive_code"],
                        data["status_id"],
                    ),
                )
                order_id = int(cursor.lastrowid)

            cursor.executemany(
                """
                INSERT INTO order_items (order_id, product_id, quantity)
                VALUES (%s, %s, %s)
                """,
                [(order_id, product_id, quantity) for product_id, quantity in product_items],
            )
            connection.commit()
            return order_id
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # Позиции заказа удаляются автоматически за счет ON DELETE CASCADE.
    def delete_order(self, order_id: int) -> None:
        self.database.execute("DELETE FROM orders WHERE id = %s", (order_id,))

    # Разбирает строку вида: "А112Т4, 2, G843H5, 1".
    @staticmethod
    def parse_order_items(raw_text: str) -> list[tuple[str, int]]:
        parts = [part.strip() for part in raw_text.replace(";", ",").split(",") if part.strip()]
        if not parts or len(parts) % 2 != 0:
            raise ValueError("Введите товары в формате: артикул, количество, артикул, количество.")

        result: list[tuple[str, int]] = []
        for index in range(0, len(parts), 2):
            article = parts[index]
            try:
                quantity = int(parts[index + 1])
            except ValueError as exc:
                raise ValueError("Количество товара должно быть целым числом.") from exc
            if quantity <= 0:
                raise ValueError("Количество товара должно быть больше нуля.")
            result.append((article, quantity))
        return result

    # Вспомогательный конвертер оставлен для форм, где нужен разбор date.
    @staticmethod
    def date_to_qdate_parts(value: date | None) -> tuple[int, int, int] | None:
        if value is None:
            return None
        return value.year, value.month, value.day
