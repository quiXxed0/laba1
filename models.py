"""Модели предметной области «Запасы и склады»."""

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from typing import (Any, Optional, Union, cast, get_args, get_origin,
                    get_type_hints)

from exceptions import ValidationError


def now_iso() -> str:
    """Текущие дата и время в формате ISO (без микросекунд)."""
    return datetime.now().replace(microsecond=0).isoformat()


def _require(condition: bool, message: str) -> None:
    """Бросает ValidationError, если условие не выполнено."""
    if not condition:
        raise ValidationError(message)


def _coerce(value: Any, hint: Any) -> Any:
    """Приводит значение (например, строку из XML) к типу поля."""
    if get_origin(hint) is Union:  # Optional[X]
        if value is None or value == "":
            return None
        hint = next(a for a in get_args(hint) if a is not type(None))
    if hint is int:
        return int(value)
    if hint is float:
        return float(value)
    return "" if value is None else str(value)


@dataclass
class Entity:
    """Базовая сущность с идентификатором и (де)сериализацией."""

    id: int = 0

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Проверка полей; переопределяется в наследниках."""

    def to_dict(self) -> dict[str, Any]:
        """Плоский словарь для записи в JSON/XML."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Entity":
        """Создаёт объект из словаря с приведением типов."""
        hints = get_type_hints(cls)
        kwargs: dict[str, Any] = {}
        for item in fields(cls):
            if item.name not in data:
                continue
            try:
                kwargs[item.name] = _coerce(data[item.name], hints[item.name])
            except (TypeError, ValueError) as err:
                raise ValidationError(
                    f"Некорректное значение поля '{item.name}': "
                    f"{data[item.name]!r}"
                ) from err
        return cls(**kwargs)


@dataclass
class Category(Entity):
    """Категория товаров."""

    name: str = ""
    description: str = ""

    def validate(self) -> None:
        _require(bool(self.name.strip()), "Название категории пусто")


@dataclass
class Supplier(Entity):
    """Поставщик."""

    name: str = ""
    phone: str = ""
    email: str = ""

    def validate(self) -> None:
        _require(bool(self.name.strip()), "Название поставщика пусто")
        _require(not self.email or "@" in self.email, "Некорректный email")


@dataclass
class Product(Entity):
    """Товар (номенклатурная позиция)."""

    sku: str = ""
    name: str = ""
    category_id: Optional[int] = None
    supplier_id: Optional[int] = None
    unit_price: float = 0.0
    unit: str = "шт"

    def validate(self) -> None:
        _require(bool(self.sku.strip()), "Артикул товара пуст")
        _require(bool(self.name.strip()), "Название товара пусто")
        _require(self.unit_price >= 0, "Цена не может быть отрицательной")


@dataclass
class Employee(Entity):
    """Сотрудник склада."""

    full_name: str = ""
    position: str = ""

    def validate(self) -> None:
        _require(bool(self.full_name.strip()), "ФИО сотрудника пусто")


@dataclass
class Warehouse(Entity):
    """Склад."""

    name: str = ""
    city: str = ""
    address: str = ""
    capacity: int = 0  # максимальное число единиц товара
    manager_id: Optional[int] = None

    def validate(self) -> None:
        _require(bool(self.name.strip()), "Название склада пусто")
        _require(self.capacity > 0, "Вместимость должна быть больше 0")


@dataclass
class StockItem(Entity):
    """Остаток товара на конкретном складе."""

    warehouse_id: int = 0
    product_id: int = 0
    quantity: int = 0
    min_quantity: int = 0  # порог для отчёта о низком остатке

    def validate(self) -> None:
        _require(self.quantity >= 0, "Остаток не может быть отрицательным")
        _require(self.min_quantity >= 0, "Минимум не может быть < 0")


@dataclass
class StockMovement(Entity):
    """Базовое движение товара (приход, отгрузка, перемещение)."""

    kind: str = ""
    date: str = field(default_factory=now_iso)
    warehouse_id: int = 0
    product_id: int = 0
    quantity: int = 0
    employee_id: int = 0

    def validate(self) -> None:
        _require(self.quantity > 0, "Количество должно быть больше 0")
        try:
            datetime.fromisoformat(self.date)
        except ValueError as err:
            raise ValidationError(f"Неверная дата: {self.date!r}") from err


@dataclass
class Receipt(StockMovement):
    """Приход товара от поставщика."""

    supplier_id: int = 0

    def __post_init__(self) -> None:
        self.kind = "receipt"
        super().__post_init__()


@dataclass
class Shipment(StockMovement):
    """Отгрузка товара получателю."""

    recipient: str = ""

    def __post_init__(self) -> None:
        self.kind = "shipment"
        super().__post_init__()

    def validate(self) -> None:
        super().validate()
        _require(bool(self.recipient.strip()), "Получатель не указан")


@dataclass
class Transfer(StockMovement):
    """Перемещение товара между складами."""

    target_warehouse_id: int = 0

    def __post_init__(self) -> None:
        self.kind = "transfer"
        super().__post_init__()

    def validate(self) -> None:
        super().validate()
        _require(self.target_warehouse_id != self.warehouse_id,
                 "Склады отправления и назначения совпадают")


@dataclass
class InventoryCheck(Entity):
    """Инвентаризация: сравнение учётного и фактического остатка."""

    date: str = field(default_factory=now_iso)
    warehouse_id: int = 0
    product_id: int = 0
    expected: int = 0
    actual: int = 0
    employee_id: int = 0

    def validate(self) -> None:
        _require(self.expected >= 0 and self.actual >= 0,
                 "Количества не могут быть отрицательными")

    @property
    def difference(self) -> int:
        """Расхождение (факт минус учёт)."""
        return self.actual - self.expected


MOVEMENT_TYPES: dict[str, type[StockMovement]] = {
    "receipt": Receipt,
    "shipment": Shipment,
    "transfer": Transfer,
}

# Соответствие имён коллекций классам сущностей
ENTITY_TYPES: dict[str, type[Entity]] = {
    "categories": Category,
    "suppliers": Supplier,
    "products": Product,
    "employees": Employee,
    "warehouses": Warehouse,
    "stock": StockItem,
    "checks": InventoryCheck,
}


def movement_from_dict(data: dict[str, Any]) -> StockMovement:
    """Создаёт нужный подкласс движения по полю kind."""
    cls = MOVEMENT_TYPES.get(str(data.get("kind", "")))
    if cls is None:
        raise ValidationError(f"Неизвестный тип движения: {data.get('kind')}")
    return cast(StockMovement, cls.from_dict(data))
