"""Консольное приложение «Запасы и склады»."""

from dataclasses import fields
from typing import Callable, get_type_hints

from exceptions import InventoryError
from models import Category, Employee, Entity, Product, Supplier, Warehouse
from services import WarehouseService
from storage import BaseStorage, JsonStorage, XmlStorage

TITLES: dict[str, str] = {
    "categories": "Категории",
    "suppliers": "Поставщики",
    "products": "Товары",
    "employees": "Сотрудники",
    "warehouses": "Склады",
    "stock": "Остатки",
    "movements": "Движения (только просмотр)",
    "checks": "Инвентаризации (только просмотр)",
}
EDITABLE = ["categories", "suppliers", "products", "employees",
            "warehouses", "stock"]


def ask_int(prompt: str) -> int:
    """Запрашивает целое число (ValueError обрабатывается выше)."""
    return int(input(prompt).strip())


def choose_collection(only_editable: bool) -> str:
    """Выбор справочника из списка."""
    names = EDITABLE if only_editable else list(TITLES)
    for number, name in enumerate(names, 1):
        print(f"  {number}. {TITLES[name]}")
    index = ask_int("Номер: ")
    if not 1 <= index <= len(names):
        raise ValueError("нет такого пункта")
    return names[index - 1]


def format_entity(entity: Entity) -> str:
    return "; ".join(f"{k}={v}" for k, v in entity.to_dict().items())


def list_entities(service: WarehouseService) -> None:
    collection = choose_collection(False)
    items = service.list_all(collection)
    if not items:
        print("Записей нет")
    for item in items:
        print(format_entity(item))


def add_entity(service: WarehouseService) -> None:
    collection = choose_collection(True)
    cls = type(service.repos[collection]).__mro__  # noqa: F841
    from models import ENTITY_TYPES  # локальный импорт для краткости
    cls = ENTITY_TYPES[collection]
    values: dict[str, str] = {}
    hints = get_type_hints(cls)
    for item in fields(cls):
        if item.name == "id":
            continue
        raw = input(f"{item.name} ({hints[item.name]}), Enter = по умолчанию: ")
        if raw.strip():
            values[item.name] = raw.strip()
    created = service.add(collection, cls.from_dict(values))
    print(f"Создано: {format_entity(created)}")


def edit_entity(service: WarehouseService) -> None:
    collection = choose_collection(True)
    old = service.get(collection, ask_int("id: "))
    print(format_entity(old))
    field_name = input("Какое поле изменить: ").strip()
    if field_name not in old.to_dict() or field_name == "id":
        raise ValueError(f"нельзя изменить поле '{field_name}'")
    data = old.to_dict()
    data[field_name] = input("Новое значение: ").strip()
    new = type(old).from_dict(data)
    new.id = old.id
    service.update(collection, new)
    print("Обновлено")


def delete_entity(service: WarehouseService) -> None:
    collection = choose_collection(True)
    service.delete(collection, ask_int("id: "))
    print("Удалено")


def op_receive(service: WarehouseService) -> None:
    service.receive(ask_int("id склада: "), ask_int("id товара: "),
                    ask_int("Количество: "), ask_int("id поставщика: "),
                    ask_int("id сотрудника: "))
    print("Приход оформлен")


def op_ship(service: WarehouseService) -> None:
    service.ship(ask_int("id склада: "), ask_int("id товара: "),
                 ask_int("Количество: "), input("Получатель: ").strip(),
                 ask_int("id сотрудника: "))
    print("Отгрузка оформлена")


def op_transfer(service: WarehouseService) -> None:
    service.transfer(ask_int("id склада-источника: "),
                     ask_int("id склада-назначения: "),
                     ask_int("id товара: "), ask_int("Количество: "),
                     ask_int("id сотрудника: "))
    print("Перемещение оформлено")


def op_inventory(service: WarehouseService) -> None:
    check = service.inventory_check(
        ask_int("id склада: "), ask_int("id товара: "),
        ask_int("Фактический остаток: "), ask_int("id сотрудника: "))
    print(f"Расхождение: {check.difference:+d}")


def op_report(service: WarehouseService) -> None:
    warehouse_id = ask_int("id склада: ")
    rows = service.stock_report(warehouse_id)
    for name, quantity, minimum in rows:
        print(f"{name}: {quantity} (мин. {minimum})")
    print(f"Всего единиц на складе: {service.warehouse_load(warehouse_id)}")


def op_low_stock(service: WarehouseService) -> None:
    items = service.low_stock()
    if not items:
        print("Позиций с низким остатком нет")
    for item in items:
        print(format_entity(item))


def make_file_action(storage: BaseStorage, default: str,
                     saving: bool) -> Callable[[WarehouseService], None]:
    """Создаёт действие сохранения/загрузки для заданного формата."""

    def action(service: WarehouseService) -> None:
        path = input(f"Файл [{default}]: ").strip() or default
        if saving:
            storage.save(service.to_data(), path)
            print(f"Сохранено в {path}")
        else:
            service.load_data(storage.load(path))
            print(f"Загружено из {path}")

    return action


def seed_demo(service: WarehouseService) -> None:
    """Заполняет систему демонстрационными данными."""
    service.add("categories", Category(name="Электроника"))
    service.add("suppliers", Supplier(name="ТехноПоставка",
                                      phone="+7 495 000-00-00",
                                      email="info@tp.example"))
    service.add("employees", Employee(full_name="Иванов И.И.",
                                      position="Кладовщик"))
    service.add("products", Product(sku="LP-001", name="Ноутбук",
                                    category_id=1, supplier_id=1,
                                    unit_price=75000.0))
    service.add("warehouses", Warehouse(name="Центральный", city="Москва",
                                        address="ул. Складская, 1",
                                        capacity=500, manager_id=1))
    service.add("warehouses", Warehouse(name="Южный", city="Краснодар",
                                        address="ул. Южная, 5",
                                        capacity=100))
    service.receive(1, 1, 50, 1, 1)
    print("Демо-данные загружены")


ACTIONS: dict[str, tuple[str, Callable[[WarehouseService], None]]] = {
    "1": ("Просмотр справочника", list_entities),
    "2": ("Добавить запись", add_entity),
    "3": ("Изменить запись", edit_entity),
    "4": ("Удалить запись", delete_entity),
    "5": ("Приход товара", op_receive),
    "6": ("Отгрузка товара", op_ship),
    "7": ("Перемещение между складами", op_transfer),
    "8": ("Инвентаризация", op_inventory),
    "9": ("Остатки на складе", op_report),
    "10": ("Товары с низким остатком", op_low_stock),
    "11": ("Сохранить в JSON",
           make_file_action(JsonStorage(), "data.json", True)),
    "12": ("Загрузить из JSON",
           make_file_action(JsonStorage(), "data.json", False)),
    "13": ("Сохранить в XML",
           make_file_action(XmlStorage(), "data.xml", True)),
    "14": ("Загрузить из XML",
           make_file_action(XmlStorage(), "data.xml", False)),
    "15": ("Загрузить демо-данные", seed_demo),
}


def main() -> None:
    service = WarehouseService()
    while True:
        print("\n=== Запасы и склады ===")
        for key, (title, _) in ACTIONS.items():
            print(f"{key}. {title}")
        print("0. Выход")
        try:
            choice = input("Выбор: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if choice == "0":
            break
        action = ACTIONS.get(choice)
        if action is None:
            print("Нет такого пункта меню")
            continue
        try:
            action[1](service)
        except InventoryError as err:  # собственные исключения
            print(f"Ошибка: {err}")
        except ValueError as err:  # неверный ввод числа и т.п.
            print(f"Некорректный ввод: {err}")
        except KeyboardInterrupt:
            print("\nОперация отменена")
        except Exception as err:  # последний рубеж: программа не падает
            print(f"Непредвиденная ошибка: {err}")


if __name__ == "__main__":
    main()
