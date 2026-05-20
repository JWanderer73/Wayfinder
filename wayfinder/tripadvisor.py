import os
import requests
import time

BASE_URL = "https://api.content.tripadvisor.com/api/v1/location"


# load api key
def get_api_key():
    key = os.getenv("TRIPADVISOR_API_KEY")
    if not key:
        raise ValueError("Missing TRIPADVISOR_API_KEY")
    return key


# search locations
def search_locations(query, category="attractions", limit=10):
    url = f"{BASE_URL}/search"

    params = {
        "key": get_api_key(),
        "searchQuery": query,
        "category": category,
        "language": "en"
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    data = response.json().get("data", [])
    return data[:limit]


# get location details
def get_location_details(location_id):
    url = f"{BASE_URL}/{location_id}/details"

    params = {
        "key": get_api_key(),
        "language": "en",
        "currency": "USD"
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    return response.json()


# extract tags for ml
def extract_tags(details):
    tags = set()

    if details.get("category"):
        tags.add(details["category"].get("name", "").lower())

    for sub in details.get("subcategory", []):
        tags.add(sub.get("name", "").lower())

    for group in details.get("groups", []):
        for cat in group.get("categories", []):
            tags.add(cat.get("name", "").lower())

    return list(filter(None, tags))


# normalize data
def normalize_place(details):
    return {
        "name": details.get("name"),
        "location_id": details.get("location_id"),
        "rating": details.get("rating", 0),
        "num_reviews": int(details.get("num_reviews", 0) or 0),
        "address": details.get("address_obj", {}).get("address_string"),
        "tags": extract_tags(details)
    }


# main fetch function
def fetch_tripadvisor_data(city, limit=10):
    results = []

    search_results = search_locations(city, limit=limit)

    for place in search_results:
        location_id = place.get("location_id")

        if not location_id:
            continue

        try:
            details = get_location_details(location_id)
            normalized = normalize_place(details)
            results.append(normalized)

            time.sleep(0.2)

        except Exception as e:
            print(f"Skipping {location_id}: {e}")
            continue

    return results