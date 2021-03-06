import logging
from collections import OrderedDict


class data(object):
    def __init__(self, pigskin_obj):
        self._pigskin = pigskin_obj
        self._store = self._pigskin._store
        self.logger = logging.getLogger(__name__)


    def get_current_season_and_week(self):
        """Get the current season (year), season type, and week.

        Returns
        -------
        dict
            with the ``season``, ``season_type``, and ``week`` fields populated
            if successful. None if otherwise.
        """
        url = self._store.gp_config['modules']['ROUTES_DATA_PROVIDERS']['games']
        current = None

        try:
            r = self._store.s.get(url)
            #self._log_request(r)
            data = r.json()
        except ValueError:
            self.logger.error('current_season_and_week: server response is invalid')
            return None

        try:
            current = {
                'season': data['modules']['meta']['currentContext']['currentSeason'],
                'season_type': data['modules']['meta']['currentContext']['currentSeasonType'],
                'week': str(data['modules']['meta']['currentContext']['currentWeek'])
            }
        except KeyError:
            self.logger.error('could not determine the current season and week')
            return None

        return current


    def get_seasons(self):
        """Get a list of available seasons.

        Returns
        -------
        list
            a list of available seasons, sorted from the most to least recent;
            None if there was a failure.
        """
        url = self._store.gp_config['modules']['ROUTES_DATA_PROVIDERS']['games']
        seasons_list = None

        try:
            r = self._store.s.get(url)
            #self._log_request(r)
            data = r.json()
        except ValueError:
            self.logger.error('_get_seasons: invalid server response')
            return None

        try:
            self.logger.debug('parsing seasons')
            giga_list = data['modules']['mainMenu']['seasonStructureList']
            seasons_list = [str(x['season']) for x in giga_list if x.get('season') != None]
        except KeyError:
            self.logger.error('unable to parse the seasons data')
            return None

        return seasons_list


    def get_team_games(self, season, team):
        """Get the raw game data for a given season (year) and team.

        Parameters
        ----------
        season : str or int
            The season can be provided as either a ``str`` or ``int``.
        team : str
            Accepts the team ``seo_name``.

        Returns
        -------
        list
            of dicts with the metadata for each game

        Note
        ----
        TODO: currently only the current season is supported
        TODO: this data really should be normalized
        """
        url = self._store.gp_config['modules']['ROUTES_DATA_PROVIDERS']['team_detail']
        url = url.replace(':team', team)
        games = None

        try:
            r = self._store.s.get(url)
            self._log_request(r)
            data = r.json()
        except ValueError:
            self.logger.error('get_team_games: server response is invalid')
            return None

        try:
            # currently, only data for the current season is available
            games = [x for x in data['modules']['gamesCurrentSeason']['content']]
            games = sorted(games, key=lambda x: x['gameDateTimeUtc'])
        except KeyError:
            self.logger.error('could not parse/build the team_games list')
            return None

        return games


    def get_teams(self, season):
        """Get a list of teams for a given season.

        Parameters
        ----------
        season : str or int
            The season can be provided as either a ``str`` or ``int``.

        Returns
        -------
        OrderedDict
            With the key as the team name (e.g. Vikings) and value as a dict
            of the teams's metadata.

            Teams are sorted alphabetically.

        Notes
        -----
        TODO: describe metadata structure
        """
        # ['modules']['API']['TEAMS'] only provides the teams for the current
        # season. So, we ask for all the games of a non-bye-week of the regular
        # season to assemble a list of teams.
        no_bye_weeks = [1, 2, 3, 13, 14, 15, 16, 17]
        teams = OrderedDict()

        # loop over non-bye weeks until we find one with 16 games
        # The 1st week should always have 16 games, but week 1 of 2017 had only 15.
        for week in no_bye_weeks:
            games_list = self._fetch_games_list(str(season), 'reg', str(week))

            if len(games_list) == 16:
                break

        if len(games_list) != 16:
            return None

        try:
            teams_list = []
            for game in games_list:
                # Cities which have multiple teams include the team name with
                # the city name. We remove that.
                teams_list.append({
                    'abbr': game['homeTeamAbbr'],
                    'city': game['homeCityState'].replace(' ' + game['homeNickName'], ''),
                    'name': game['homeNickName'],
                })

                teams_list.append({
                    'abbr': game['visitorTeamAbbr'],
                    'city': game['visitorCityState'].replace(' ' + game['visitorNickName'], ''),
                    'name': game['visitorNickName'],
                })
        except KeyError:
            self.logger.error('get_teams: could not build the teams list')
            return None

        teams_list = sorted(teams_list, key=lambda x: x['name'])
        teams = OrderedDict((t['name'], t) for t in teams_list)

        return teams


    def get_week_games(self, season, season_type, week):
        """Get the games list and metadata for a given week.

        Parameters
        ----------
        season : str or int
            The season can be provided as either a ``str`` or ``int``.
        season_type : str
            The season_type can be either ``pre``, ``reg``, or ``post``.
        week : str or int
            The week can be provided as either a ``str`` or ``int``.

        Returns
        -------
        OrderedDict
            With the key as the game name (e.g. Packers@Bears) and value a dict
            of the game's metadata.

            Games are sorted according to their broadcast time and date.

        Notes
        -----
        TODO: describe metadata structure
        TODO: 'home' should return the name of the team, so it can be easily
              attached to a team object elsewhere

        See Also
        --------
        ``_fetch_games_list()``
        """
        games = OrderedDict()
        games_list = self._fetch_games_list(str(season), season_type, str(week))

        if not games_list:
            return None

        try:
            games_list = sorted(games_list, key=lambda x: x['gameDateTimeUtc'])
            for game in games_list:
                key = '{0}@{1}'.format(game['visitorNickName'],  game['homeNickName'])
                games[key] = {
                    'city': game['siteCity'],
                    'stadium': game['siteFullName'],
                    'start_time': game['gameDateTimeUtc'],
                    'phase': game['phase'],
                    'home': {
                        'name': game['homeNickName'],
                        'city': game['homeCityState'],
                        'points': game['homeScore']['pointTotal'],
                    },
                    'away': {
                        'name': game['visitorNickName'],
                        'city': game['visitorCityState'],
                        'points': game['visitorScore']['pointTotal'],
                    },
                    'versions' : {},
                }
                # TODO: perhaps it would be nice for the version to be stored in
                # an OrderedDict. full, then condensed, then coaches. What I
                # assume to be in order of what users are most likely to want.
                version_types = {'condensed': 'condensedVideo' , 'coach': 'condensedVideo', 'full': 'video'}
                for v in version_types:
                    try:
                        games[key]['versions'][v] = game[version_types[v]]['videoId']
                    except KeyError:
                        pass
        except KeyError:
            self.logger.error('get_week_games: could not parse/build the games list')
            return None

        self.logger.debug('``games`` ready')
        return games


    def get_weeks(self, season):
        """Get the weeks of a given season.

        Returns
        -------
        OrderedDict
            with the ``pre``, ``reg``, and ``post`` fields populated with
            OrderedDicts containing the week's number (key) and the week's
            description (value) if it's a special week (Hall of Fame, Super
            Bowl, etc). None if there was a failure.
        """
        url = self._store.gp_config['modules']['ROUTES_DATA_PROVIDERS']['games']
        season = int(season)
        weeks = OrderedDict()

        try:
            r = self._store.s.get(url)
            #self._log_request(r)
            data = r.json()
        except ValueError:
            self.logger.error('_get_weeks: invalid server response')
            return None

        try:
            self.logger.debug('parsing weeks')
            giga_list = data['modules']['mainMenu']['seasonStructureList']
            season_data = [x['seasonTypes'] for x in giga_list if x.get('season') == season][0]

            for st in ['pre', 'reg', 'post']:
                # TODO: This is one long line. Either reformat it, or split the
                # check into a filter or function.
                weeks[st] = OrderedDict((str(w['number']), self._week_description(w['weekNameAbbr'])) for t in season_data if t.get('seasonType') == st for w in t['weeks'])
        except KeyError:
            self.logger.error('unable to parse the weeks data')
            return None

        return weeks


    def _fetch_games_list(self, season, season_type, week):
        """Get a list of games for a given week.

        Parameters
        ----------
        season : str or int
            The season can be provided as either a ``str`` or ``int``.
        season_type : str
            The season_type can be either ``pre``, ``reg``, or ``post``.
        week : str or int
            The week can be provided as either a ``str`` or ``int``.

        Returns
        -------
        list
            With a dict of metadata as the value. An empty list if there was a
            failure.
        """
        url = self._store.gp_config['modules']['ROUTES_DATA_PROVIDERS']['games_detail']
        url = url.replace(':seasonType', season_type).replace(':season', str(season)).replace(':week', str(week))
        games_list = []

        try:
            r = self._store.s.get(url)
            #self._log_request(r)
            data = r.json()
        except ValueError:
            self.logger.error('_fetch_games_list: invalid server response')
            return []

        try:
            games_list = [g for x in data['modules'] if data['modules'][x].get('content') for g in data['modules'][x]['content']]
        except KeyError:
            self.logger.error('_fetch_games_list: could not parse/build the games list')
            return []

        return games_list


    def _week_description(self, abbr):
        descriptions = {
            'hof': 'Hall of Fame',
            'wc': 'Wild Card',
            'div': 'Divisional',
            'conf': 'Conference',
            'pro': 'Pro Bowl',
            'sb': 'Super Bowl',
        }

        try:
            return descriptions[abbr]
        except KeyError:
            return ''
