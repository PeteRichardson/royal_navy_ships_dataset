#!/usr/bin/env python

from csv import DictReader
import requests
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Ship(object):
    def __init__(self, name):
        self.name = name
        logger.debug("Initializing ship {}".format(self.name))

        self.data_from_dbpedia()


    def data_from_ships_csv(self):
        pass


class ShipList(object):
    def __init__(self, name):
        self.name = name
        self.ships = {}

        # Get info from lookup.dbpedia.org
        url_str = "http://lookup.dbpedia.org/api/search/KeywordSearch?QueryClass=ship&QueryString=HMS%20{}"
        url = url_str.format(self.name)
        r = requests.get(url, headers={'Accept':'application/json'})
        self.results = r.json()['results']
        self.count = len(self.results)


if __name__=="__main__":
    fieldnames = ['year_launched','name','guns','rating','notes']
    ships = {}
    with open("ships.csv","rb") as f:
        ships = { row['name']:row for row in DictReader(f) }

    for shipname in sorted(ships.keys()):
        logger.debug("dbpedia: {}".format(shipname))
        shiplist = ShipList(shipname)
        logger.debug("dbpedia: found {:3} ships named {}".format(shiplist.count, shipname))
        for ship in shiplist.results:
            logger.debug("       : {} - {}".format(ship['label'],ship['uri']))




