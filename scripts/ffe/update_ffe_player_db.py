from dataclasses import dataclass

from database.sqlite.fide.fide_database import FideDatabase
from plugins.ffe.ffe_database import FfeDatabase
from plugins.ffe.utils import FFEArbiterTitle
from utils.enum import ArbiterTitle

FFE_ARBITER_TITLES: list[FFEArbiterTitle] = [
    FFEArbiterTitle.AFC,
    FFEArbiterTitle.AFO1,
    FFEArbiterTitle.AFO2,
    FFEArbiterTitle.AFE1,
    FFEArbiterTitle.AFE2,
]

HIGHLIGHTS: dict[FFEArbiterTitle, set[ArbiterTitle]] = {
    FFEArbiterTitle.AFC: {
        ArbiterTitle.NATIONAL,
        ArbiterTitle.FIDE,
        ArbiterTitle.INTERNATIONAL,
    },
    FFEArbiterTitle.AFO1: {
        ArbiterTitle.NATIONAL,
        ArbiterTitle.INTERNATIONAL,
    },
    FFEArbiterTitle.AFO2: {
        ArbiterTitle.NONE,
        ArbiterTitle.NATIONAL,
        ArbiterTitle.FIDE,
        ArbiterTitle.INTERNATIONAL,
    },
    FFEArbiterTitle.AFE1: {
        ArbiterTitle.NONE,
        ArbiterTitle.NATIONAL,
        ArbiterTitle.INTERNATIONAL,
    },
    FFEArbiterTitle.AFE2: {
        ArbiterTitle.NONE,
        ArbiterTitle.NATIONAL,
        ArbiterTitle.FIDE,
        ArbiterTitle.INTERNATIONAL,
    },
}


@dataclass
class FFEArbiter:
    ffe_arbiter_title: FFEArbiterTitle
    federation: str
    league: str
    name: str
    ffe_licence_number: str
    fide_id: int | None
    fide_arbiter_title: ArbiterTitle = ArbiterTitle.NONE


class FfeDatabaseWrapper(FfeDatabase):
    def get_ffe_arbiters_by_ffe_title(self) -> dict[FFEArbiterTitle, list[FFEArbiter]]:
        ffe_arbiters_by_ffe_title: dict[FFEArbiterTitle, list[FFEArbiter]] = {
            ffe_arbiter_title: [] for ffe_arbiter_title in FFE_ARBITER_TITLES
        }
        with self:
            self.execute(
                """
                SELECT arbiter.ffe_arbiter_title, player.federation, player.league, player.last_name, player.first_name, player.ffe_licence_number, player.fide_id
                FROM player
                JOIN arbiter ON arbiter.player_ffe_licence_number = player.ffe_licence_number
                ORDER BY arbiter.ffe_arbiter_title, player.federation, player.league, player.last_name, player.first_name
                """
            )
            for row in self.fetchall():
                ffe_arbiter_title: FFEArbiterTitle = FFEArbiterTitle(
                    row['ffe_arbiter_title']
                )
                if ffe_arbiter_title in FFE_ARBITER_TITLES:
                    ffe_arbiter: FFEArbiter = FFEArbiter(
                        ffe_arbiter_title=ffe_arbiter_title,
                        federation=row['federation'],
                        league=row['league'],
                        name=f'{row["last_name"]} {row["first_name"]}',
                        ffe_licence_number=row['ffe_licence_number'],
                        fide_id=row['fide_id'],
                    )
                    ffe_arbiters_by_ffe_title[ffe_arbiter.ffe_arbiter_title].append(
                        ffe_arbiter
                    )
        return ffe_arbiters_by_ffe_title


class FideDatabaseWrapper(FideDatabase):
    def get_ffe_arbiters_by_ffe_fide_title(
        self,
        ffe_arbiters_by_ffe_title: dict[FFEArbiterTitle, list[FFEArbiter]],
    ) -> dict[FFEArbiterTitle, dict[ArbiterTitle, list[FFEArbiter]]]:
        ffe_arbiters_by_ffe_fide_title: dict[
            FFEArbiterTitle, dict[ArbiterTitle, list[FFEArbiter]]
        ] = {
            ffe_arbiter_title: {
                fide_arbiter_title: [] for fide_arbiter_title in ArbiterTitle
            }
            for ffe_arbiter_title in FFE_ARBITER_TITLES
        }
        with self:
            for ffe_arbiter_title in FFE_ARBITER_TITLES:
                for ffe_arbiter in ffe_arbiters_by_ffe_title[ffe_arbiter_title]:
                    self.execute(
                        'SELECT arbiter.arbiter_title FROM arbiter WHERE player_fide_id = ?',
                        (ffe_arbiter.fide_id,),
                    )
                    if row := self.fetchone():
                        ffe_arbiter.fide_arbiter_title = ArbiterTitle(
                            row['arbiter_title']
                        )
                    ffe_arbiters_by_ffe_fide_title[ffe_arbiter_title][
                        ffe_arbiter.fide_arbiter_title
                    ].append(ffe_arbiter)
        return ffe_arbiters_by_ffe_fide_title


class Analyser:
    @staticmethod
    def run():
        ffe_database: FfeDatabaseWrapper = FfeDatabaseWrapper()
        if not ffe_database.exists():
            print('Updating the local FFE player database...')
            FfeDatabase()._update()
        ffe_arbiters_by_ffe_title: dict[FFEArbiterTitle, list[FFEArbiter]] = (
            ffe_database.get_ffe_arbiters_by_ffe_title()
        )
        fide_database: FideDatabaseWrapper = FideDatabaseWrapper()
        if not fide_database.exists():
            print('Updating the FIDE player database...')
            FideDatabase()._update()
        ffe_arbiters_by_ffe_fide_title: dict[
            FFEArbiterTitle, dict[ArbiterTitle, list[FFEArbiter]]
        ] = fide_database.get_ffe_arbiters_by_ffe_fide_title(ffe_arbiters_by_ffe_title)
        for (
            ffe_arbiter_title,
            ffe_arbiters_by_fide_title,
        ) in ffe_arbiters_by_ffe_fide_title.items():
            print(f'FFE arbiter title: {ffe_arbiter_title}')
            for fide_arbiter_title, ffe_arbiters in ffe_arbiters_by_fide_title.items():
                print(
                    f'- {ffe_arbiter_title.short_name}/{fide_arbiter_title.short_name}: {len(ffe_arbiters)}'
                )
                if fide_arbiter_title in HIGHLIGHTS[ffe_arbiter_title]:
                    for ffe_arbiter in ffe_arbiters:
                        print(
                            f'  - {ffe_arbiter_title.short_name}/{fide_arbiter_title.short_name} {ffe_arbiter.federation} {ffe_arbiter.league} {ffe_arbiter.name}'
                        )


if __name__ == '__main__':
    analyser = Analyser()
    analyser.run()
