# _Sharly Chess_ - National rating lists

The _FFE_ database is built on a server and downloaded ready to use. The _FIDE_ database and the other national databases are built by the application itself: it downloads the file the federation publishes and converts it into a local database (see the national player table in [the description of the databases](databases.md)).

Each list is activated with the first event of its federation (or from the data sources modal) and refreshed like the other local databases.

The lists differ a lot in what they carry. This page records, for each of them, where the file comes from, what is read, what the file does not have, and what it has that the application does not use yet.

## FIDE (`fide`)

`FIDE_SOURCE` in `src/database/sqlite/fide/fide_database.py` chooses between this conversion and the ready-made database of the _GitHub_ releases, built by the same conversion on a server.

| | |
|---|---|
| Source | `https://ratings.fide.com/download/players_list_xml_legacy.zip` (the monthly list, published on the 1st) |
| Format | ZIP → one XML file (about 800 MB, read straight out of the archive) |
| Elements | `<player>`: `fideid`, `name`, `country`, `sex`, `title`, `w_title`, `o_title`, `rating`, `games`, `k`, `rapid_rating`, `rapid_games`, `rapid_k`, `blitz_rating`, `blitz_games`, `blitz_k`, `birthday`, `flag` |
| Identifier | `fideid` |
| Read | `name` (written `Last name, First name`), `country`, `sex`, `title` (open titles only: `title` holds the highest title, which may be a women's one), `w_title`, `o_title` (the arbiter title among `NA`, `FA`, `IA`), the three ratings and K factors, `birthday` (year) |
| Missing | full date of birth, club |
| Unused | `games` counts, `flag` (inactivity `i`, women `w`), the trainer and organiser titles of `o_title` |

## KNSB - Netherlands (`knsb`)

| | |
|---|---|
| Source | `https://schaakbond.nl/wp-content/uploads/2024/12/KLASSIEK.zip`, `.../2024/10/RAPID.zip`, `.../2024/10/SNEL.zip` (the KNSB keeps these links for the current lists) |
| Format | ZIP → CSV, `;`-separated, cp1252, one file per rate of play |
| Columns | `Relatienummer;Naam;Titel;FED;Rating;Nv;Geboren;S` |
| Identifier | `Relatienummer` |
| Read | name (`Naam`, written `Last name, First name`), `Titel` (FIDE title), `FED`, `Geboren` (year of birth), `S` (`w` for the women, blank for the men), the rating of each of the three lists |
| Missing | _FIDE_ ID and ratings, club, full date of birth |
| Unused | `Nv` (number of rated games) |

## FSI - Italy (`fsi`)

| | |
|---|---|
| Source | `https://www.torneionline.com/dwn/allin.csv` (the "ALLIN" export of the FSI site) |
| Format | CSV, `;`-separated, UTF-8 |
| Columns | `Nominativo;Elo;Categoria;K Italia;Federazione;Anno Nascita;ID FSI;Sex;FIN;Elo FIDE Std;K Elo FIDE Std;Games Elo FIDE Std;Elo FIDE Rapid;…;Elo FIDE Blitz;…;Attivo;Data Nascita;Provincia Residenza;Regione Residenza;Provincia Tesseramento;Regione Tesseramento;Cittadinanza;Data Ultimo Torneo;Circolo Attuale;Circolo Anno Precedente;Circolo Due Anni Precedenti;Anno Ultimo Tesseramento;Tipo Tessera;Numero Tessera` |
| Identifier | `ID FSI` (the rows without one are placeholders of the export and are skipped) |
| Read | name (`Nominativo`, written `LAST NAME First name`; a name in capitals only gives its first word as the last name), `Elo` (Elo Italia, standard only), `Federazione`, `Data Nascita` / `Anno Nascita`, `Sex`, `FIN` (_FIDE_ ID), the three _FIDE_ ratings |
| Missing | club (`Circolo Attuale` is a numeric code), title, national rapid and blitz ratings |
| Unused | `Categoria` (national category: NC, 3N, 2N, 1N, CM…), `K Italia`, `Attivo`, province and region of residence and of registration, `Cittadinanza`, `Data Ultimo Torneo`, `Tipo Tessera` / `Numero Tessera` / `Anno Ultimo Tesseramento` (the membership, the closest thing to the _FFE_ licence), the _FIDE_ K factors and game counts |

## CFR - Russia (`cfr`)

| | |
|---|---|
| Source | `https://ratings.ruchess.ru/api/smanager_standard.csv.zip`, `smanager_rapid.csv.zip`, `smanager_blitz.csv.zip` (refreshed every 20 minutes) |
| Format | ZIP → CSV, `,`-separated, UTF-8 with BOM, one file per rate of play |
| Columns | `ID_No,Name,Sex,Fed,Clubnumber,ClubName,Birthday,Rtg_Nat,Fide_No,Rtg_Int` |
| Identifier | `ID_No` |
| Read | name (`Name`, written `Last name First name Patronymic` in Cyrillic: the first word is the last name), `Sex` (`f` for the women, blank for the men), `Fed`, `Birthday` (year), `ClubName` (the regional federation, stored as the club), `Fide_No`, `Rtg_Nat` of each list, `Rtg_Int` (standard) |
| Missing | full date of birth, title, club (the region stands in) |
| Unused | `Clubnumber` (region code) |

Names are Cyrillic only; the search transliterates (`bondarenko` finds `Бондаренко`).

## SELO - Finland (`ssl`)

| | |
|---|---|
| Source | `https://www.shakki.net/cgi-bin/selo?do=selo&…&muoto=csv&…&sivpit=10000` (the CSV export of the SELO service of the Finnish federation) |
| Format | CSV, `;`-separated, cp1252 |
| Columns | `Id;Sukunimi;Etunimi;Seura;Selo;Selopelejä;Ikäryhmä;Maa;Lisenssi` |
| Identifier | `Id` |
| Read | `Sukunimi` (last name), `Etunimi` (first name), `Seura` (club), `Selo` (standard), `Maa` (federation) |
| Missing | year of birth (so no age category), gender, _FIDE_ ID and ratings, title, rapid and blitz ratings |
| Unused | `Lisenssi` (`L` when the player holds a licence), `Ikäryhmä` (age group: `U12`, `S50`…, not a year), `Selopelejä` (number of rated games) |

## CFC - Canada (`cfc`)

| | |
|---|---|
| Source | `https://storage.googleapis.com/cfc-public/data/tdlist.txt` |
| Format | CSV, `,`-separated, with a broken quoting (the city carries a stray quote: every field is stripped of its quotes) |
| Columns | `CFC#,Expiry,Last,First,Prov,City,Rating,High,Active Rtg,Active High,FIDE Number,FIDE Rating` |
| Identifier | `CFC#` (the rows without a name, `---`, are skipped) |
| Read | `Last`, `First`, `City` (stored as the club), `Rating` (regular, standard), `Active Rtg` (quick, used for rapid and blitz), `FIDE Number`, `FIDE Rating` (standard) |
| Missing | year of birth (so no age category), gender, title, club |
| Unused | `Expiry` (membership expiry date, the closest thing to a licence), `Prov` (province), `High` / `Active High` (peak ratings) |

## DSB - Germany (`dsb`)

| | |
|---|---|
| Source | `https://www.schachbund.de/download-dwz-daten.html?file=files/wertungsportal/downloads/export/csv/LV-0-csv.zip` (the daily export of the Wertungsportal, refreshed at 04:15) |
| Format | ZIP → `spieler.csv`, `vereine.csv`, `verbaende.csv`, `,`-separated, cp1252 |
| Columns | `spieler.csv`: `ID,ZPS,Mitgliedsnummer,Status,"Name,Vorname",Geschlecht,Spielberechtigung,Geburtsjahr,"Letzte Auswertung",DWZ,Index,FIDE-Elozahl,FIDE-Titel,FIDE-ID,FIDE-Land,Vorname,Nachname,FIDE-Frauentitel,FIDE-Elozahl-Schnellschach,FIDE-Elozahl-Blitz`; `vereine.csv`: `ZPS-Nummer,Landesverband,UebergeordneterVerband,Vereinsname` |
| Identifier | `ID` (a player belonging to several clubs has one row per club: the active membership, `Status` `A`, wins over a passive one, `P`, which wins over none) |
| Read | `Nachname`, `Vorname`, `Geschlecht` (`M`/`W`), `Geburtsjahr`, `FIDE-Titel` (or `FIDE-Frauentitel`), `FIDE-Land`, the club name through `ZPS`, `FIDE-ID`, `DWZ` (standard), the three _FIDE_ ratings |
| Missing | full date of birth, national rapid and blitz ratings (the DWZ is one rating) |
| Unused | `Status` beyond the choice of the row, `Mitgliedsnummer` (membership number in the club, not unique), `Letzte Auswertung` (last rating period, YYYYWW), `Index`, the club's regional association (`Landesverband`, `verbaende.csv`) |

The README of the export states that publishing the data needs the agreement of the DSB's DWZ officer: the application downloads it for the user's own use only.

## ECF - England (`ecf`)

| | |
|---|---|
| Source | `https://rating.englishchess.org.uk/api/rating-list/csv` |
| Format | CSV, `,`-separated, UTF-8 |
| Columns | `ECF_code,full_name,member_no,FIDE_no,gender,nation,original_standard,standard_original_category,revised_standard,standard_revised_category,original_rapid,…,revised_rapid,…,original_blitz,…,revised_blitz,…` (the same four for the online ratings) `,club_code,club_name,title` |
| Identifier | `ECF_code` |
| Read | `full_name` (written `Last name, First name`), `gender`, `nation`, `club_name`, `FIDE_no`, `title`, `revised_standard` / `revised_rapid` / `revised_blitz` |
| Missing | year of birth (so no age category), full date of birth, _FIDE_ ratings (the _FIDE_ database fills them) |
| Unused | `member_no` (membership number), the rating categories (`A`…`K`, the reliability of each rating), the `original_*` ratings (before the monthly revision), the online ratings, `club_code` |

## CHESSA - South Africa (`chessa`)

| | |
|---|---|
| Source | `https://ratings.chessa.co.za/downloads/ratings_main.zip`, `ratings_rapid.zip`, `ratings_blitz.zip` |
| Format | ZIP → CSV, `,`-separated, UTF-8, one file per rate of play (the "main" one is the classical list) |
| Columns | `UNIQUE_NO,SURNAME,FIRSTNAME,BDATE,SEX,TITLE,RATING,FED` |
| Identifier | `UNIQUE_NO` |
| Read | names, `BDATE` (full date, `1900/01/01` for none), `SEX`, `TITLE`, `FED` (the regional federation, stored as the club), the rating of each of the three lists |
| Missing | _FIDE_ ID and ratings, club |
| Unused | the `ratings_standard` and `ratings_cfplay` lists, the `mini-` (active players only) variants |

## LOK - Czech Republic (`lok`)

| | |
|---|---|
| Source | `https://elo.miramal.com/download/lok_sm_cz.xls` and `rapid_lok_sm_cz.xls` (the Swiss-Manager exports of the ŠSČR rating site) |
| Format | binary Excel (`.xls`, read with `xlrd`), one file per rate of play |
| Columns | `ID_no, Name, ClubName, BirthDay, Sex, Rtg_nat, Rtg_int, Title, FIDE_no, Fed, ClubNo, Status, PARTIE, BODY, SUMA_ELO` |
| Identifier | `ID_no` |
| Read | `Name` (written `Last name First name`), `ClubName`, `BirthDay` (`dd.mm.yyyy`, `00.00.yyyy` for a year alone), `Sex` (`f` for the women), `Title`, `FIDE_no`, `Fed`, `Rtg_nat` of each list, `Rtg_int` (standard) |
| Missing | blitz ratings |
| Unused | `Status` (A: active, N: not), `PARTIE`/`BODY`/`SUMA_ELO` (games, points and rating sum of the period), `ClubNo` |

## UCF - Ukraine (`ucf`)

| | |
|---|---|
| Source | `https://www.ukrchess.org.ua/kvalif/<yyyy>/<mm>/nat<yy><mm>s.zip` (the Swiss-Manager list of the qualification commission; the current month is found on the federation's home page) |
| Format | ZIP → binary Excel (`.xls`, cp1251 strings) |
| Columns | `Fide_No, Name, Fed, Sex, Rtg_Nat, Rtg_Int, Birthday` |
| Identifier | `Fide_No` (the federation identifies its players by their _FIDE_ ID) |
| Read | `Name` (written `Last name First name` in Cyrillic, followed by the titles in lower case: `мг` GM, `мм` IM, `мф` FM, national ones after a slash), `Fed` (the regional federation, stored as the club), `Sex` (a `w` for the women), `Birthday`, `Rtg_Nat` (standard), `Rtg_Int` |
| Missing | rapid and blitz ratings, club |
| Unused | the inactivity flag `н` of `Sex`, the national titles (`кмс`, `мс`, `змс`), the general list (`players_list_<yyyy>_<mm>.xls`, all the registered players, most of them unrated) |

## JCF - Japan (`jcf`)

| | |
|---|---|
| Source | the spreadsheet of the monthly "Rating List" post of japanchess.org, found through the site's WordPress API (`wp-json/wp/v2/media`, newest `yyyy-mm-01.xlsx`) |
| Format | Excel (`.xlsx`), a legend sheet then the list |
| Columns | `ID, Name, Kanji, ST-K, ST, ST-G, RP-K, RP, RP-G` |
| Identifier | `ID` |
| Read | `Name` (Latin, written `Last name First name`), `ST` (standard), `RP` (rapid) |
| Missing | birth year, gender, club, _FIDE_ ID, title, blitz rating |
| Unused | `Kanji` (the name in Japanese), the K factors and game counts |

## NZCF - New Zealand (`nzcf`)

| | |
|---|---|
| Source | the "Alphabetical" spreadsheet linked from `https://compete.newzealandchess.co.nz/new-zealand-ratings-list/` (`<yyyy>-<n>-Alphabetical-<yyyymmdd>.xlsx`, quarterly) |
| Format | Excel (`.xlsx`), two header rows |
| Columns | `Code, Name` (last and first name in two columns), `Club, Year`, the `Standard` and `Rapid` blocks (`Rating, T, G, ∑G, Active`), the `FIDE` block (`Code, Fed, Title`) |
| Identifier | `Code` |
| Read | names, `Club` (a code), `Year`, the standard and rapid ratings (`unr` for none), the _FIDE_ code, federation and title |
| Missing | gender, full date of birth, blitz rating |
| Unused | the rating reliability, game counts and last active period of each block, the "Active" spreadsheet |

## DSU - Denmark (`dsu`)

| | |
|---|---|
| Source | `https://turnering.skak.dk/ClubAndMembers/AllMemberReport?memType=ActiveMembersAjax&format=csv` (the report of the active members of the federation's tournament site) |
| Format | CSV, `;`-separated, quoted, cp1252, a blank first line |
| Columns | `Nr;Født;Alder;Navn;Klub;Titel;Rat.;Hur.;Lyn;Fide;Nr;K` |
| Identifier | the first `Nr` (the DSU number) |
| Read | `Navn` (written `First name Last name`: the last word is the last name), `Født` (year of birth), `Klub`, `Titel`, `Rat.` / `Hur.` / `Lyn` (standard, rapid, blitz), `Fide` (the _FIDE_ standard rating, `-` for none), the second `Nr` (_FIDE_ id) |
| Missing | gender, full date of birth |
| Unused | `Alder` (age), `K` |

Every local database accepts a source file installed by hand (the folder button of its row), for the cases where the download is impossible.

## MCF - Malaysia (`mcf`)

| | |
|---|---|
| Source | `https://rating.malaysiachess.my/api/mcfratinglist.ashx` (the Swiss-Manager export of the MCF rating portal) |
| Format | binary Excel (`.xls`) |
| Columns | `ID_No, Name, Sex, FED, Clubnumber, Clubname, birthday, rtg_nat, fide_no, rating_int, Title, K` |
| Identifier | `ID_No` |
| Read | `Name` (a Malay name, kept whole as the last name), `Sex`, `FED`, `Clubname` or `Clubnumber` (the state), `birthday` (year), `Title`, `fide_no`, `rtg_nat` (standard), `rating_int` |
| Missing | rapid and blitz ratings, full date of birth, a first / last name split |
| Unused | `K` |

## Percasi - Indonesia (`percasi`)

| | |
|---|---|
| Source | the Google Sheet of the national rating list (DRN) linked from `https://www.pb-percasi.com/p/blog-page_22.html` (`docs.google.com/spreadsheets/d/<id>/export?format=csv`), published on 1 January and 1 July |
| Format | CSV, two title rows |
| Columns | `ID.,FIDE-ID,PROVINSI,NAMA,L/P,Tgl.Lahir,Gelar,Standar,Cepat,Kilat` |
| Identifier | `ID.` |
| Read | `NAMA` (kept whole as the last name), `PROVINSI` (stored as the club), `L/P` (`P` for the women), `Tgl.Lahir` (`m/d/Y`, mostly empty), `Gelar` when it is a FIDE title, `FIDE-ID`, the three ratings |
| Missing | a first / last name split, the birth date for most players |
| Unused | the national titles of `Gelar` (`MN`, `MP`…) |

## Not converted

- **USA (US Chess)**: the "All Ratings" TSV needs a member login, and the API keys the federation issues since September 2026 are for members too; the converter waits for an answer from the federation (the manual install covers the file meanwhile).

- **Croatia (HŠS)**: the national rating list is published as PDF files only since 2019 (list 146 was the last spreadsheet).
- **Spain (FEDA)**: the national Elo stopped with the December 2023 list; the federation rates on the _FIDE_ list since.
- **Australia (ACF)**: the files exist but their licence forbids importing them into another database.
- **Ireland (ICU)**: the CSV export is for logged-in members only; a manual install like the US Chess one is possible once the format of an export is known.
- **Belgium**, **Switzerland**, **Sweden**, **Norway**, **Serbia**, **Lithuania**, **Latvia**, **Iceland**, **India**, **Singapore**, **Hong Kong**, **Georgia**, **Armenia**, **Uruguay**: no national rating list, the _FIDE_ list applies.
- **Austria**, **Poland**, **Hungary**, **Turkey**, **Israel**, **Portugal**, **Colombia**, **Wales**, **Scotland**, **Slovakia**, **Estonia**, **Iran**, **Philippines**, **China**: a national list exists but is only searchable on the federation's site (or its file could not be found).
- **Greece**, **Bulgaria**, **Mexico**: files attached to news posts or shared drives at irregular addresses.

## Cross-referencing with the _FIDE_ database

When a list gives the _FIDE_ ID of a player (FSI, CFR, CFC, DSB, ECF, LOK, UCF, NZCF), the player fetched from it is completed from the _FIDE_ database when it is installed: _FIDE_ ratings and K factors, titles and federation, as for the _FFE_ database.
