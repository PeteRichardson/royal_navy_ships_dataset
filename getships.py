import asyncio
import aiohttp
import signal
import sys
import json
from pprint import pprint
from csv import DictReader
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)



loop = asyncio.get_event_loop()
client = aiohttp.ClientSession(loop=loop)
headers = {'Accept': 'application/json'}
search_url = "http://lookup.dbpedia.org/api/search/KeywordSearch?QueryClass=ship&QueryString=HMS%20{}"

async def get_json(url):
    async with client.get(url, headers=headers) as resp:
        if resp.status == 200:
            return await resp.read()
        else:
            return ""


def extract_details(detail_json):
    details = {}
    dbos = ['class', 'homeport', 'layingDown', 'length', 'orderDate', 'shipBeam',
              'shipLaunch', 'status', 'topSpeed', 'shipCommissioned', 'shipComplement',
               'shipTonsBurthen']

    dbps = ['shipArmament','shipDisplacement', 'shipPropulsion', 'shipArmour', 'shipNamesake', 'shipAcquired',
                  'shipHonours', 'shipBuilder', 'shipCountry', 'shipCompleted', 'shipLaidDown', 'shipComplement']

    for f in dbos:
        if 'http://dbpedia.org/ontology/{}'.format(f) in detail_json:
            details[f] = detail_json['http://dbpedia.org/ontology/{}'.format(f)][0]['value']
    for f in dbps:
        if 'http://dbpedia.org/property/{}'.format(f) in detail_json:
            details[f] = detail_json['http://dbpedia.org/property/{}'.format(f)][0]['value']
    return details

async def get_dbpedia(shipname):
    data = await get_json(search_url.format(shipname))
    j = json.loads(data)['results']
    for s in j:
        detail_data = await get_json(s['uri'])
        if len(detail_data) > 10:
            print("--- ship: {}    {}".format(s['label'],s['uri']))
            detail_json = json.loads(detail_data)[s['uri']]
            details = extract_details(detail_json)
            pprint(details)

async def get_all_ships():
    fieldnames = ['year_launched','name','guns','rating','notes']
    ships = {}
    with open("ships.csv","r") as f:
        ships = { row['name']:row for row in DictReader(f) }

    for shipname in sorted(ships.keys()):
        logger.debug("dbpedia: {}".format(shipname))
        await asyncio.ensure_future(get_dbpedia(shipname))
    await client.close()

loop.run_until_complete(get_all_ships())