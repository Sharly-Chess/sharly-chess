**[Retour au sommaire de la documentation](../README.md)**

# Papi-web - Annexe technique : URLs utilisées par le serveur web

Cette page décrit les URLs utilisées par Papi-web.

## URLs publiques (affichées dans la barre d'URL)

| URI                                                                                  | Name                                                       | Description |
|--------------------------------------------------------------------------------------|------------------------------------------------------------|-------------|
| ``/``                                                                                | ``index``                                                  |             |
| ``/admin``                                                                           | ``admin``                                                  |             |
| ``/admin/download-event-players/{event_uniq_id:str}``                                | ``admin-download-event-players``                           |             |
| ``/admin/event-print/{event_uniq_id:str}``                                           | ``admin-event-print``                                      |             |
| ``/admin/event/{event_uniq_id:str}``                                                 | ``admin-event``                                            |             |
| ~~``/admin/event/{event_uniq_id:str}/{admin_event_tab:str}``~~                       | ``admin-event-tab``                                        |             |
| ``/admin/event/{event_uniq_id:str}/config``                                          | ``admin-event-tab``                                        |             |
| ``/admin/event/{event_uniq_id:str}/tournaments``                                     | ``admin-event-tab``                                        |             |
| ``/admin/event/{event_uniq_id:str}/players``                                         | ``admin-event-tab``                                        |             |
| ``/admin/event/{event_uniq_id:str}/screens``                                         | ``admin-event-tab``                                        |             |
| ``/admin/event/{event_uniq_id:str}/families``                                        | ``admin-event-tab``                                        |             |
| ``/admin/event/{event_uniq_id:str}/rotators``                                        | ``admin-event-tab``                                        |             |
| ``/admin/event/{event_uniq_id:str}/timers``                                          | ``admin-event-tab``                                        |             |
| ``/admin/tournament-trf-export/{event_uniq_id:str}/{tournament_id:int}/{usage:str}`` | ``admin-tournament-trf-export``                            |             |
| ~~``/admin/{admin_tab:str}``~~                                                       | ``admin-tab``                                              |             |
| ``/admin/config``                                                                    | ``admin-tab``                                              |             |
| ``/admin/current_events``                                                            | ``admin-tab``                                              |             |
| ``/admin/coming_events``                                                             | ``admin-tab``                                              |             |
| ``/admin/passed_events``                                                             | ``admin-tab``                                              |             |
| ``/admin/archives``                                                                  | ``admin-tab``                                              |             |
| ``/user``                                                                            | ``user``                                                   |             |
| ``/user/event/{event_uniq_id:str}``                                                  | ``user-event``                                             |             |
| ``/user/rotator/{event_uniq_id:str}/{rotator_id:int}``                               | ``user-rotator``                                           |             |
| ``/user/screen/{event_uniq_id:str}/{screen_uniq_id:str}``                            | ``user-screen``                                            |             |
| ``/user/{user_tab:str}``                                                             | ``user-tab``                                               |             |

## URLs non affichées

| URI                                                                                                                       | Name                                                       | Description |
|---------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------|-------------|
| ``/admin/config-modal``                                                                                                   | ``admin-config-modal``                                     |             |
| ``/admin/config-update``                                                                                                  | ``admin-config-update``                                    |             |
| ``/admin/default-timers-modal/{event_uniq_id:str}``                                                                       | ``admin-default-timers-modal``                             |             |
| ``/admin/default-timers-update/{event_uniq_id:str}``                                                                      | ``default-timers-update``                                  |             |
| ``/admin/event-clone/{event_uniq_id:str}``                                                                                | ``admin-event-clone``                                      |             |
| ``/admin/event-delete/{event_uniq_id:str}``                                                                               | ``admin-event-delete``                                     |             |
| ``/admin/event-modal/{action:str}/{event_uniq_id:str}``                                                                   | ``admin-event-modal``                                      |             |
| ``/admin/event-update/{event_uniq_id:str}``                                                                               | ``admin-event-update``                                     |             |
| ``/admin/family-clone/{event_uniq_id:str}/{family_id:int}``                                                               | ``admin-family-clone``                                     |             |
| ``/admin/family-create/{event_uniq_id:str}/{family_type:str}``                                                            | ``admin-family-create``                                    |             |
| ``/admin/family-delete/{event_uniq_id:str}/{family_id:int}``                                                              | ``admin-family-delete``                                    |             |
| ``/admin/family-modal/create/{event_uniq_id:str}/{family_type:str}``                                                      | ``admin-family-create-modal``                              |             |
| ``/admin/family-modal/{action:str}/{event_uniq_id:str}/{family_id:int}``                                                  | ``admin-family-modal``                                     |             |
| ``/admin/family-update/{event_uniq_id:str}/{family_id:int}``                                                              | ``admin-family-update``                                    |             |
| ``/admin/player-check-in/{event_uniq_id:str}/{player_id:int}``                                                            | ``admin-player-check-in``                                  |             |
| ``/admin/player-check-out/{event_uniq_id:str}/{player_id:int}``                                                           | ``admin-player-check-out``                                 |             |
| ``/admin/player-create/{event_uniq_id:str}``                                                                              | ``admin-player-create``                                    |             |
| ``/admin/player-delete/{event_uniq_id:str}/{player_id:int}``                                                              | ``admin-player-delete``                                    |             |
| ``/admin/player-modal/create-from-fide/{event_uniq_id:str}/{player_fide_id:int}``                                         | ``admin-player-create-from-fide-modal``                    |             |
| ``/admin/player-modal/create/{event_uniq_id:str}``                                                                        | ``admin-player-create-modal``                              |             |
| ``/admin/player-modal/{action:str}/{event_uniq_id:str}/{player_id:int}``                                                  | ``admin-player-modal``                                     |             |
| ``/admin/player-move/{event_uniq_id:str}/{player_id:int}/{tournament_id:int}``                                            | ``admin-player-move``                                      |             |
| ``/admin/player-print-view/{event_uniq_id:str}/{tournament_id:int}``                                                      | ``admin-player-print-view``                                |             |
| ``/admin/player-record/{event_uniq_id:str}/{player_id:int}``                                                              | ``admin-player-record``                                    |             |
| ``/admin/player-update/{event_uniq_id:str}/{player_id:int}``                                                              | ``admin-player-update``                                    |             |
| ``/admin/print-modal/{event_uniq_id:str}``                                                                                | ``admin-print-modal``                                      |             |
| ``/admin/record-modal/{event_uniq_id:str}/{player_id:int}``                                                               | ``admin-record-modal``                                     |             |
| ``/admin/rotator-create/{event_uniq_id:str}``                                                                             | ``admin-rotator-create``                                   |             |
| ``/admin/rotator-delete/{event_uniq_id:str}/{rotator_id:int}``                                                            | ``admin-rotator-delete``                                   |             |
| ``/admin/rotator-modal/create/{event_uniq_id:str}``                                                                       | ``admin-rotator-create-modal``                             |             |
| ``/admin/rotator-modal/{action:str}/{event_uniq_id:str}/{rotator_id:int}``                                                | ``admin-rotator-modal``                                    |             |
| ``/admin/rotator-update/{event_uniq_id:str}/{rotator_id:int}``                                                            | ``admin-rotator-update``                                   |             |
| ``/admin/screen-clone/{event_uniq_id:str}/{screen_id:int}``                                                               | ``admin-screen-clone``                                     |             |
| ``/admin/screen-create/{event_uniq_id:str}/{screen_type:str}``                                                            | ``admin-screen-create``                                    |             |
| ``/admin/screen-delete/{event_uniq_id:str}/{screen_id:int}``                                                              | ``admin-screen-delete``                                    |             |
| ``/admin/screen-modal/create/{event_uniq_id:str}/{screen_type:str}``                                                      | ``admin-screen-create-modal``                              |             |
| ``/admin/screen-modal/{action:str}/{event_uniq_id:str}/{screen_id:int}``                                                  | ``admin-screen-modal``                                     |             |
| ``/admin/screen-reorder-sets/{event_uniq_id:str}/{screen_id:int}``                                                        | ``admin-screen-reorder-sets``                              |             |
| ``/admin/screen-set-add/{event_uniq_id:str}/{screen_id:int}``                                                             | ``admin-screen-set-add``                                   |             |
| ``/admin/screen-set-clone/{event_uniq_id:str}/{screen_id:int}/{screen_set_id:int}``                                       | ``admin-screen-set-clone``                                 |             |
| ``/admin/screen-set-delete/{event_uniq_id:str}/{screen_id:int}/{screen_set_id:int}``                                      | ``admin-screen-set-delete``                                |             |
| ``/admin/screen-set-update/{event_uniq_id:str}/{screen_id:int}/{screen_set_id:int}``                                      | ``admin-screen-set-update``                                |             |
| ``/admin/screen-sets-modal/{event_uniq_id:str}/{screen_id:int}``                                                          | ``admin-screen-sets-modal``                                |             |
| ``/admin/screen-sets-set-modal/{event_uniq_id:str}/{screen_id:int}/{screen_set_id:int}``                                  | ``admin-screen-sets-set-modal``                            |             |
| ``/admin/screen-update/{event_uniq_id:str}/{screen_id:int}``                                                              | ``admin-screen-update``                                    |             |
| ``/admin/timer-clone/{event_uniq_id:str}/{timer_id:int}``                                                                 | ``admin-timer-clone``                                      |             |
| ``/admin/timer-create/{event_uniq_id:str}``                                                                               | ``admin-timer-create``                                     |             |
| ``/admin/timer-delete/{event_uniq_id:str}/{timer_id:int}``                                                                | ``admin-timer-delete``                                     |             |
| ``/admin/timer-hour-add/{event_uniq_id:str}/{timer_id:int}``                                                              | ``admin-timer-hour-add``                                   |             |
| ``/admin/timer-hour-clone/{event_uniq_id:str}/{timer_id:int}/{timer_hour_id:int}``                                        | ``admin-timer-hour-clone``                                 |             |
| ``/admin/timer-hour-delete/{event_uniq_id:str}/{timer_id:int}/{timer_hour_id:int}``                                       | ``admin-timer-hour-delete``                                |             |
| ``/admin/timer-hour-update/{event_uniq_id:str}/{timer_id:int}/{timer_hour_id:int}``                                       | ``admin-timer-hour-update``                                |             |
| ``/admin/timer-hours-hour-modal/{event_uniq_id:str}/{timer_id:int}/{timer_hour_id:int}``                                  | ``admin-timer-hours-hour-modal``                           |             |
| ``/admin/timer-hours-modal/{event_uniq_id:str}/{timer_id:int}``                                                           | ``admin-timer-hours-modal``                                |             |
| ``/admin/timer-modal/create/{event_uniq_id:str}``                                                                         | ``admin-timer-create-modal``                               |             |
| ``/admin/timer-modal/{action:str}/{event_uniq_id:str}/{timer_id:int}``                                                    | ``admin-timer-modal``                                      |             |
| ``/admin/timer-reorder-hours/{event_uniq_id:str}/{timer_id:int}``                                                         | ``admin-timer-reorder-hours``                              |             |
| ``/admin/timer-update/{event_uniq_id:str}/{timer_id:int}``                                                                | ``admin-timer-update``                                     |             |
| ``/admin/tournament-close-check-in-forfeit-last-rounds/{event_uniq_id:str}/{tournament_id:int}``                          | ``admin-tournament-close-check-in-forfeit-last-rounds``    |             |
| ``/admin/tournament-close-check-in-forfeit-next-round/{event_uniq_id:str}/{tournament_id:int}``                           | ``admin-tournament-close-check-in-forfeit-next-round``     |             |
| ``/admin/tournament-close-check-in-modal/{event_uniq_id:str}/{tournament_id:int}``                                        | ``admin-tournament-close-check-in-modal``                  |             |
| ``/admin/tournament-create/{event_uniq_id:str}``                                                                          | ``admin-tournament-create``                                |             |
| ``/admin/tournament-delete/{event_uniq_id:str}/{tournament_id:int}``                                                      | ``admin-tournament-delete``                                |             |
| ``/admin/tournament-generate-pairings/{event_uniq_id:str}/{tournament_id:int}``                                           | ``admin-tournament-generate-pairings``                     |             |
| ``/admin/tournament-modal/create/{event_uniq_id:str}``                                                                    | ``admin-tournament-create-modal``                          |             |
| ``/admin/tournament-modal/{action:str}/{event_uniq_id:str}/{tournament_id:int}``                                          | ``admin-tournament-modal``                                 |             |
| ``/admin/tournament-open-check-in/{event_uniq_id:str}/{tournament_id:int}``                                               | ``admin-tournament-open-check-in``                         |             |
| ``/admin/tournament-papi-create/{event_uniq_id:str}/{tournament_id:int}``                                                 | ``admin-tournament-papi-create``                           |             |
| ``/admin/tournament-update/{event_uniq_id:str}/{tournament_id:int}``                                                      | ``admin-tournament-update``                                |             |
| ``/admin/{admin_tab:str}/create-event``                                                                                   | ``admin-tab-create-event``                                 |             |
| ``/admin/{admin_tab:str}/event-modal/create``                                                                             | ``admin-tab-event-create-modal``                           |             |
| ``/background``                                                                                                           | ``background``                                             |             |
| ``/empty-modal``                                                                                                          | ``empty-modal``                                            |             |
| ``/favicon.ico``                                                                                                          | ``favicon``                                                |             |
| ``/ffe/create-from-ffe/{event_uniq_id:str}/{player_ffe_id:int}``                                                          | ``ffe-create-from-modal``                                  |             |
| ``/ffe/event/{event_uniq_id:str}/{admin_event_tab:str}``                                                                  | ``ffe-admin-event-tab``                                    |             |
| ``/ffe/search/{event_uniq_id:str}``                                                                                       | ``ffe-search``                                             |             |
| ``/schema/openapi.json``                                                                                                  | ``c86efb050a3f42bcad22ffda38994257_litestar_openapi_json`` |             |
| ``/search/fide/{event_uniq_id:str}``                                                                                      | ``search-fide``                                            |             |
| ``/static/{file_path:path}``                                                                                              | ``static``                                                 |             |
| ``/user/add-illegal-move/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{player_id:int}``                   | ``user-add-illegal-move``                                  |             |
| ``/user/add-result/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{round:int}/{board_id:int}/{result:int}`` | ``user-add-result``                                        |             |
| ``/user/checkin-modal/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{player_id:int}``                      | ``user-checkin-modal``                                     |             |
| ``/user/delete-illegal-move/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{player_id:int}``                | ``user-delete-illegal-move``                               |             |
| ``/user/delete-result/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{round:int}/{board_id:int}``           | ``user-delete-result``                                     |             |
| ``/user/download-tournament/{event_uniq_id:str}/{tournament_id:str}``                                                     | ``user-download-tournament``                               |             |
| ``/user/download-tournaments/{event_uniq_id:str}``                                                                        | ``user-download-tournaments``                              |             |
| ``/user/event/{event_uniq_id:str}/{user_event_tab:str}``                                                                  | ``user-event-tab``                                         |             |
| ``/user/login/{event_uniq_id:str}/{screen_uniq_id:str}``                                                                  | ``user-login``                                             |             |
| ``/user/result-modal/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{board_id:int}``                        | ``user-result-modal``                                      |             |
| ``/user/rotator/{event_uniq_id:str}/{rotator_id:int}/{rotator_screen_index:int}``                                         | ``user-rotator``                                           |             |
| ``/user/toggle-check-in/{event_uniq_id:str}/{screen_uniq_id:str}/{tournament_id:int}/{player_id:int}``                    | ``user-toggle-check-in``                                   |             |
