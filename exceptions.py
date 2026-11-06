"""Собственные исключения приложения «Запасы и склады»."""


class InventoryError(Exception):
    """Базовое исключение приложения."""


class ValidationError(InventoryError):
    """Некорректные данные сущности."""


class EntityNotFoundError(InventoryError):
    """Сущность с указанным id не найдена."""

    def __init__(self, title: str, entity_id: int) -> None:
        super().__init__(f"{title} с id={entity_id} не найден(а)")
        self.title = title
        self.entity_id = entity_id


class DuplicateEntityError(InventoryError):
    """Сущность с таким id уже существует."""

    def __init__(self, title: str, entity_id: int) -> None:
        super().__init__(f"{title} с id={entity_id} уже существует")
        self.title = title
        self.entity_id = entity_id


class InsufficientStockError(InventoryError):
    """На складе недостаточно товара для операции."""

    def __init__(self, product_id: int, requested: int,
                 available: int) -> None:
        super().__init__(
            f"Недостаточно товара id={product_id}: "
            f"нужно {requested}, доступно {available}"
        )
        self.product_id = product_id
        self.requested = requested
        self.available = available


class CapacityExceededError(InventoryError):
    """Превышена вместимость склада."""

    def __init__(self, warehouse: str, capacity: int, load: int,
                 incoming: int) -> None:
        super().__init__(
            f"Склад '{warehouse}': вместимость {capacity}, занято {load}, "
            f"поступает {incoming}"
        )
        self.warehouse = warehouse
        self.capacity = capacity
        self.load = load
        self.incoming = incoming


class StorageError(InventoryError):
    """Ошибка чтения или записи файла (JSON/XML)."""