from typing import override

from plugins.ffe.print_documents import ffe_types
from plugins.ffe.print_documents.ffe_types import FFEDocumentType
from utils.entity import EntityManager


class FFEDocumentTypeManager(EntityManager[FFEDocumentType]):
    @override
    def entity_types(self) -> list[type[FFEDocumentType]]:
        return [
            ffe_types.FFET1T2Type,
            ffe_types.FFET3T4Type,
            ffe_types.FFET5Type,
            ffe_types.FFET6Type,
            ffe_types.FFET7Type,
            ffe_types.FFEArbiterCompensationType,
        ]
