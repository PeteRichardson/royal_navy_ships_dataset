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
		(ship['year'], ship['name'], ship['guns'], ship['rating'],ship['misc']) = line.split(",")
		for c in extract(ship['misc']):
			ship['year'] = ""
			ship['text'] = c.strip()
			#m = re.match("(.*) ([\d-]+)( \[[0-9\[\]]\])?$",c)
			m = re.match("(.*) ?([\d-]{4})(-\d+)? ?\[?.*\]?$",c)
			if m:
				ship['text'],ship['year'],_ = m.groups()
				event = (ship['year'], ship['text'].strip())
				#ship['events'].append("{}: {}".format(ship['year'], ship['text'].strip()))
				ship['events'].append(event)
			else:
				if c[0:2]=="ex-":
					ex = c[3:]
				else:				
					ship['notes'].append(ship['text'].strip())
					#print("\twas {}".format(c.strip()))
					#print("\t----{}".format(ship['text'].strip()))
		pprint(ship)
