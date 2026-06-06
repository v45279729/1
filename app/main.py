from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

from mysql.connector import IntegrityError
from PIL import Image
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.config import (
    BASE_DIR,
    IMPORT_DIR,
    PLACEHOLDER_IMAGE,
    PRODUCT_IMAGES_DIR,
    absolute_from_base,
    relative_to_base,
)
from app.db import Database
from app.repositories import Repository


# Роли используются для включения и отключения функций интерфейса.
ROLE_GUEST = "Гость"
ROLE_CLIENT = "Авторизированный клиент"
ROLE_MANAGER = "Менеджер"
ROLE_ADMIN = "Администратор"


# Общий стиль приложения по руководству В5: Calibri, белый фон, голубой доп. цвет и синий акцент.
APP_STYLE = """
QWidget {
    font-family: Calibri;
    font-size: 11pt;
    background-color: #FFFFFF;
}
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {
    border: 1px solid #9AA5B1;
    border-radius: 4px;
    padding: 5px;
    background-color: #FFFFFF;
}
QPushButton {
    background-color: #0000FF;
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 7px 12px;
}
QPushButton:disabled {
    background-color: #A7B0BE;
}
QPushButton:hover {
    background-color: #1E40FF;
}
QHeaderView::section {
    background-color: #00FFFF;
    border: 1px solid #B8C2CC;
    padding: 6px;
}
QTableWidget {
    gridline-color: #D0D7DE;
    selection-background-color: #C7D2FE;
}
"""


# Обертки над QMessageBox нужны, чтобы сообщения во всех окнах выглядели одинаково.
def show_error(parent: QWidget, title: str, message: str) -> None:
    QMessageBox.critical(parent, title, message)


def show_info(parent: QWidget, title: str, message: str) -> None:
    QMessageBox.information(parent, title, message)


def confirm(parent: QWidget, title: str, message: str) -> bool:
    answer = QMessageBox.question(
        parent,
        title,
        message,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


# Устанавливает выбранный элемент combobox по id из базы.
def set_combo_value(combo: QComboBox, value: int | None) -> None:
    for index in range(combo.count()):
        if combo.itemData(index) == value:
            combo.setCurrentIndex(index)
            return


# Заполняет выпадающий список справочником из базы.
def fill_combo(combo: QComboBox, options: list[dict], empty_text: str | None = None) -> None:
    combo.clear()
    if empty_text is not None:
        combo.addItem(empty_text, None)
    for option in options:
        combo.addItem(str(option["name"]), int(option["id"]))


# Форматирование чисел и дат вынесено отдельно, чтобы таблицы выглядели единообразно.
def format_money(value) -> str:
    return f"{float(value):,.2f}".replace(",", " ")


def format_date(value) -> str:
    return value.strftime("%d.%m.%Y") if value else "не указана"


def qdate_to_date(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())


class ProductFormDialog(QDialog):
    # Диалог используется и для добавления нового товара, и для редактирования существующего.
    def __init__(
        self,
        repository: Repository,
        product_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.product_id = product_id
        self.selected_image_path: Path | None = None
        self.current_photo_path = relative_to_base(PLACEHOLDER_IMAGE)
        self.old_photo_path: str | None = None

        self.setWindowTitle("Редактирование товара" if product_id else "Добавление товара")
        self.setMinimumWidth(720)
        self.build_ui()
        self.load_options()
        if product_id:
            self.load_product(product_id)
        else:
            self.set_preview(PLACEHOLDER_IMAGE)

    def build_ui(self) -> None:
        # Все поля соответствуют требованиям формы добавления/редактирования товара.
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.id_label = QLabel("будет создан автоматически")
        self.article_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.category_combo = QComboBox()
        self.manufacturer_combo = QComboBox()
        self.supplier_combo = QComboBox()
        self.unit_combo = QComboBox()
        self.price_spin = QDoubleSpinBox()
        self.price_spin.setMaximum(99_999_999)
        self.price_spin.setDecimals(2)
        self.stock_spin = QSpinBox()
        self.stock_spin.setMaximum(1_000_000)
        self.discount_spin = QDoubleSpinBox()
        self.discount_spin.setRange(0, 100)
        self.discount_spin.setDecimals(2)
        self.description_edit = QTextEdit()
        self.description_edit.setFixedHeight(90)

        image_row = QHBoxLayout()
        self.image_label = QLabel()
        self.image_label.setFixedSize(300, 200)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("border: 1px solid #9AA5B1; background: #F8FAFC;")
        choose_image_button = QPushButton("Выбрать изображение")
        choose_image_button.clicked.connect(self.choose_image)
        image_row.addWidget(self.image_label)
        image_row.addWidget(choose_image_button)
        image_row.addStretch()

        self.id_caption = QLabel("ID")
        form.addRow(self.id_caption, self.id_label)
        form.addRow("Артикул", self.article_edit)
        form.addRow("Наименование", self.name_edit)
        form.addRow("Категория", self.category_combo)
        form.addRow("Производитель", self.manufacturer_combo)
        form.addRow("Поставщик", self.supplier_combo)
        form.addRow("Цена", self.price_spin)
        form.addRow("Единица измерения", self.unit_combo)
        form.addRow("Количество на складе", self.stock_spin)
        form.addRow("Действующая скидка, %", self.discount_spin)
        form.addRow("Описание", self.description_edit)
        form.addRow("Фото", image_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(buttons)

        # При добавлении ID не показывается, потому что он автоматически создается в БД.
        if not self.product_id:
            self.id_caption.hide()
            self.id_label.hide()

    def load_options(self) -> None:
        # Категория, производитель, поставщик и единица измерения берутся из справочников.
        fill_combo(self.category_combo, self.repository.get_options("categories"))
        fill_combo(self.manufacturer_combo, self.repository.get_options("manufacturers"))
        fill_combo(self.supplier_combo, self.repository.get_options("suppliers"))
        fill_combo(self.unit_combo, self.repository.get_options("units"))

    def load_product(self, product_id: int) -> None:
        # При редактировании форма заполняется актуальными значениями из базы данных.
        product = self.repository.get_product(product_id)
        if not product:
            show_error(self, "Ошибка", "Выбранный товар не найден в базе данных.")
            self.reject()
            return

        self.id_label.setText(str(product["id"]))
        self.article_edit.setText(product["article"])
        self.name_edit.setText(product["name"])
        set_combo_value(self.category_combo, product["category_id"])
        set_combo_value(self.manufacturer_combo, product["manufacturer_id"])
        set_combo_value(self.supplier_combo, product["supplier_id"])
        set_combo_value(self.unit_combo, product["unit_id"])
        self.price_spin.setValue(float(product["price"]))
        self.stock_spin.setValue(int(product["stock_quantity"]))
        self.discount_spin.setValue(float(product["discount_percent"]))
        self.description_edit.setPlainText(product["description"] or "")
        self.current_photo_path = product["photo_path"] or relative_to_base(PLACEHOLDER_IMAGE)
        self.old_photo_path = self.current_photo_path
        self.set_preview(absolute_from_base(self.current_photo_path))

    def set_preview(self, path: Path) -> None:
        # Изображение масштабируется в область 300x200 без искажения пропорций.
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            pixmap = QPixmap(str(PLACEHOLDER_IMAGE))
        self.image_label.setPixmap(
            pixmap.scaled(
                300,
                200,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def choose_image(self) -> None:
        # Администратор выбирает новое фото, но сохранение в папку приложения происходит позже.
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите изображение товара",
            str(BASE_DIR),
            "Images (*.png *.jpg *.jpeg *.bmp)",
        )
        if not file_name:
            return
        self.selected_image_path = Path(file_name)
        self.set_preview(self.selected_image_path)

    def save_selected_image(self) -> str:
        # Новое изображение уменьшается до 300x200 и сохраняется как отдельный файл проекта.
        if not self.selected_image_path:
            return self.current_photo_path

        PRODUCT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        target = PRODUCT_IMAGES_DIR / f"product_{uuid4().hex}.jpg"
        with Image.open(self.selected_image_path) as image:
            image.thumbnail((300, 200))
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            image.save(target, "JPEG", quality=90)
        return relative_to_base(target)

    def remove_old_image_if_needed(self, new_photo_path: str) -> None:
        # При замене удаляются только файлы из рабочей папки product_images.
        if not self.old_photo_path or self.old_photo_path == new_photo_path:
            return
        old_path = BASE_DIR / self.old_photo_path
        try:
            if old_path.exists() and old_path.parent.resolve() == PRODUCT_IMAGES_DIR.resolve():
                old_path.unlink()
        except OSError:
            pass

    def remove_new_image_if_save_failed(self, photo_path: str | None) -> None:
        # Если БД отказала в сохранении, новое уже скопированное фото не должно остаться мусором.
        if not photo_path or photo_path == self.old_photo_path:
            return
        path = BASE_DIR / photo_path
        try:
            if path.exists() and path.parent.resolve() == PRODUCT_IMAGES_DIR.resolve():
                path.unlink()
        except OSError:
            pass

    def save(self) -> None:
        # Перед сохранением проверяются обязательные поля и ограничения задания.
        article = self.article_edit.text().strip()
        name = self.name_edit.text().strip()
        if not article:
            show_error(self, "Ошибка ввода", "Укажите артикул товара.")
            return
        if not name:
            show_error(self, "Ошибка ввода", "Укажите наименование товара.")
            return

        photo_path: str | None = None
        try:
            photo_path = self.save_selected_image()
            data = {
                "id": self.product_id,
                "article": article,
                "name": name,
                "unit_id": self.unit_combo.currentData(),
                "price": self.price_spin.value(),
                "supplier_id": self.supplier_combo.currentData(),
                "manufacturer_id": self.manufacturer_combo.currentData(),
                "category_id": self.category_combo.currentData(),
                "discount_percent": self.discount_spin.value(),
                "stock_quantity": self.stock_spin.value(),
                "description": self.description_edit.toPlainText().strip(),
                "photo_path": photo_path,
            }
            self.repository.save_product(data)
            self.remove_old_image_if_needed(photo_path)
            self.accept()
        except IntegrityError as exc:
            self.remove_new_image_if_save_failed(photo_path)
            show_error(
                self,
                "Ошибка сохранения",
                "Товар с таким артикулом уже существует. Укажите уникальный артикул.",
            )
            if self.selected_image_path:
                self.set_preview(self.selected_image_path)
        except Exception as exc:
            self.remove_new_image_if_save_failed(photo_path)
            show_error(self, "Ошибка сохранения", str(exc))


class OrderFormDialog(QDialog):
    # Диалог заказа поддерживает добавление и редактирование заказа вместе с его позициями.
    def __init__(
        self,
        repository: Repository,
        order_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.order_id = order_id
        self.setWindowTitle("Редактирование заказа" if order_id else "Добавление заказа")
        self.setMinimumWidth(640)
        self.build_ui()
        self.load_options()
        if order_id:
            self.load_order(order_id)
        else:
            self.receive_code_spin.setValue(self.repository.get_next_receive_code())

    def build_ui(self) -> None:
        # Поля формы заказа повторяют состав данных из задания: артикулы, статус, пункт и даты.
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.id_label = QLabel("будет создан автоматически")
        self.items_edit = QLineEdit()
        self.items_edit.setPlaceholderText("Например: А112Т4, 2, G843H5, 1")
        self.status_combo = QComboBox()
        self.pickup_combo = QComboBox()
        self.customer_combo = QComboBox()
        self.receive_code_spin = QSpinBox()
        self.receive_code_spin.setRange(0, 999_999)
        self.order_date_edit = QDateEdit()
        self.order_date_edit.setCalendarPopup(True)
        self.order_date_edit.setDisplayFormat("dd.MM.yyyy")
        self.delivery_date_edit = QDateEdit()
        self.delivery_date_edit.setCalendarPopup(True)
        self.delivery_date_edit.setDisplayFormat("dd.MM.yyyy")

        today = date.today()
        delivery = today + timedelta(days=7)
        self.order_date_edit.setDate(QDate(today.year, today.month, today.day))
        self.delivery_date_edit.setDate(QDate(delivery.year, delivery.month, delivery.day))

        self.order_id_caption = QLabel("ID")
        form.addRow(self.order_id_caption, self.id_label)
        form.addRow("Артикулы и количество", self.items_edit)
        form.addRow("Статус заказа", self.status_combo)
        form.addRow("Адрес пункта выдачи", self.pickup_combo)
        form.addRow("Клиент", self.customer_combo)
        form.addRow("Код получения", self.receive_code_spin)
        form.addRow("Дата заказа", self.order_date_edit)
        form.addRow("Дата выдачи", self.delivery_date_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(buttons)

        if not self.order_id:
            self.order_id_caption.hide()
            self.id_label.hide()

    def load_options(self) -> None:
        # Статусы, пункты выдачи и клиенты загружаются из базы для выпадающих списков.
        fill_combo(self.status_combo, self.repository.get_options("order_statuses"))
        pickup_points = self.repository.database.fetch_all(
            "SELECT id, address AS name FROM pickup_points ORDER BY id"
        )
        fill_combo(self.pickup_combo, pickup_points)
        fill_combo(self.customer_combo, self.repository.get_customers(), "Без клиента")

    def load_order(self, order_id: int) -> None:
        # При редактировании заказа подтягиваются его шапка и позиции.
        order = self.repository.get_order(order_id)
        if not order:
            show_error(self, "Ошибка", "Выбранный заказ не найден в базе данных.")
            self.reject()
            return

        self.id_label.setText(str(order["id"]))
        self.items_edit.setText(
            "; ".join(f"{item['article']}, {item['quantity']}" for item in order["items"])
        )
        set_combo_value(self.status_combo, order["status_id"])
        set_combo_value(self.pickup_combo, order["pickup_point_id"])
        set_combo_value(self.customer_combo, order["customer_id"])
        self.receive_code_spin.setValue(int(order["receive_code"] or 0))

        for field, editor in (
            ("order_date", self.order_date_edit),
            ("delivery_date", self.delivery_date_edit),
        ):
            value = order[field]
            if value:
                editor.setDate(QDate(value.year, value.month, value.day))

    def save(self) -> None:
        # Сохраняем заказ через репозиторий, чтобы позиции и шапка попали в одну транзакцию.
        try:
            items = self.repository.parse_order_items(self.items_edit.text())
            order_date = qdate_to_date(self.order_date_edit.date())
            delivery_date = qdate_to_date(self.delivery_date_edit.date())
            if delivery_date < order_date:
                raise ValueError("Дата выдачи не может быть раньше даты заказа.")
            data = {
                "id": self.order_id,
                "order_date": order_date,
                "delivery_date": delivery_date,
                "pickup_point_id": self.pickup_combo.currentData(),
                "customer_id": self.customer_combo.currentData(),
                "receive_code": self.receive_code_spin.value(),
                "status_id": self.status_combo.currentData(),
            }
            self.repository.save_order(data, items)
            self.accept()
        except Exception as exc:
            show_error(self, "Ошибка сохранения заказа", str(exc))


class MainWindow(QMainWindow):
    # Главное окно переключает экраны входа, товаров и заказов без запуска новых приложений.
    def __init__(self) -> None:
        super().__init__()
        self.database = Database()
        self.repository = Repository(self.database)
        self.current_user: dict | None = None
        self.products: list[dict] = []
        self.orders: list[dict] = []

        self.database.fetch_one("SELECT 1 AS ok")
        self.setMinimumSize(1180, 720)
        self.setWindowIcon(QIcon(str(IMPORT_DIR / "icon.png")))
        self.show_login()

    def show_login(self) -> None:
        # Стартовый экран: авторизация или переход к просмотру товаров в роли гостя.
        self.setWindowTitle("МебельОрг - вход")
        page = QWidget()
        root = QVBoxLayout(page)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(IMPORT_DIR / "icon.png"))
        logo.setPixmap(
            pixmap.scaled(
                128,
                128,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

        title = QLabel("ООО «МебельОрг»")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22pt; font-weight: 700;")

        self.login_edit = QLineEdit()
        self.login_edit.setPlaceholderText("Логин")
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Пароль")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.returnPressed.connect(self.handle_login)

        login_button = QPushButton("Войти")
        login_button.clicked.connect(self.handle_login)
        guest_button = QPushButton("Продолжить как гость")
        guest_button.clicked.connect(self.login_as_guest)

        form = QVBoxLayout()
        form.addWidget(self.login_edit)
        form.addWidget(self.password_edit)
        form.addWidget(login_button)
        form.addWidget(guest_button)

        wrapper = QWidget()
        wrapper.setFixedWidth(360)
        wrapper.setLayout(form)

        root.addWidget(logo)
        root.addWidget(title)
        root.addSpacing(20)
        root.addWidget(wrapper, alignment=Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(page)

    def handle_login(self) -> None:
        # Успешная авторизация открывает основной экран с правами найденной роли.
        login = self.login_edit.text().strip()
        password = self.password_edit.text().strip()
        if not login or not password:
            show_error(self, "Ошибка авторизации", "Введите логин и пароль.")
            return

        try:
            user = self.repository.authenticate(login, password)
        except Exception as exc:
            show_error(self, "Ошибка подключения", str(exc))
            return

        if not user:
            show_error(
                self,
                "Ошибка авторизации",
                "Пользователь с указанным логином и паролем не найден.",
            )
            return

        self.show_products(user)

    def login_as_guest(self) -> None:
        # Гость видит только список товаров без поиска, сортировки и фильтрации.
        self.show_products({"id": None, "full_name": "Гость", "role_name": ROLE_GUEST})

    def show_products(self, user: dict) -> None:
        # Экран товаров адаптируется под роль пользователя.
        self.current_user = user
        role = user["role_name"]
        self.setWindowTitle(f"МебельОрг - товары ({role})")
        page = QWidget()
        root = QVBoxLayout(page)

        top = QHBoxLayout()
        logo = QLabel()
        pixmap = QPixmap(str(IMPORT_DIR / "icon.png"))
        logo.setPixmap(
            pixmap.scaled(
                44,
                44,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        title = QLabel("Список товаров")
        title.setStyleSheet("font-size: 18pt; font-weight: 700;")
        user_label = QLabel(f"{user['full_name']}")
        user_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        logout_button = QPushButton("Выйти")
        logout_button.clicked.connect(self.show_login)
        top.addWidget(logo)
        top.addWidget(title)
        top.addStretch()
        top.addWidget(user_label)
        top.addWidget(logout_button)
        root.addLayout(top)

        self.search_edit = None
        self.discount_combo = None
        self.sort_combo = None

        # Менеджер и администратор получают поиск, фильтр по скидке, сортировку и заказы.
        if role in (ROLE_MANAGER, ROLE_ADMIN):
            controls = QGridLayout()
            self.search_edit = QLineEdit()
            self.search_edit.setPlaceholderText("Поиск по текстовым данным")
            self.search_edit.textChanged.connect(self.load_products)
            self.discount_combo = QComboBox()
            self.discount_combo.addItem("Все диапазоны", "all")
            self.discount_combo.addItem("0-10,99%", "0_10")
            self.discount_combo.addItem("11-14,99%", "11_14")
            self.discount_combo.addItem("15% и более", "15_plus")
            self.discount_combo.currentIndexChanged.connect(self.load_products)
            self.sort_combo = QComboBox()
            self.sort_combo.addItem("Без сортировки", "none")
            self.sort_combo.addItem("Цена по возрастанию", "price_asc")
            self.sort_combo.addItem("Цена по убыванию", "price_desc")
            self.sort_combo.addItem("Остаток по возрастанию", "stock_asc")
            self.sort_combo.addItem("Остаток по убыванию", "stock_desc")
            self.sort_combo.currentIndexChanged.connect(self.load_products)

            orders_button = QPushButton("Заказы")
            orders_button.clicked.connect(self.show_orders)

            controls.addWidget(QLabel("Поиск"), 0, 0)
            controls.addWidget(self.search_edit, 0, 1)
            controls.addWidget(QLabel("Скидка"), 0, 2)
            controls.addWidget(self.discount_combo, 0, 3)
            controls.addWidget(QLabel("Сортировка"), 0, 4)
            controls.addWidget(self.sort_combo, 0, 5)
            controls.addWidget(orders_button, 0, 6)

            if role == ROLE_ADMIN:
                # Администратор дополнительно может управлять товарами.
                add_button = QPushButton("Добавить товар")
                add_button.clicked.connect(lambda: self.open_product_dialog(None))
                edit_button = QPushButton("Редактировать")
                edit_button.clicked.connect(self.edit_selected_product)
                delete_button = QPushButton("Удалить")
                delete_button.clicked.connect(self.delete_selected_product)
                controls.addWidget(add_button, 1, 0)
                controls.addWidget(edit_button, 1, 1)
                controls.addWidget(delete_button, 1, 2)

            root.addLayout(controls)

        self.product_table = QTableWidget(0, 9)
        self.product_table.setHorizontalHeaderLabels(
            [
                "Фото",
                "Товар",
                "Категория",
                "Производитель",
                "Поставщик",
                "Цена",
                "Ед.",
                "Остаток",
                "Скидка",
            ]
        )
        self.product_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.product_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.product_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.product_table.verticalHeader().setDefaultSectionSize(104)
        self.product_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.product_table.horizontalHeader().setStretchLastSection(True)
        if role == ROLE_ADMIN:
            self.product_table.cellDoubleClicked.connect(
                lambda row, column: self.open_product_dialog(self.product_id_at_row(row))
            )
        root.addWidget(self.product_table)
        self.setCentralWidget(page)
        self.load_products()

    def load_products(self) -> None:
        # Для гостя и клиента параметры поиска принудительно сбрасываются по заданию.
        if not self.current_user:
            return

        role = self.current_user["role_name"]
        search = self.search_edit.text() if self.search_edit else ""
        discount_filter = self.discount_combo.currentData() if self.discount_combo else "all"
        sort_mode = self.sort_combo.currentData() if self.sort_combo else "none"
        if role not in (ROLE_MANAGER, ROLE_ADMIN):
            search = ""
            discount_filter = "all"
            sort_mode = "none"

        try:
            self.products = self.repository.list_products(search, discount_filter, sort_mode)
        except Exception as exc:
            show_error(self, "Ошибка загрузки товаров", str(exc))
            return

        self.product_table.setRowCount(0)
        for row_index, product in enumerate(self.products):
            self.product_table.insertRow(row_index)
            self.fill_product_row(row_index, product)

    def fill_product_row(self, row: int, product: dict) -> None:
        # Строка подсвечивается серым при нулевом остатке или бирюзовым при скидке больше 15%.
        discount = float(product["discount_percent"])
        stock = int(product["stock_quantity"])
        background = "#D9D9D9" if stock == 0 else "#008080" if discount > 15 else "#FFFFFF"

        image_label = QLabel()
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_label.setStyleSheet(f"background-color: {background};")
        pixmap = QPixmap(str(absolute_from_base(product["photo_path"])))
        if pixmap.isNull():
            pixmap = QPixmap(str(PLACEHOLDER_IMAGE))
        image_label.setPixmap(
            pixmap.scaled(
                88,
                88,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        id_item = QTableWidgetItem("")
        id_item.setData(Qt.ItemDataRole.UserRole, int(product["id"]))
        id_item.setBackground(QColor(background))
        self.product_table.setItem(row, 0, id_item)
        self.product_table.setCellWidget(row, 0, image_label)

        values = [
            f"{product['article']}\n{product['name']}\n{product['description']}",
            product["category_name"],
            product["manufacturer_name"],
            product["supplier_name"],
            "",
            product["unit_name"],
            str(product["stock_quantity"]),
            f"{format_money(product['discount_percent'])}%",
        ]
        for column, value in enumerate(values, start=1):
            item = QTableWidgetItem(str(value))
            item.setBackground(QColor(background))
            item.setData(Qt.ItemDataRole.UserRole, int(product["id"]))
            self.product_table.setItem(row, column, item)

        price_label = QLabel()
        price_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        price_label.setStyleSheet(f"background-color: {background}; padding: 4px;")
        if discount > 0:
            # При скидке старая цена зачеркивается, а итоговая выводится рядом черным цветом.
            price_label.setText(
                "<span style='color: red; text-decoration: line-through;'>"
                f"{format_money(product['price'])}</span><br>"
                "<span style='color: black;'>"
                f"{format_money(product['final_price'])}</span>"
            )
        else:
            price_label.setText(f"{format_money(product['price'])}")
        self.product_table.setCellWidget(row, 5, price_label)

    def product_id_at_row(self, row: int) -> int | None:
        # id товара хранится в скрытых данных строки таблицы, а не выводится отдельной колонкой.
        item = self.product_table.item(row, 0)
        return int(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def selected_product_id(self) -> int | None:
        selected = self.product_table.selectionModel().selectedRows()
        if not selected:
            return None
        return self.product_id_at_row(selected[0].row())

    def edit_selected_product(self) -> None:
        product_id = self.selected_product_id()
        if not product_id:
            show_error(self, "Не выбран товар", "Выберите строку товара для редактирования.")
            return
        self.open_product_dialog(product_id)

    def open_product_dialog(self, product_id: int | None) -> None:
        # Модальный диалог не дает открыть несколько окон редактирования одновременно.
        dialog = ProductFormDialog(self.repository, product_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_products()

    def delete_selected_product(self) -> None:
        # Перед удалением пользователь подтверждает необратимую операцию.
        product_id = self.selected_product_id()
        if not product_id:
            show_error(self, "Не выбран товар", "Выберите строку товара для удаления.")
            return
        if not confirm(self, "Удаление товара", "Удалить выбранный товар?"):
            return
        try:
            self.repository.delete_product(product_id)
            self.load_products()
            show_info(self, "Удаление товара", "Товар удален.")
        except Exception as exc:
            show_error(self, "Ошибка удаления", str(exc))

    def show_orders(self) -> None:
        # Экран заказов доступен менеджеру и администратору из панели товаров.
        if not self.current_user:
            return
        role = self.current_user["role_name"]
        self.setWindowTitle(f"МебельОрг - заказы ({role})")

        page = QWidget()
        root = QVBoxLayout(page)
        top = QHBoxLayout()
        title = QLabel("Заказы")
        title.setStyleSheet("font-size: 18pt; font-weight: 700;")
        user_label = QLabel(self.current_user["full_name"])
        back_button = QPushButton("Назад")
        back_button.clicked.connect(lambda: self.show_products(self.current_user))
        logout_button = QPushButton("Выйти")
        logout_button.clicked.connect(self.show_login)
        top.addWidget(title)
        top.addStretch()
        top.addWidget(user_label)
        top.addWidget(back_button)
        top.addWidget(logout_button)
        root.addLayout(top)

        if role == ROLE_ADMIN:
            # Управление заказами разрешено только администратору.
            controls = QHBoxLayout()
            add_button = QPushButton("Добавить заказ")
            add_button.clicked.connect(lambda: self.open_order_dialog(None))
            edit_button = QPushButton("Редактировать")
            edit_button.clicked.connect(self.edit_selected_order)
            delete_button = QPushButton("Удалить")
            delete_button.clicked.connect(self.delete_selected_order)
            controls.addWidget(add_button)
            controls.addWidget(edit_button)
            controls.addWidget(delete_button)
            controls.addStretch()
            root.addLayout(controls)

        self.orders_table = QTableWidget(0, 8)
        self.orders_table.setHorizontalHeaderLabels(
            [
                "Номер",
                "Артикулы",
                "Статус",
                "Пункт выдачи",
                "Дата заказа",
                "Дата выдачи",
                "Клиент",
                "Код",
            ]
        )
        self.orders_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.orders_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.orders_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.orders_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.orders_table.horizontalHeader().setStretchLastSection(True)
        if role == ROLE_ADMIN:
            self.orders_table.cellDoubleClicked.connect(
                lambda row, column: self.open_order_dialog(self.order_id_at_row(row))
            )
        root.addWidget(self.orders_table)
        self.setCentralWidget(page)
        self.load_orders()

    def load_orders(self) -> None:
        # Таблица заказов показывает шапку заказа и краткий список позиций.
        try:
            self.orders = self.repository.list_orders()
        except Exception as exc:
            show_error(self, "Ошибка загрузки заказов", str(exc))
            return

        self.orders_table.setRowCount(0)
        for row_index, order in enumerate(self.orders):
            self.orders_table.insertRow(row_index)
            values = [
                order["id"],
                order["items"],
                order["status_name"],
                order["pickup_address"],
                format_date(order["order_date"]),
                format_date(order["delivery_date"]),
                order["customer_name"] or "не указан",
                order["receive_code"] or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, int(order["id"]))
                self.orders_table.setItem(row_index, column, item)

    def order_id_at_row(self, row: int) -> int | None:
        item = self.orders_table.item(row, 0)
        return int(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def selected_order_id(self) -> int | None:
        selected = self.orders_table.selectionModel().selectedRows()
        if not selected:
            return None
        return self.order_id_at_row(selected[0].row())

    def edit_selected_order(self) -> None:
        order_id = self.selected_order_id()
        if not order_id:
            show_error(self, "Не выбран заказ", "Выберите строку заказа для редактирования.")
            return
        self.open_order_dialog(order_id)

    def open_order_dialog(self, order_id: int | None) -> None:
        # После сохранения заказа список сразу перечитывается из базы.
        dialog = OrderFormDialog(self.repository, order_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_orders()

    def delete_selected_order(self) -> None:
        # Позиции заказа удалятся каскадно вместе с заказом.
        order_id = self.selected_order_id()
        if not order_id:
            show_error(self, "Не выбран заказ", "Выберите строку заказа для удаления.")
            return
        if not confirm(self, "Удаление заказа", "Удалить выбранный заказ?"):
            return
        try:
            self.repository.delete_order(order_id)
            self.load_orders()
            show_info(self, "Удаление заказа", "Заказ удален.")
        except Exception as exc:
            show_error(self, "Ошибка удаления", str(exc))


def main() -> int:
    # Точка входа PyQt-приложения: стиль применяется до создания главного окна.
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)
    try:
        window = MainWindow()
    except Exception as exc:
        QMessageBox.critical(
            None,
            "Ошибка запуска",
            "Не удалось подключиться к базе данных.\n\n"
            "Проверьте настройки .env и выполните импорт:\n"
            "python scripts/import_data.py\n\n"
            f"Техническая информация: {exc}",
        )
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
