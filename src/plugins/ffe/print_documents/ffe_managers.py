from typing import override

from plugins.ffe.print_documents import ffe_types
from plugins.ffe.print_documents.ffe_types import FFEDocumentType
from utils.entity import EntityManager


class FFEDocumentTypeManager(EntityManager[FFEDocumentType]):
    @override
    def entity_types(self) -> list[type[FFEDocumentType]]:
        return [
            ffe_types.FFET1Type,
            ffe_types.FFET2Type,
            ffe_types.FFET3Type,
            ffe_types.FFET4Type,
            ffe_types.FFET5Type,
            ffe_types.FFET6Type,
            ffe_types.FFET7Type,
            ffe_types.FFEArbiterCompensationType,
            ffe_types.FFECheatingType,
            # FIXME(Amaras): après une conversation avec le directeur des titres,
            # il est évident que toutes les ASP générées par Sharly Chess seront immédiatement
            # refusées.
            # J'ai décidé de les désactiver mais de garder le code.
            # TODO(Amaras): fix the template in a separate PR
            # ffe_types.FFETrainingCertificate1Type,
            # ffe_types.FFETrainingCertificate2Type,
        ]
