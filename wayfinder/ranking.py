from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# build text features
def build_feature_strings(data):
    docs = []
    for place in data:
        tags = " ".join(place.get("tags", []))
        rating = round(place.get("rating", 0))
        reviews = place.get("num_reviews", 0)
        text = f"{tags} rating_{rating} reviews_{reviews}"
        docs.append(text)
    return docs


# rank places with ml
def score_places_ml(data, preferences):
    if not data:
        return []

    if not preferences:
        return data

    docs = build_feature_strings(data)

    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform(docs)

    user_query = " ".join(preferences)
    user_vec = vectorizer.transform([user_query])

    scores = cosine_similarity(user_vec, X)[0]

    scored = list(zip(data, scores))
    scored.sort(key=lambda x: x[1], reverse=True)

    return [p[0] for p in scored]