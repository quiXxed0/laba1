"""Чтение и запись данных в форматах JSON и XML."""

import json
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Union

from exceptions import StorageError

Data = dict[str, list[dict[str, Any]]]
PathLike = Union[str, Path]

# Имя элемента XML для записи каждой коллекции
ITEM_TAGS: dict[str, str] = {
    "categories": "category",
    "suppliers": "supplier",
    "products": "product",
    "employees": "employee",
    "warehouses": "warehouse",
    "stock": "stock_item",
    "movements": "movement",
    "checks": "check",
}


class BaseStorage(ABC):
    """Интерфейс хранилища данных в файле."""

    @abstractmethod
    def save(self, data: Data, path: PathLike) -> None:
        """Записывает данные в файл."""

    @abstractmethod
    def load(self, path: PathLike) -> Data:
        """Читает данные из файла."""


class JsonStorage(BaseStorage):
    """Хранилище в формате JSON."""

    def save(self, data: Data, path: PathLike) -> None:
        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
        except (OSError, TypeError) as err:
            raise StorageError(f"Не удалось записать JSON: {err}") from err

    def load(self, path: PathLike) -> Data:
        try:
            with open(path, encoding="utf-8") as file:
                data = json.load(file)
        except FileNotFoundError:
            raise StorageError(f"Файл не найден: {path}") from None
        except (OSError, json.JSONDecodeError) as err:
            raise StorageError(f"Не удалось прочитать JSON: {err}") from err
        if not isinstance(data, dict):
            raise StorageError("Корень JSON должен быть объектом")
        return data


class XmlStorage(BaseStorage):
    """Хранилище в формате XML.

    Структура: <inventory><products><product><name>..</name></product>
    ...</products>...</inventory>
    """

    ROOT_TAG = "inventory"

    def save(self, data: Data, path: PathLike) -> None:
        root = ET.Element(self.ROOT_TAG)
        for collection, records in data.items():
            parent = ET.SubElement(root, collection)
            tag = ITEM_TAGS.get(collection, "item")
            for record in records:
                element = ET.SubElement(parent, tag)
                for key, value in record.items():
                    child = ET.SubElement(element, key)
                    child.text = "" if value is None else str(value)
        ET.indent(root)  # красивое форматирование (Python 3.9+)
        try:
            ET.ElementTree(root).write(
                path, encoding="utf-8", xml_declaration=True)
        except OSError as err:
            raise StorageError(f"Не удалось записать XML: {err}") from err

    def load(self, path: PathLike) -> Data:
        try:
            root = ET.parse(path).getroot()
        except FileNotFoundError:
            raise StorageError(f"Файл не найден: {path}") from None
        except (OSError, ET.ParseError) as err:
            raise StorageError(f"Не удалось прочитать XML: {err}") from err
        if root.tag != self.ROOT_TAG:
            raise StorageError(f"Ожидался корень <{self.ROOT_TAG}>")
        return {
            parent.tag: [
                {child.tag: child.text or "" for child in element}
                for element in parent
            ]
            for parent in root
        }
