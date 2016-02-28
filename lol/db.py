__doc__ = '''Database-specific logic here. All functions are thread-safe.

'''


import lol.model as model
import lol.config as config


def add_match(match):
    assert type(match) is model.Match, 'expected a Match object.'


def add_summoner(summoner):
    assert type(summoner) is model.Summoner, 'expected a Summoner object.'


def add_summoner_champions(champions):
    assert all(type(x) is model.Champion for x in champions), \
            'expected Champion objects.'
