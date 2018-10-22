# -*- coding: utf-8 -*-
""" process the wikipedia wooden ship list to get a ship dataset """

import re

filename = "wikipedia_ship_list.txt"

print "year_launched,name,guns,rating,notes"

with open(filename, "rb") as f:
	for line in f.readlines():
		line = line.replace(",",". ")
		#print line
		rate_regex = r"(.*)\[edit\]"
		r = re.match(rate_regex, line)
		if r:
			rate = r.groups()[0]
			rate = rate.replace(" rates", "")
			rate = rate.replace(" rate", "")
			#print rate
			continue
		ship_regex = '([A-Za-z ]+) (\d+) \((.*)\) – (.*)$'
		s = re.match(ship_regex, line)
		if s:
			ship = s.groups()[0]
			guns = s.groups()[1]
			notes = s.groups()[3]
			year = s.groups()[2]
			if year.startswith("c."):
				notes = "{}. {}".format(year, notes)
				year = year[3:]
			print "{},{},{},{},{}".format(year,ship,guns,rate,notes)