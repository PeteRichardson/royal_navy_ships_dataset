import asyncio
import aiohttp
import signal
import sys
import json



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

async def get_dbpedia(shipname):
    data = await get_json(search_url.format(shipname))
    j = json.loads(data)['results']
    for s in j:
        print("--- ship: {}    {}".format(s['label'],s['uri']))
        detail_data = await get_json(s['uri'])
        if len(detail_data) > 10:
            detail_json = json.loads(detail_data)[s['uri']]
            if 'http://dbpedia.org/ontology/topSpeed' in detail_json:
                print("found topSpeed")
                print(detail_json['http://dbpedia.org/ontology/topSpeed'][0]['value'])

async def get_all_ships():
    shipnames = ['Victory', 'Prince', 'Royal James']
    for shipname in shipnames:
        await asyncio.ensure_future(get_dbpedia(shipname))
    await client.close()

loop.run_until_complete(get_all_ships())