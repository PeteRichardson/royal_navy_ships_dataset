#!/usr/bin/env python

import re
from pprint import pprint

def extract(notes):
	notes = notes.replace(";",".")
	clauses = notes.split(".")
	return clauses


with open("ships.csv", "rb") as f:
	for line in f.readlines():
		ship = {}
		ship['events']=[]
		ship['notes'] = []
		(ship['start_year'], ship['name'], ship['guns'], ship['rating'],ship['misc']) = line.split(",")
		for c in extract(ship['misc']):
			ship['start_year'] = ""
			ship['text'] = c.strip()
			#m = re.match("(.*) ([\d-]+)( \[[0-9\[\]]\])?$",c)
			m = re.match("(.*) ?([\d-]{4})(-\d+)? ?\[?.*\]?$",c)
			if m:
				ship['text'],ship['start_year'],_ = m.groups()
				ship['text'] = ship['text'].strip()
				event = (ship['start_year'], ship['text'])
				ship['events'].append(event)
				if ship['text'] in ['sunk by the Luftwaffe','burnt and broken up','cancelled','destroyed by fire','broken up','sold','scuttled','foundered','hulked',
				'sold for breaking', 'wreck sold for breaking']:
					ship['end_year'] = ship['start_year']
					ship['end_reason'] = ship['text']
			else:
				if c[0:2]=="ex-":
					ex = c[3:]
				else:				
					ship['notes'].append(ship['text'].strip())
					#print("\twas {}".format(c.strip()))
					#print("\t----{}".format(ship['text'].strip()))
		ship.pop('notes','')
		ship.pop('misc','')
		ship.pop('text','')
		#if not ship.get('end_year',None):
		#	print('-'*50)
		pprint(ship)
