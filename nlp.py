#!/usr/bin/env python

import re
import os
from pprint import pprint
from tableausdk import Collation, Type
from tableausdk.HyperExtract import ExtractAPI, Extract, TableDefinition, Row
from datetime import datetime
import logging

APP_NAME = "NLP"

logger = logging.getLogger("NLP")
logging.basicConfig(level=logging.INFO)

extract = None

def define_schema():
	# Define Table Schema (If we are creating a new extract)
	# (NOTE: In Tableau Data Engine, all tables must be named 'Extract')
	logger.debug("Defining Schema")

	if not extract.hasTable('Extract'):
		schema = TableDefinition()
		schema.setDefaultCollation(Collation.EN_US)
		schema.addColumn('ID', Type.INTEGER)
		schema.addColumn('Name', Type.CHAR_STRING)
		schema.addColumn('Rating', Type.CHAR_STRING)
		schema.addColumn('Guns', Type.INTEGER)
		schema.addColumn('Start Year', Type.DATETIME)
		schema.addColumn('End Year', Type.DATETIME)
		schema.addColumn('End Reason', Type.CHAR_STRING)
		schema.addColumn('Notes', Type.CHAR_STRING)
		extract.addTable('Extract', schema)

def extract_clauses(notes):
	notes = notes.replace(";",".")
	clauses = notes.split(".")
	return clauses


def create_row(schema, ship):
	row = Row(schema)
	t = datetime.now().timetuple()
	row.setInteger(0, ship['id'])
	row.setCharString(1, ship['name'])
	row.setCharString(2, ship['rating'])
	row.setInteger(3, int(ship['guns']))
	row.setDateTime(4, int(ship.get('start_year',9999)), 1, 1, 12, 0, 0, 0)
	row.setDateTime(5, int(ship.get('end_year',9999)), 1, 1, 12, 0, 0, 0)
	row.setCharString(6, ship.get('end_reason',""))
	row.setCharString(7, ship.get('notes',""))

	logger.info("Inserting ship {}. {}".format(ship['id'], ship['name']))
	return row

ExtractAPI.initialize()

output_filename = "ships.hyper"

os.unlink(output_filename)

extract = Extract(output_filename)

define_schema()
table = extract.openTable('Extract')
schema = table.getTableDefinition()

with open("ships.csv", "rb") as f:
	ship_id = 1
	for line in f.readlines()[1:]:     # [1:] skips the header line in the csv
		ship = {}
		ship['id'] = ship_id
		ship['events']=[]
		ship['notes'] = []
		logger.debug(line)
		(ship['start_year'], ship['name'], ship['guns'], ship['rating'],ship['misc']) = line.split(",")
		for c in extract_clauses(ship['misc']):
			ship['text'] = c.strip()
			if (ship['start_year'] != '-') and (ship['start_year'] != '?'):
				ship['start_year'] = int(ship['start_year'])
			#m = re.match("(.*) ([\d-]+)( \[[0-9\[\]]\])?$",c)
			m = re.match("(.*) ?([\d]{4})(-\d+)? ?\[?.*\]?$",c)
			if m:
				ship['text'],ship['start_year'],_ = m.groups()
				ship['text'] = ship['text'].strip()
				ship['start_year'] = int(ship['start_year'])
				event = (ship['start_year'], ship['text'])
				ship['events'].append(event)
				if ship['text'] in ['sunk by the Luftwaffe',
									'burnt and broken up',
									'cancelled',
									'destroyed by fire',
									'broken up',
									'sold',
									'scuttled',
									'foundered',
									'hulked',
									'sold for breaking',
									'wreck sold for breaking']:
					ship['end_year'] = int(ship['start_year'])
					ship['end_reason'] = ship['text']
			else:
				if c[0:2]=="ex-":
					ex = c[3:]
				else:				
					ship['notes'].append(ship['text'].strip())
					#print("\twas {}".format(c.strip()))
					#print("\t----{}".format(ship['text'].strip()))
		#ship.pop('notes','')
		ship['notes'] = ". ".join(ship['notes'])
		ship.pop('misc','')
		ship.pop('text','')
		#if not ship.get('end_year',None):
		#	print('-'*50)
		#pprint(ship)
		row = create_row(schema, ship)
		ship_id = ship_id + 1
		table.insert(row)

	extract.close()

	ExtractAPI.cleanup()