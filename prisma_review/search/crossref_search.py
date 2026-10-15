"""Crossref search backend using REST API."""

from __future__ import annotations

import re
import time
import requests
from ..models import Paper
from .query_plan import text_search_query
from .filters import SearchFilters, build_crossref_filter, apply_post_filters

# Progress output must go to stderr: this module is imported by the stdio MCP
# server, where stdout is the JSON-RPC channel and any stray byte corrupts it.
import sys
import functools
print = functools.partial(print, file=sys.stderr)

API_URL = "https://api.crossref.org/works"


def _clean_query(query: str) -> str:
	"""Reduce a Boolean query to Crossref's plain-text search string.

	Delegates to the shared helper so the transparency warnings reported by
	``search.query_plan`` match exactly what is sent here.
	"""
	return text_search_query(query)


def search_crossref(query: str, date_start: str, date_end: str,
                    max_results: int = 500, email: str = "",
                    filters: SearchFilters | None = None) -> list[Paper]:
	"""Search Crossref and return normalized Paper objects."""
	search_text = _clean_query(query)
	start_year = int(date_start[:4])
	end_year = int(date_end[:4])

	# Request channel: date is always filtered; append supported facets to the
	# same structured `filter` string (Crossref honours these even though it
	# ignores the Boolean query).
	filter_str = f"from-pub-date:{date_start},until-pub-date:{date_end}"
	if filters:
		extra = build_crossref_filter(filters)
		if extra:
			filter_str += "," + extra

	papers = []
	cursor = "*"
	count = 0

	try:
		while count < max_results and cursor:
			params = {
				"query": search_text,
				"filter": filter_str,
				"rows": min(100, max_results - count),
				"cursor": cursor,
			}
			if email:
				params["mailto"] = email

			resp = requests.get(API_URL, params=params, timeout=10)

			if resp.status_code == 429:
				time.sleep(30)
				continue

			if resp.status_code != 200:
				print(f"  [!] Crossref API error: HTTP {resp.status_code}")
				break

			data = resp.json()
			items = data.get("message", {}).get("items", [])

			if not items:
				break

			for item in items:
				if count >= max_results:
					break

				title_list = item.get("title", [])
				title = title_list[0] if title_list else ""
				if not title:
					continue

				authors = []
				for author in item.get("author", []):
					given = author.get("given", "")
					family = author.get("family", "")
					name = f"{given} {family}".strip()
					if name:
						authors.append(name)

				abstract = item.get("abstract", "")
				if abstract:
					abstract = re.sub(r'<[^>]+>', '', abstract).strip()

				year = 0
				pub_date = item.get("published", {}).get("date-parts")
				if pub_date and isinstance(pub_date, list) and pub_date[0]:
					year = pub_date[0][0] if isinstance(pub_date[0], list) else pub_date[0]

				doi = item.get("DOI", "")
				url = item.get("URL", "")
				if not url and doi:
					url = f"https://doi.org/{doi}"

				venue_list = item.get("container-title", [])
				venue = venue_list[0] if venue_list else ""

				keywords = item.get("subject", [])

				issn_list = item.get("ISSN", [])
				issn = issn_list[0] if issn_list else None

				paper = Paper(
					title=title.strip(),
					authors=authors,
					abstract=abstract,
					year=year,
					doi=doi if doi else None,
					url=url,
					venue=venue,
					keywords=keywords,
					source="crossref",
					source_id=doi if doi else "",
					type=item.get("type"),
					issn=issn,
				)
				papers.append(paper)
				count += 1

			cursor = data.get("message", {}).get("next-cursor")

	except Exception as e:
		print(f"  [!] Crossref search error: {e}")

	# Post-request safety net (e.g. open_access, which Crossref can't filter).
	if filters:
		papers = apply_post_filters(papers, filters, "crossref")

	return papers
