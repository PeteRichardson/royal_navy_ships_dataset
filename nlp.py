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

class Ship(object):
	def __init__(self, ship_id, text):
		self.id = ship_id
		self.events=[]
		self.notes = []
		self.start_year = 9999
		self.end_year = 9999
		self.end_reason = ""
		logger.debug(text)
		(self.start_year, self.name, self.guns, self.rating,self.misc) = text.split(",")
		for c in extract_clauses(self.misc):
			self.text = c.strip()
			if (self.start_year != '-') and (self.start_year != '?'):
				self.start_year = int(self.start_year)
			#m = re.match("(.*) ([\d-]+)( \[[0-9\[\]]\])?$",c)
			m = re.match("(.*) ?([\d]{4})(-\d+)? ?\[?.*\]?$",c)
			if m:
				self.text,self.start_year,_ = m.groups()
				self.text = self.text.strip()
				self.start_year = int(self.start_year)
				event = (self.start_year, self.text)
				self.events.append(event)
				if self.text in ['sunk by the Luftwaffe',
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
					self.end_year = int(self.start_year)
					self.end_reason = self.text
			else:
				if c[0:2]=="ex-":
					ex = c[3:]
				else:				
					self.notes.append(self.text.strip())
					#print("\twas {}".format(c.strip()))
					#print("\t----{}".format(self.text'].strip()))
		#ship.pop('notes','')
		self.notes = ". ".join(self.notes)
		self.misc = None
		self.text = None
		#if not ship.get('end_year',None):
		#	print('-'*50)
		#pprint(ship)

extract = None

def define_schema(extract):
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
	row.setInteger(0, ship.id)
	row.setCharString(1, ship.name)
	row.setCharString(2, ship.rating)
	row.setInteger(3, int(ship.guns))
	row.setDateTime(4, int(ship.start_year), 1, 1, 12, 0, 0, 0)
	row.setDateTime(5, int(ship.end_year), 1, 1, 12, 0, 0, 0)
	row.setCharString(6, ship.end_reason)
	row.setCharString(7, ship.notes)

	logger.info("Inserting ship {}. {}".format(ship.id, ship.name))
	return row

ExtractAPI.initialize()

output_filename = "ships.hyper"
os.unlink(output_filename)

extract = Extract(output_filename)

define_schema(extract)
table = extract.openTable('Extract')
schema = table.getTableDefinition()

with open("ships.csv", "rb") as f:
	ship_id = 1
	for line in f.readlines()[1:]:     # [1:] skips the header line in the csv
		ship = Ship(ship_id, line)
		row = create_row(schema, ship)
		ship_id = ship_id + 1
		table.insert(row)

	extract.close()

	ExtractAPI.cleanup()