"""Репозитории и бизнес-логика склада."""

from typing import Any, Callable, Generic, Optional, TypeVar, cast

from exceptions import (CapacityExceededError, DuplicateEntityError,
                        EntityNotFoundError, InsufficientStockError,
                        InventoryError, StorageError, ValidationError)
from models import (ENTITY_TYPES, Entity, InventoryCheck, Receipt, Shipment,
                    StockItem, StockMovement, Transfer, Warehouse,
                    movement_from_dict)

T = TypeVar("T", bound=Entity)


class Repository(Generic[T]):
    """Хранилище сущностей одного типа в памяти (CRUD)."""

    def __init__(self, title: str) -> None:
        self.title = title
        self._items: dict[int, T] = {}
        self._next_id = 1

    def add(self, item: T) -> T:
        """Create: добавляет сущность, при id=0 назначает новый id."""
        if item.id == 0:
            item.id = self._next_id
        elif item.id in self._items:
            raise DuplicateEntityError(self.title, item.id)
        self._items[item.id] = item
        self._next_id = max(self._next_id, item.id + 1)
        return item

    def get(self, entity_id: int) -> T:
        """Read: возвращает сущность по id."""
        try:
            return self._items[entity_id]
        except KeyError:
            raise EntityNotFoundError(self.title, entity_id) from None

    def update(self, item: T) -> T:
        """Update: заменяет существующую сущность."""
        self.get(item.id)
        self._items[item.id] = item
        return item

    def delete(self, entity_id: int) -> None:
        """Delete: удаляет сущность по id."""
        self.get(entity_id)
        del self._items[entity_id]

    def all(self) -> list[T]:
        """Список всех сущностей, отсортированный по id."""
        return [self._items[key] for key in sorted(self._items)]

    def find(self, predicate: Callable[[T], bool]) -> list[T]:
        """Сущности, удовлетворяющие условию."""
        return [item for item in self.all() if predicate(item)]

    def replace_all(self, items: list[T]) -> None:
        """Полностью заменяет содержимое (используется при загрузке)."""
        new_items: dict[int, T] = {}
        for item in items:
            if item.id <= 0:
                raise ValidationError("id должен быть положительным")
            if item.id in new_items:
                raise DuplicateEntityError(self.title, item.id)
            new_items[item.id] = item
        self._items = new_items
        self._next_id = max(new_items, default=0) + 1


# Ссылки между сущностями: коллекция -> [(поле, целевая коллекция)]
REFERENCES: dict[str, list[tuple[str, str]]] = {
    "products": [("category_id", "categories"),
                 ("supplier_id", "suppliers")],
    "warehouses": [("manager_id", "employees")],
    "stock": [("warehouse_id", "warehouses"), ("product_id", "products")],
}


class WarehouseService:
    """Фасад: CRUD по справочникам и складские операции."""

    def __init__(self) -> None:
        self.repos: dict[str, Repository[Any]] = {
            "categories": Repository("Категория"),
            "suppliers": Repository("Поставщик"),
            "products": Repository("Товар"),
            "employees": Repository("Сотрудник"),
            "warehouses": Repository("Склад"),
            "stock": Repository("Остаток"),
            "movements": Repository("Движение"),
            "checks": Repository("Инвентаризация"),
        }

    # ---------- универсальный CRUD ----------

    def _repo(self, collection: str) -> Repository[Any]:
        try:
            return self.repos[collection]
        except KeyError:
            raise InventoryError(
                f"Неизвестная коллекция: {collection}") from None

    def _check_refs(self, collection: str, entity: Entity) -> None:
        """Проверяет, что все внешние ссылки сущности существуют."""
        for field_name, target in REFERENCES.get(collection, []):
            ref = getattr(entity, field_name)
            if ref is not None:
                self.repos[target].get(ref)

    def add(self, collection: str, entity: Entity) -> Entity:
        self._check_refs(collection, entity)
        return cast(Entity, self._repo(collection).add(entity))

    def get(self, collection: str, entity_id: int) -> Entity:
        return cast(Entity, self._repo(collection).get(entity_id))

    def update(self, collection: str, entity: Entity) -> Entity:
        self._check_refs(collection, entity)
        return cast(Entity, self._repo(collection).update(entity))

    def delete(self, collection: str, entity_id: int) -> None:
        """Удаляет сущность, если на неё никто не ссылается."""
        self._repo(collection).get(entity_id)
        for source, refs in REFERENCES.items():
            for field_name, target in refs:
                if target != collection:
                    continue
                if any(getattr(item, field_name) == entity_id
                       for item in self.repos[source].all()):
                    raise InventoryError(
                        f"Нельзя удалить: запись используется в '{source}'")
        self._repo(collection).delete(entity_id)

    def list_all(self, collection: str) -> list[Entity]:
        return cast(list[Entity], self._repo(collection).all())

    # ---------- остатки ----------

    def _stock_of(self, warehouse_id: int,
                  product_id: int) -> Optional[StockItem]:
        found = self.repos["stock"].find(
            lambda s: s.warehouse_id == warehouse_id
                      and s.product_id == product_id)
        return found[0] if found else None

    def stock_quantity(self, warehouse_id: int, product_id: int) -> int:
        """Текущий остаток товара на складе."""
        item = self._stock_of(warehouse_id, product_id)
        return item.quantity if item else 0

    def warehouse_load(self, warehouse_id: int) -> int:
        """Суммарное количество единиц товара на складе."""
        return sum(s.quantity for s in self.repos["stock"].all()
                   if s.warehouse_id == warehouse_id)

    def _change_stock(self, warehouse_id: int, product_id: int,
                      delta: int) -> None:
        """Изменяет остаток с проверкой наличия и вместимости."""
        warehouse: Warehouse = self.repos["warehouses"].get(warehouse_id)
        self.repos["products"].get(product_id)
        if delta == 0:
            return
        item = self._stock_of(warehouse_id, product_id)
        current = item.quantity if item else 0
        if current + delta < 0:
            raise InsufficientStockError(product_id, -delta, current)
        load = self.warehouse_load(warehouse_id)
        if delta > 0 and load + delta > warehouse.capacity:
            raise CapacityExceededError(
                warehouse.name, warehouse.capacity, load, delta)
        if item is None:
            self.repos["stock"].add(StockItem(
                warehouse_id=warehouse_id, product_id=product_id,
                quantity=current + delta))
        else:
            item.quantity = current + delta

    # ---------- складские операции ----------

    def receive(self, warehouse_id: int, product_id: int, quantity: int,
                supplier_id: int, employee_id: int) -> StockMovement:
        """Приход товара на склад."""
        movement = Receipt(
            warehouse_id=warehouse_id, product_id=product_id,
            quantity=quantity, employee_id=employee_id,
            supplier_id=supplier_id)
        self.repos["suppliers"].get(supplier_id)
        self.repos["employees"].get(employee_id)
        self._change_stock(warehouse_id, product_id, quantity)
        return cast(StockMovement, self.repos["movements"].add(movement))

    def ship(self, warehouse_id: int, product_id: int, quantity: int,
             recipient: str, employee_id: int) -> StockMovement:
        """Отгрузка товара со склада."""
        movement = Shipment(
            warehouse_id=warehouse_id, product_id=product_id,
            quantity=quantity, employee_id=employee_id, recipient=recipient)
        self.repos["employees"].get(employee_id)
        self._change_stock(warehouse_id, product_id, -quantity)
        return cast(StockMovement, self.repos["movements"].add(movement))

    def transfer(self, source_id: int, target_id: int, product_id: int,
                 quantity: int, employee_id: int) -> StockMovement:
        """Перемещение товара между складами (с откатом при ошибке)."""
        movement = Transfer(
            warehouse_id=source_id, product_id=product_id,
            quantity=quantity, employee_id=employee_id,
            target_warehouse_id=target_id)
        self.repos["employees"].get(employee_id)
        self.repos["warehouses"].get(target_id)
        self._change_stock(source_id, product_id, -quantity)
        try:
            self._change_stock(target_id, product_id, quantity)
        except InventoryError:
            self._change_stock(source_id, product_id, quantity)  # откат
            raise
        return cast(StockMovement, self.repos["movements"].add(movement))

    def inventory_check(self, warehouse_id: int, product_id: int,
                        actual: int, employee_id: int) -> InventoryCheck:
        """Инвентаризация: фиксирует расхождение и корректирует остаток."""
        expected = self.stock_quantity(warehouse_id, product_id)
        check = InventoryCheck(
            warehouse_id=warehouse_id, product_id=product_id,
            expected=expected, actual=actual, employee_id=employee_id)
        self.repos["employees"].get(employee_id)
        self._change_stock(warehouse_id, product_id, actual - expected)
        return cast(InventoryCheck, self.repos["checks"].add(check))

    # ---------- отчёты ----------

    def stock_report(self, warehouse_id: int) -> list[tuple[str, int, int]]:
        """Строки отчёта: (название товара, остаток, минимум)."""
        self.repos["warehouses"].get(warehouse_id)
        return [
            (self.repos["products"].get(s.product_id).name,
             s.quantity, s.min_quantity)
            for s in self.repos["stock"].all()
            if s.warehouse_id == warehouse_id
        ]

    def low_stock(self) -> list[StockItem]:
        """Позиции, остаток которых ниже минимального порога."""
        return self.repos["stock"].find(
            lambda s: s.min_quantity > 0 and s.quantity < s.min_quantity)

    # ---------- (де)сериализация ----------

    def to_data(self) -> dict[str, list[dict[str, Any]]]:
        """Все данные в виде словаря для JSON/XML."""
        return {name: [item.to_dict() for item in repo.all()]
                for name, repo in self.repos.items()}

    def load_data(self, data: dict[str, list[dict[str, Any]]]) -> None:
        """Загружает данные; при ошибке разбора текущие данные целы."""
        parsed: dict[str, list[Entity]] = {}
        try:
            for name in self.repos:
                records = data.get(name, [])
                if name == "movements":
                    parsed[name] = [movement_from_dict(r) for r in records]
                else:
                    parsed[name] = [ENTITY_TYPES[name].from_dict(r)
                                    for r in records]
        except (TypeError, AttributeError) as err:
            raise StorageError("Неверная структура данных файла") from err
        for name, repo in self.repos.items():
            repo.replace_all(parsed[name])
