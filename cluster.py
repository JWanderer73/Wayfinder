import sklearn
from sklearn.datasets import make_blobs
from sklearn.cluster import KMeans
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

def distance(point1, point2):
    return np.linalg.norm(np.array(point1) - np.array(point2))

#claude generated haversine formula to get relative distance based on coordinates
def haversine_km(point1, point2):
    R = 6371  # Earth radius in km
    lat1, lon1 = np.radians(point1)
    lat2, lon2 = np.radians(point2)
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    return 2 * R * np.arcsin(np.sqrt(a))

#claude-made total cluster travel time approximation
def cluster_travel_time(cluster_points, center, speed_kmh=20):
    """Estimate total travel time through cluster using nearest-neighbor path"""
    coords = cluster_points[:, 0:2]
    unvisited = list(range(len(coords)))
    
    # start from the point closest to the center
    current = min(unvisited, key=lambda i: haversine_km(center, coords[i]))
    unvisited.remove(current)
    
    total_km = haversine_km(center, coords[current])  # hotel → first point
    
    while unvisited:
        # go to nearest unvisited point
        nearest = min(unvisited, key=lambda i: haversine_km(coords[current], coords[i]))
        total_km += haversine_km(coords[current], coords[nearest])
        current = nearest
        unvisited.remove(current)
    
    total_km += haversine_km(coords[current], center)  # last point → hotel
    return (total_km / speed_kmh) * 60  # convert to minutes

#first version
def clustering_alg(locations, days):
    """
    takes in locations, n by _ matrix with x coordinate in first column
    and y coordinate in second column for n locations

    days is number of days
    """
    # Apply K-Means++
    kmeans = KMeans(n_clusters=days, init='k-means++', random_state=42)
    kmeans.fit(locations)

    # Visualize clusters
    plt.scatter(locations[:, 0], locations[:, 1], c=kmeans.labels_, cmap='viridis', alpha=0.7)
    plt.scatter(kmeans.cluster_centers_[:, 0], kmeans.cluster_centers_[:, 1], 
                s=300, c='red', marker='X', label='Centroids')
    plt.title("Customer Segmentation with K-Means++")
    plt.legend()
    plt.show()

#adding start
def clustering_alg_with_hotel(locations, days, start, max_distance):
    """
    takes in locations, n by _ matrix with x coordinate in first column
    and y coordinate in second column for n locations

    days is number of days
    start is hotel coordinates, 1d array of length 2
    max_distance is maximum distance willing to drive per day
    """
    # Apply K-Means++
    kmeans = KMeans(n_clusters=days, init='k-means++', random_state=42)
    kmeans.fit(locations)

    labels_count = np.bincount(kmeans.labels_)
    inertias = np.zeros(days)
    works = np.zeros(days)
    print(kmeans.cluster_centers_)
    for label in range(days):
        cluster_points = locations[kmeans.labels_ == label]
        inertia_i = np.sum(np.linalg.norm(cluster_points - kmeans.cluster_centers_[label], axis=1))
        print(inertia_i)
        if(distance(kmeans.cluster_centers_[label], start) * 2 + inertia_i > max_distance):
            works[label] = False
        else:
            works[label] = True
    print(works)
    curr_working = np.nonzero(works)[0]
    if(len(curr_working) != days):
        for index, val in enumerate(works):
            if(val == 0):
                return

    # Visualize clusters
    plt.scatter(locations[:, 0], locations[:, 1], c=kmeans.labels_, cmap='viridis', alpha=0.7)
    plt.scatter(kmeans.cluster_centers_[:, 0], kmeans.cluster_centers_[:, 1], 
                s=300, c='red', marker='X', label='Centroids')
    plt.title("Customer Segmentation with K-Means++")
    plt.legend()
    plt.show()

#realized miles cap is probably not what we want, using time cap + trying to optimize
def clust_time(locations, days, start, time_cap):
    """
    takes in locations, n by _ matrix with x coordinate in first column
    and y coordinate in second column for n locations

    days is number of days
    start is hotel coordinates, 1d array of length 2
    max_distance is maximum distance willing to drive per day
    """
    best_score = 0
    best_clustering = None
    while(not best_clustering and len(locations >= 3)):
        for i in range(100):
            #score = 0
            # Apply K-Means++
            kmeans = KMeans(n_clusters=days, init='k-means++', random_state=i * 10)
            pure_locs = locations[:, 0:2]
            kmeans.fit(pure_locs)

            labels_count = np.bincount(kmeans.labels_)
            inertias = np.zeros(days)
            works = np.zeros(days)
            for label in range(days):
                #old time approximation
                # cluster_points = locations[kmeans.labels_ == label]
                # dist = np.sum(np.linalg.norm(cluster_points[:, 0:2] - kmeans.cluster_centers_[label], axis=1)) \
                #     + distance(kmeans.cluster_centers_[label], start) * 2
                
                # if(dist / 40 + np.sum(cluster_points[:, 2])> time_cap):
                #     works[label] = False
                # else:
                #     works[label] = True
                cluster_points = locations[kmeans.labels_ == label]
    
                travel_time = cluster_travel_time(cluster_points, kmeans.cluster_centers_[label])
                activity_time = np.sum(cluster_points[:, 2])
                
                if travel_time + activity_time > time_cap:
                    works[label] = False
                else:
                    works[label] = True
                    print(travel_time + activity_time)
            curr_working = np.nonzero(works)[0]
            # score += len(curr_working)
            # if(score > best_score):
            #     best_score = score
            #     best_clustering = kmeans
            if(len(curr_working) == days):
                best_clustering = kmeans
                print(len(locations))
        if(not best_clustering):
            locations = locations[:-1]
    if(best_clustering):
        # Visualize clusters
        plt.scatter(locations[:, 0], locations[:, 1], c=best_clustering.labels_, cmap='viridis', alpha=0.7)
        plt.scatter(best_clustering.cluster_centers_[:, 0], best_clustering.cluster_centers_[:, 1], 
                    s=300, c='red', marker='X', label='Centroids')
        plt.title("Customer Segmentation with K-Means++")
        plt.legend()
        plt.show()

# cities = pd.read_csv("/Users/AbhinavKrishna/WayFinder/Cloned Repo/Wayfinder/uscities.csv")
# cities = cities[["lat", "lng"]]p
# clustering_alg(cities.to_numpy(), 3)

#claude-generated dataset
locations = np.array([
    # Cluster 1 — top-left area (~15-30, 70-85)
    [18, 75], [22, 80], [15, 72], [27, 83], [20, 78],
    [25, 70], [17, 85],

    # Cluster 2 — bottom-center area (~40-60, 15-30)
    [45, 20], [52, 18], [48, 25], [55, 22], [43, 28],
    [50, 15], [57, 27],

    # Cluster 3 — right area (~75-90, 50-65)
    [78, 55], [85, 60], [80, 52], [88, 63], [75, 58],
    [83, 50],
])
#clustering_alg(locations, 3)
#clustering_alg_with_hotel(locations, 3, [50, 50], 100)

#claude-generated dataset
locations2 = np.array([
    # Downtown / City Center (~35-65, 35-65)
    [50, 50], [58, 42], [38, 60], [63, 55], [40, 38],
    [55, 65], [35, 48],

    # Tourist / Waterfront area (~5-35, 60-95)
    [10, 85], [25, 70], [15, 92], [30, 68], [8, 75],
    [28, 88], [18, 63],

    # Suburbs / Outskirts (~65-98, 5-35)
    [70, 28], [90, 12], [75, 8], [95, 30], [68, 18],
    [88, 22],
])
#clustering_alg_with_hotel(locations2, 3, [50, 50], 150)

#even more spread out data from claude, plus manually added 6 minute times
locations3 = np.array([
    # Downtown / City Center (~30-70, 30-70)
    [50, 50, 0.1], [65, 35, 0.2], [32, 62, 0.2], [68, 68, 0.1], [38, 32, 0.1],
    [55, 70, 0.1], [30, 45, 0.1], [70, 42, 0.1],

    # Tourist / Waterfront (~2-30, 55-99)
    [5, 95, 0.1], [28, 60, 0.1], [12, 75, 0.1], [22, 98, 0.1], [8, 62, 0.1],
    [18, 88, 0.1], [2, 70, 0.1],  [25, 55, 0.1],

    # Suburbs / Outskirts (~65-99, 2-38)
    [68, 35, 0.1], [98, 5, 0.1],  [72, 12, 0.1], [99, 38, 0.1], [65, 8, 0.1],
    [88, 28, 0.1], [78, 2, 0.1],  [95, 20, 0.1],
])

if __name__ == "__main__":
    clust_time(locations3, 3, [50, 50], 5)