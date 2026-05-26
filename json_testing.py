from cluster import clust_time
import json
import numpy as np

with open("/Users/AbhinavKrishna/WayFinder/Cloned Repo/Wayfinder/5865ca1e85c2.json") as f:
    data = json.load(f)

attractions = data["attractions"]

locations = np.array([
    [a["latitude"], a["longitude"], a["duration_minutes"], a["score"]]
    for a in attractions
])

locations = locations[locations[:, 3].argsort()[::-1]]

paris_locations = np.array([
    # Central Paris (~48.85-48.87, 2.33-2.36)
    [48.8584, 2.2945, 90,  9.5],  # Eiffel Tower
    [48.8606, 2.3376, 120, 9.2],  # Louvre
    [48.8600, 2.3266, 75,  8.8],  # Musée d'Orsay
    [48.8738, 2.3323, 60,  8.5],  # Sacré-Cœur
    [48.8530, 2.3499, 60,  8.3],  # Notre-Dame
    [48.8656, 2.3212, 45,  7.9],  # Place de la Concorde
    [48.8698, 2.3078, 90,  8.1],  # Arc de Triomphe
    [48.8772, 2.3430, 60,  7.5],  # Moulin Rouge
    [48.8462, 2.3372, 75,  7.2],  # Panthéon
    [48.8535, 2.3708, 90,  8.7],  # Le Marais

    # East Paris (~48.84-48.86, 2.37-2.41)
    [48.8533, 2.3692, 60,  7.8],  # Place des Vosges
    [48.8579, 2.3491, 75,  8.0],  # Centre Pompidou
    [48.8492, 2.3895, 45,  6.5],  # Père Lachaise Cemetery
    [48.8409, 2.3866, 60,  6.8],  # Bois de Vincennes
    [48.8448, 2.3723, 75,  7.1],  # Promenade Plantée
    [48.8525, 2.3800, 60,  7.3],  # Place de la Bastille
    [48.8366, 2.3817, 90,  6.9],  # Marché d'Aligre
    [48.8601, 2.3835, 45,  6.4],  # Canal Saint-Martin

    # West Paris (~48.85-48.87, 2.26-2.30)
    [48.8656, 2.2769, 120, 8.4],  # Bois de Boulogne
    [48.8737, 2.2950, 75,  7.6],  # Palais de Chaillot
    [48.8628, 2.3020, 60,  7.0],  # Palais de Tokyo
    [48.8796, 2.2836, 45,  6.3],  # Fondation Louis Vuitton
    [48.8588, 2.2770, 90,  7.4],  # Musée Marmottan Monet
    [48.8470, 2.2951, 60,  6.7],  # Parc André Citroën

    # South Paris (~48.82-48.84, 2.30-2.36)
    [48.8338, 2.3325, 75,  6.6],  # Paris Catacombs
    [48.8462, 2.3059, 60,  7.7],  # Luxembourg Gardens
    [48.8390, 2.3461, 45,  6.2],  # Montparnasse Tower
    [48.8310, 2.3230, 90,  6.0],  # Parc Montsouris
    [48.8283, 2.3588, 60,  5.8],  # Butte-aux-Cailles
    [48.8425, 2.3215, 75,  7.3],  # Musée de Cluny

    # North Paris (~48.88-48.90, 2.33-2.37)
    [48.8841, 2.3430, 60,  7.0],  # Montmartre vineyard
    [48.8929, 2.3444, 45,  6.1],  # Marché Saint-Pierre
    [48.8853, 2.3620, 75,  6.8],  # Parc de la Villette
    [48.8960, 2.3877, 90,  7.2],  # Cité des Sciences
    [48.8795, 2.3567, 60,  6.5],  # Canal de l'Ourcq
])

# Starting point (e.g. your hotel or city center)
start = np.array([48.8566, 2.3522])  # Paris city center

clust_time(paris_locations, 4, start, 480)  # 480 min = 8hr day