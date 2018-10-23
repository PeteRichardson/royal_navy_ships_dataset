#!/usr/bin/env python

import re

def extract(notes):
	notes = notes.replace(";",".")
	clauses = notes.split(".")
	return clauses

with open("ships.csv", "rb") as f:
	for line in f.readlines():
		(year, name, guns, rating, notes) = line.split(",")
		print("{}\n{}".format("-"*40, name))
		for c in extract(notes):
			c_year = ""
			c_text = c
			m = re.match("(.*) ([\d-]+)( \[[0-9\[\]]\])?$",c)
			if m:
				c_text,c_year,c_citations = m.groups()
				print("\t{}: {}".format(c_year, c_text.strip()))
			else:
				print("\t{}".format(c_text.strip()))
