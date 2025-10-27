from typing import override
from data.print_documents import (
    documents,
    options,
    player_splitters,
    player_sorters,
    pairing_styles,
    qrcode_types,
)
from data.print_documents.documents import PrintDocument
from data.print_documents.options import PrintOption
from data.print_documents.pairing_styles import PairingStyle
from data.print_documents.player_sorters import PlayerSorter
from data.print_documents.player_splitters import PlayerSplitter
from data.print_documents.qrcode_types import QRCodeType
from plugins.manager import plugin_manager
from utils.entity import EventBoundEntityManager


class PrintDocumentManager(EventBoundEntityManager[PrintDocument]):
    @override
    def entity_types(self) -> list[type[PrintDocument]]:
        return [
            documents.PlayerListPrintDocument,
            documents.PlayerCheckinListPrintDocument,
            documents.PairingPrintDocument,
            documents.ResultPrintDocument,
            documents.PlayerRankingPrintDocument,
            documents.PlayerCrosstablePrintDocument,
            documents.PlayerRoundPerformanceIndicatorPrintDocument,
            documents.BergerGridPrintDocument,
            documents.PrizeListPrintDocument,
            documents.PrizeAssignmentPrintDocument,
            documents.StatisticsPrintDocument,
            documents.NormReportPrintDocument,
            documents.QRCodePrintDocument,
            documents.PlayerCardsPrintDocument,
            documents.BoardCardsPrintDocument,
        ]

    @override
    def objects(self) -> list[PrintDocument]:
        return [type_(self.event) for type_ in self.entity_types()]


class PrintDocumentOptionManager(EventBoundEntityManager[PrintOption]):
    @override
    def entity_types(self) -> list[type[options.PrintOption]]:
        return [
            options.QRCodePrintOption,
            options.TournamentPrintOption,
            options.TournamentsPrintOption,
            options.PlayerPrintOption,
            options.PairingStylePrintOption,
            options.RoundPrintOption,
            options.PlayerSplitPrintOption,
            options.PlayerSortPrintOption,
            options.ShowWarningsPrintOption,
            options.ClubThresholdPrintOption,
            options.QRCodeNetworkPrintOption,
        ]

    @override
    def objects(self) -> list[PrintOption]:
        return [type_(self.event) for type_ in self.entity_types()]


class PrintPlayerSplitterManager(EventBoundEntityManager[PlayerSplitter]):
    @override
    def entity_types(self) -> list[type[PlayerSplitter]]:
        splitters = [
            player_splitters.NoSplitPlayerSplitter,
            player_splitters.CategoryPlayerSplitter,
            player_splitters.ClubPlayerSplitter,
            player_splitters.FederationPlayerSplitter,
        ]
        plugin_manager.hook_for_event(self.event, 'insert_print_player_splitter_types')(
            player_splitter_types=splitters
        )
        return splitters


class PrintPlayerSorterManager(EventBoundEntityManager[PlayerSorter]):
    @override
    def entity_types(self) -> list[type[PlayerSorter]]:
        return [
            player_sorters.NamePlayerSorter,
            player_sorters.RankPlayerSorter,
            player_sorters.StartingRankPlayerSorter,
            player_sorters.PairingNumberPlayerSorter,
        ]


class PrintPairingStyleManager(EventBoundEntityManager[PairingStyle]):
    @override
    def entity_types(self) -> list[type[PairingStyle]]:
        return [
            pairing_styles.BoardsPairingStyle,
            pairing_styles.PlayersPairingStyleSorter,
        ]


class PrintQRCodeTypeManager(EventBoundEntityManager[QRCodeType]):
    @override
    def entity_types(self) -> list[type[QRCodeType]]:
        types: list[type[QRCodeType]] = [
            qrcode_types.NetworkQRCodeType,
        ]
        plugin_manager.hook_for_event(self.event, 'insert_print_qrcode_types')(
            qrcode_types=types
        )
        return types
