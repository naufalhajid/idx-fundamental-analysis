from dataclasses import asdict, fields
from typing import List, get_args, get_origin

from attr import dataclass


@dataclass
class BaseDataClass:
    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_orm(cls, orm_obj):
        data = {}
        for f in fields(cls):
            if not hasattr(orm_obj, f.name):
                continue

            value = getattr(orm_obj, f.name)
            field_type = f.type
            origin = get_origin(field_type)

            if origin in (list, List):
                args = get_args(field_type)
                item_type = args[0] if args else None
                if isinstance(item_type, type) and issubclass(item_type, BaseDataClass):
                    data[f.name] = [item_type.from_orm(item) for item in value or []]
                    continue

            if isinstance(field_type, type) and issubclass(field_type, BaseDataClass):
                if value is not None:
                    data[f.name] = field_type.from_orm(value)
                continue

            data[f.name] = value

        return cls(**data)
