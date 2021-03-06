__doc__ = '''Contains data structures of basic game entities.

'''


import enum

from collections import namedtuple


current_season = 'SEASON2016'
ranked_solo    = 'RANKED_SOLO_5x5'
current_region = 'na'


@enum.unique
class tier(enum.IntEnum):
    bronze     = 1
    silver     = 2
    gold       = 3
    platinum   = 4
    diamond    = 5
    master     = 6
    challenger = 7


def get_tier_id(name):
    '''Given a tier's name, returns its id.'''
    assert name in _map_tier_id, '{} is an invalid tier name'.format(name)
    return _map_tier_id[name]


_map_tier_id = {
    'BRONZE'     : tier.bronze,
    'SILVER'     : tier.silver,
    'GOLD'       : tier.gold,
    'PLATINUM'   : tier.platinum,
    'DIAMOND'    : tier.diamond,
    'MASTER'     : tier.master,
    'CHALLENGER' : tier.challenger,
}


match_champion = namedtuple('MatchChampion', ['match_id', 'champion_id'])


class Match(object):
    '''Represents a match.'''

    def __init__(self, match_id, duration=0, creation_time=0,
            players_stats=[], winning_team_stats=None, losing_team_stats=None):
        self.match_id = match_id
        self.duration = duration
        self.creation_time = creation_time
        self.players_stats = players_stats
        self.winning_team_stats = winning_team_stats
        self.losing_team_stats = losing_team_stats


class Stats(object):
    '''Represents an entity's perspective of a match.'''

    def __init__(self, kills=0, deaths=0, assists=0, damage_dealt=0,
            damage_taken=0, cs=0, gold=0, won=False):
        self.kills = kills
        self.deaths = deaths
        self.assists = assists
        self.damage_dealt = damage_dealt
        self.damage_taken = damage_taken
        self.cs = cs
        self.gold = gold
        self.won = won


class PlayerStats(Stats):
    '''Represents a summoner's perspective of a match.'''

    def __init__(self, summoner_id, champion_id=0, **kwargs):
        super().__init__(**kwargs)
        self.summoner_id = summoner_id
        self.champion_id = champion_id


class TeamStats(Stats):
    '''Represents a team's perspective of a match.'''

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class Summoner(object):
    '''Represents a summoner.'''

    def __init__(self, summoner_id, tier_id=0):
        self.summoner_id = summoner_id
        self.tier_id = tier_id


class Champion(object):
    '''Represents a summoner's champion.'''

    def __init__(self, summoner_id, champion_id, games_played):
        self.summoner_id = summoner_id
        self.champion_id = champion_id
        self.games_played = games_played
