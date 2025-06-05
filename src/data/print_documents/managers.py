from data.print_documents import documents, options, player_splitters, player_sorters
from data.print_documents.documents import PrintDocument
from data.print_documents.options import PrintOption
from data.print_documents.player_sorters import PlayerSorter
from data.print_documents.player_splitters import PlayerSplitter
from plugins.manager import plugin_manager
from utils.entity import EntityManager


class PrintDocumentManager(EntityManager[PrintDocument]):
    @staticmethod
    def entity_types() -> list[type[PrintDocument]]:
        return [
            documents.PlayerListPrintDocument,
            documents.PlayerCheckinListPrintDocument,
            documents.PairingPrintDocument,
            documents.ResultPrintDocument,
            documents.PlayerRankingPrintDocument,
            documents.PlayerCrosstablePrintDocument,
            documents.BergerGridPrintDocument,
        ]


class PrintDocumentOptionManager(EntityManager[PrintOption]):
    @staticmethod
    def entity_types() -> list[type[options.PrintOption]]:
        return [
            options.RoundPrintOption,
            options.PlayerSplitPrintOption,
            options.PlayerSortPrintOption,
        ]


class PrintPlayerSplitterManager(EntityManager[PlayerSplitter]):
    @staticmethod
    def entity_types() -> list[type[PlayerSplitter]]:
        splitters = [
            player_splitters.NoSplitPlayerSplitter,
            player_splitters.CategoryPlayerSplitter,
            player_splitters.ClubPlayerSplitter,
            player_splitters.FederationPlayerSplitter,
        ]
        plugin_manager.hook.insert_print_player_splitter_types(
            player_splitter_types=splitters
        )
        return splitters


class PrintPlayerSorterManager(EntityManager[PlayerSorter]):
    @staticmethod
    def entity_types() -> list[type[PlayerSorter]]:
        return [
            player_sorters.NamePlayerSorter,
            player_sorters.RankPlayerSorter,
            player_sorters.StartingRankPlayerSorter,
            player_sorters.PairingNumberPlayerSorter,
        ]
