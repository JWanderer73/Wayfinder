from wayfinder.tripadvisor import fetch_tripadvisor_data
from wayfinder.ranking import score_places_ml


# match preference to tags
def match(pref, tags):
    return any(pref in t or t in pref for t in tags)


# filter places
def filter_places(data, preferences):
    if not preferences:
        return data

    filtered = [
        p for p in data
        if any(match(pref.lower(), [t.lower() for t in p.get("tags", [])]) for pref in preferences)
    ]

    if not filtered:
        return data

    return filtered


# convert to stops
def convert_to_stops(places):
    stops = []

    for p in places:
        tags = p.get("tags", [])

        stops.append({
            "name": p.get("name"),
            "address": p.get("address", ""),
            "visit_minutes": 90,
            "required": False,
            "category": tags[0] if tags else "general"
        })

    return stops


# main pipeline
def generate_recommendations(city, preferences, k=5):
    data = fetch_tripadvisor_data(city)

    if not data:
        print("No data returned from API")
        return []

    filtered = filter_places(data, preferences)
    ranked = score_places_ml(filtered, preferences)

    top_k = ranked[:k]

    return convert_to_stops(top_k)