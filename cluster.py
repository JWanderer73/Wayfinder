import sklearn
from sklearn.datasets import make_blobs
from sklearn.cluster import KMeans
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

def distance(point1, point2):
    return np.linalg.norm(np.array(point1) - np.array(point2))

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

# cities = pd.read_csv("/Users/AbhinavKrishna/WayFinder/Cloned Repo/Wayfinder/uscities.csv")
# cities = cities[["lat", "lng"]]
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
clustering_alg_with_hotel(locations2, 3, [50, 50], 150)