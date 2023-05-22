import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from scipy.stats import skew
import math as m
from coordinates import *
from visualization import *
from utils import *
from rdkit import Chem
from similarity_3d import calculate_partial_score

from scipy.spatial import KDTree


#### New KDTREE fingerprint implementation ####

def molecule_info(molecule):

    elements, masses, protons, neutrons, electrons, coordinates = get_atoms_info(molecule)
    info = {'elements': elements,
            'masses': masses,
            'protons': protons, 
            'neutrons': neutrons, 
            'electrons': electrons, 
            'coordinates': coordinates}
    return info

def compute_matching(points1, points2):
    """Compute the matching between two sets of points"""
    # Build the KDTree
    tree = KDTree(points2)
    # Query the tree
    distances, indices = tree.query(points1)
    return distances, indices

# SIMILARITIES
def size_similarity(N_query, N_target):
    """Compute the size similarity between two sets of points"""
    similarity_s = min(N_query, N_target) / max(N_query, N_target)
    return similarity_s

def positional_similarity(differences):
    """Compute the positional similarity between two sets of points"""
    # Compute the mean of the distances
    mean = np.mean(differences)
    similarity_r = 1 / (1 + mean)
    return similarity_r

def formula_isotopic_charge_similarity(molecule1: dict, molecule2: dict):
    """Compute the formula similarity between two sets of points"""
    delta_protons= []
    delta_neutrons = []
    delta_electrons = []
    p_change = 0
    n_change = 0
    e_change = 0
    for i in range(0, len(molecule1['elements'])):
        p_diff = abs(molecule1['protons'][i] - molecule2['protons'][i])
        if p_diff == 0:
            n_diff = abs(molecule1['neutrons'][i] - molecule2['neutrons'][i])
            e_diff = abs(molecule1['electrons'][i] - molecule2['electrons'][i])
        else:
            p_change += 1
            current_mass = molecule1['masses'][i] + molecule2['masses'][i]
            standard_mass = Chem.GetMass(molecule1['elements'][i]) + Chem.GetMass(molecule2['elements'][i])
            n_diff = round(current_mass - standard_mass)
            current_electrons = molecule1['electrons'][i] + molecule2['electrons'][i]
            electrons = Chem.GetAtomicNum(molecule1['elements'][i]) + Chem.GetAtomicNum(molecule2['elements'][i])
            e_diff = abs(electrons - current_electrons)

        if n_diff != 0:
                n_change += 1
        if e_diff != 0:
                e_change += 1     
        delta_protons.append(p_diff)
        delta_neutrons.append(n_diff)
        delta_electrons.append(e_diff)

    l = len(molecule1['elements'])
    similarity_f =1/(1 + sum(p_diff)/l + (p_change/l))
    similarity_n =1/(1 + sum(n_diff)/l + (n_change/l))
    similarity_e =1/(1 + sum(e_diff)/l + (e_change/l))
    return similarity_f, similarity_n, similarity_e

def reduced_formula_isotopic_charge_similarity(molecule1: dict, molecule2: dict):
    """Compute the reduced formula similarity between two sets of points"""
    # Mass of the moleules
    mass1 = sum(molecule1['masses'])
    mass2 = sum(molecule2['masses'])
    similarity_f = min(mass1, mass2) / max(mass1, mass2)
    # TODO:Check if there are isotopes in the molecules
    isotopes1 = []
    isotopes2 = []
    for i, neutrons in enumerate(molecule1['neutrons']):
        std_neutrons = Chem.GetMassDifference(molecule1['elements'][i])
        diff_n = abs(neutrons - std_neutrons)
        isotopes1.append(diff_n)
    for j, neutrons in enumerate(molecule2['neutrons']):
        std_neutrons = Chem.GetMassDifference(molecule2['elements'][j])
        diff_n = abs(neutrons - std_neutrons)
        isotopes2.append(diff_n)

    diff1 = abs(len(isotopes1) - len(isotopes2))
    diff2 = abs(sum(isotopes1) - sum(isotopes2))
    similarity_n = 1 / (1 + diff1 + diff2)
    
    # TODO: Charges of the molecules
    charge1 = sum(molecule1['protons']) - sum(molecule1['electrons'])
    charge2 = sum(molecule2['protons']) - sum(molecule2['electrons'])
    similarity_e = 1/ (1 + abs(charge1 - charge2)/ len(molecule1['elements']))

    return similarity_f, similarity_e, similarity_n

def final_similarity(similarity_s, similarity_r, similarity_f, similarity_e, similarity_n):
    """Compute the final similarity between two sets of points"""
    similarities = [similarity_s, similarity_r, similarity_f, similarity_e, similarity_n]
    similarity = similarity_s * similarity_r * similarity_f * similarity_e * similarity_n
    return similarities, similarity

def reorder_info(molecule, indices):

    reordered_molecule = {}
    for key, values in molecule.items():
        values_array = np.array(values)  
        reordered_molecule[key] = values_array[indices]

    return reordered_molecule

def compute_similarity_based_on_matching(query, target):
    # Align the molecules
    N1, N2 = len(query['elements']), len(target['elements'])
    if N1 <= N2:
        points1, points2 = query['coordinates'], target['coordinates']
        molecule1, molecule2 = query, target
    else:   
        points1, points2 = target['coordinates'], query['coordinates']
        molecule1, molecule2 = target, query
    points1, points2 = molecule1['coordinates'], molecule2['coordinates']
    tensor1, tensor2 = compute_inertia_tensor_no_masses(points1), compute_inertia_tensor(points2)
    principal_axes1, _ , principal_axes2, _ = compute_principal_axes(tensor1, points1), compute_principal_axes(tensor2, points2)
    points1, points2 = compute_new_coordinates(principal_axes1, points1), compute_new_coordinates(principal_axes2, points2)

    # Compute the matching
    distances, indices = compute_matching(points1, points2)
    molecule2 = reorder_info(molecule2, indices)
    
    # Compute the similarities
    similarity_s = size_similarity(N1, N2)
    similarity_r = positional_similarity(distances)
    if similarity_s > 0.9 and similarity_r > 0.8: #TODO: is there a more objective way of doing this? 
        similarity_f, similarity_n, similarity_e = formula_isotopic_charge_similarity(molecule1, molecule2)
    else:
        similarity_f, similarity_e, similarity_n = reduced_formula_isotopic_charge_similarity(molecule1, molecule2)
    
    # Compute the final similarity
    similarities, similarity = final_similarity(similarity_s, similarity_r, similarity_f, similarity_e, similarity_n)

    return similarities, similarity

################################################

##### Moments fingerprints #####################

##### 3-dimensional fingerprint ####################

def compute_distances(points, reference_points):
    """Compute the distance of each point to the 4 refernce points"""
    num_points = points.shape[0]
    num_ref_points = len(reference_points)
    distances = np.zeros((num_ref_points, num_points))
    
    for i, point in enumerate(points):
        for j, ref_point in enumerate(reference_points):
            distances[j, i] = np.linalg.norm(point - ref_point)
            
    return distances  

def compute_weighted_distances(points, masses, reference_points):
    """Compute the mass-weigthed distance of each point to the 4 refernce points"""
    num_points = points.shape[0]
    num_ref_points = len(reference_points)
    weighted_distances = np.zeros((num_ref_points, num_points))

    for i, (point, mass) in enumerate(zip(points, masses)):
        for j, ref_point in enumerate(reference_points):
            if mass == 0:
                mass = 1
            weighted_distances[j, i] = ((m.log(mass))) * np.linalg.norm(point - ref_point)

    return weighted_distances

def compute_statistics(distances):
    means = np.mean(distances, axis=1)
    std_devs = np.std(distances, axis=1)
    skewness = skew(distances, axis=1)
    # check if skewness is nan
    skewness[np.isnan(skewness)] = 0
    
    statistics_matrix = np.vstack((means, std_devs, skewness)).T 
    # add all rows to a list   
    statistics_list = [element for row in statistics_matrix for element in row]

    return statistics_list  

def compute_3d_fingerprint(points, n_prot, n_neut, n_elec):

    #particles = [n_prot, n_neut, n_elec]
    fingerprints = []

    #points, center_of_mass = translate_points_to_center_of_mass(points, masses), [0,0,0]
    points, geometrical_center = translate_points_to_geometrical_center(points), [0,0,0]

    #inertia_tensor = compute_inertia_tensor(points, masses, center_of_mass)
    weights = np.ones(len(points))
    inertia_tensor = compute_inertia_tensor(points, weights, geometrical_center)
    inertia_tensor = compute_inertia_tensor_no_masses(points, geometrical_center)

    principal_axes, eigenvalues = compute_principal_axes(inertia_tensor)

    #max_distance = max_distance_from_center_of_mass(points, center_of_mass)
    max_distance = max_distance_from_geometrical_center(points, geometrical_center)

    #reference_points = generate_reference_points(center_of_mass, principal_axes, max_distance)
    reference_points = generate_reference_points(geometrical_center, principal_axes, max_distance)

    # compute weighted distances
    proton_distances = compute_weighted_distances(points, n_prot, reference_points)
    neutron_distances = compute_weighted_distances(points, n_neut, reference_points)
    electron_distances = compute_weighted_distances(points, n_elec, reference_points)
    
    # compute statistics
    proton_fingerprint = compute_statistics(proton_distances)
    neutron_fingerprint = compute_statistics(neutron_distances)
    electron_fingerprint = compute_statistics(electron_distances)

    fingerprints = [proton_fingerprint, neutron_fingerprint, electron_fingerprint]

    return fingerprints

def compute_3d_similarity(query, target):
    """Compute the similarity between two 3d fingerprints"""
    similarities = []
    # compute the fingerprints
    query_fingerprints = compute_3d_fingerprint(query['coordinates', query['n_prot'], query['n_neut'], query['n_elec']])
    target_fingerprints = compute_3d_fingerprint(target['coordinates', target['n_prot'], target['n_neut'], target['n_elec']])

    # compute the similarities
    for i in range(3):
        similarities.append(1/(1 + calculate_partial_score(query_fingerprints[i], target_fingerprints[i])))

    # compute the final similarity
    similarity_mean = np.mean(similarities)

    return similarities, similarity_mean


##### n-Dimensionl fingerprints #####################

def principal_components(data):
    """
    Calculates the principal components (eigenvectors) of the covariance matrix of points with 
    additional info.
    """
    covariance_matrix = np.cov(data, ddof=0, rowvar=False)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance_matrix)
    sorted_indices = np.argsort(eigenvalues)[::-1]
    return eigenvectors[:, sorted_indices]

def compute_reference_points(data, eigenvectors):
    centroid = data.mean(axis = 0)
    reference_points = centroid + eigenvectors*(data.max(axis=0)-centroid)
    reference_points.insert(0, centroid)
    return reference_points

def compute_nD_fingerprint(data):
    pca_axis = principal_components(data)
    reference_points = compute_reference_points(data, pca_axis)
    distances = compute_distances(data, reference_points)
    fingerprint = compute_statistics(distances)
    return fingerprint

def compute_nD_similarity(query, target):
    """Compute the similarity between two nD fingerprints"""

    data = np.hstack((query['coordinates'], query['masses'].reshape(-1, 1)))
    data1 = np.hstack((target['coordinates'], target['masses'].reshape(-1, 1)))

    fingerprint_query = compute_nD_fingerprint(data)
    fingerprint_target = compute_nD_fingerprint(data1)

    similarity = 1/(1 + calculate_partial_score(fingerprint_query, fingerprint_target))
    return similarity
        





# def compute_fingerprint(points, masses, n_prot, n_neut, n_elec):

#     #particles = [n_prot, n_neut, n_elec]
#     fingerprints = []

#     #points, center_of_mass = translate_points_to_center_of_mass(points, masses), [0,0,0]
#     points, geometrical_center = translate_points_to_geometrical_center(points), [0,0,0]

#     #inertia_tensor = compute_inertia_tensor(points, masses, center_of_mass)
#     weights = np.ones(len(points))
#     inertia_tensor = compute_inertia_tensor(points, weights, geometrical_center)

#     principal_axes, eigenvalues = compute_principal_axes(inertia_tensor, points, masses)

#     #max_distance = max_distance_from_center_of_mass(points, center_of_mass)
#     max_distance = max_distance_from_geometrical_center(points, geometrical_center)

#     #reference_points = generate_reference_points(center_of_mass, principal_axes, max_distance)
#     reference_points = generate_reference_points(geometrical_center, principal_axes, max_distance)
#     # compute distances
#     #distances = compute_distances(points, reference_points)
#     # compute weighted distances
#     proton_distances = compute_weighted_distances(points, n_prot, reference_points)
#     neutron_distances = compute_weighted_distances(points, n_neut, reference_points)
#     electron_distances = compute_weighted_distances(points, n_elec, reference_points)
#     # compute statistics
#     # statistics_matrix, fingerprint_1 = compute_statistics(distances)
#     # statistics_matrix, fingerprint_2 = compute_statistics(weighted_distances)
#     proton_fingerprint = compute_statistics(proton_distances)
#     print(proton_fingerprint)
#     neutron_fingerprint = compute_statistics(neutron_distances)
#     electron_fingerprint = compute_statistics(electron_distances)
    
#     # print("Center of mass:", center_of_mass)
#     # # print("Inertia tensor:", inertia_tensor)
#     # print("Principal axes:", principal_axes)
#     # print("Eigenvalues:", eigenvalues)
#     # # print("Distances:", distances)
#     # # print("Fingerprint of regular distances:", fingerprint_1)
#     # # print("Fingerprint of weighted distances:", fingerprint_2)
#     # print(f'Handedness: {compute_handedness(principal_axes, eigenvalues)}')

#     # If the third eigenvalue less than 0.001, we still need to visulaize the third axis
#     if np.abs(eigenvalues[2]) < 0.001:
#         eigenvalues[2] = 0.5 * eigenvalues[1]

#     #visualize(points, n_prot, center_of_mass, principal_axes, eigenvalues, max_distance, reference_points)
#     visualize(points, n_prot, geometrical_center, principal_axes, eigenvalues, max_distance, reference_points)

#     fingerprints = [proton_fingerprint, neutron_fingerprint, electron_fingerprint]

#     return fingerprints