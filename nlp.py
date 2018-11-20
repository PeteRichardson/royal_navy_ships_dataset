#!/usr/bin/env python

import re
import os
from pprint import pprint
from tableausdk import Collation, Type
from tableausdk.HyperExtract import ExtractAPI, Extract, TableDefinition, Row
from datetime import datetime
import logging


class ShipEvent(object):
	def __init__(self, year, text):
		self.year = year
		self.text = text

	def is_final(self):
		return self.text in ['sunk by the Luftwaffe',
						'burnt and broken up',
						'cancelled',
						'destroyed by fire',
						'broken up',
						'sold',
						'scuttled',
						'foundered',
						'hulked',
						'sold for breaking',
						'wreck sold for breaking']

	def __str__(self):
		return "\t{}: {}".format(self.year, self.text)

class Ship(object):
	def __init__(self, ship_id, text):
		self.id = ship_id
		self.events=[]
		self.notes = []
		self.end_year = 9999
		self.end_reason = ""
		(self.start_year, self.name, self.guns, self.rating,self.other) = text.split(",")
		if self.start_year in ['?','-']:
			self.start_year = 9999
		else:
			self.start_year = int(self.start_year)
		self.events = self.get_events(self.other)
		self.notes = ". ".join(self.notes)
		self.other = None
		self.text = None

	def get_events(self, text):
		events = []
		text = text.replace(";",".")
		clauses = text.split(".")
		for c in clauses:
			clause = c.strip()
			#m = re.match("(.*) ([\d-]+)( \[[0-9\[\]]\])?$",c)
			m = re.match("(.*) ?([\d]{4})(-\d+)? ?\[?.*\]?$",c)
			if m:
				ctext,cyear,_ = m.groups()
				event = ShipEvent(int(cyear), ctext.strip())
				events.append(event)
				if event.is_final():
					self.end_year = event.year
					self.end_reason = event.text
			else:
				if c[0:2]=="ex-":
					ex = c[3:]
				else:				
					self.notes.append(clause)
		return events

	def __str__(self):
		return "[{:4}] {} ({}, {}g)".format(self.id, self.name, self.start_year, self.guns)

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
	return row

if __name__ == '__main__':
	logger = logging.getLogger("NLP")
	logging.basicConfig(level=logging.INFO)

	with open("ships.csv", "rb") as f:
		ExtractAPI.initialize()

		output_filename = "ships.hyper"
		os.unlink(output_filename)

		extract = Extract(output_filename)

		define_schema(extract)
		table = extract.openTable('Extract')
		schema = table.getTableDefinition()

		ship_id = 0
		for line in f.readlines()[1:]:     # [1:] skips the header line in the csv
			ship_id = ship_id + 1
			ship = Ship(ship_id, line)
			row = create_row(schema, ship)
			table.insert(row)

			logger.info(ship)
			logger.debug(ship.notes)
			for e in ship.events:
				logger.debug(e)


		extract.close()

		ExtractAPI.cleanup()