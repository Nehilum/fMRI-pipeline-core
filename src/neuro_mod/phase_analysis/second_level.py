import os
import glob
import pandas as pd
from nilearn.glm.second_level import SecondLevelModel
from nilearn.glm import threshold_stats_img
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SecondLevelManager:
    """
    Manages Group-Level (Second-Level) analysis using Nilearn.
    """
    def __init__(self, output_dir):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def run_one_sample_t_test(self, maps, contrast_id, threshold=3.1, cluster_threshold=10):
        """
        Runs a one-sample t-test on a collection of subject contrast maps.
        
        Parameters:
        -----------
        maps : list of str (or Niimg-like)
            List of contrast maps from multiple subjects.
        contrast_id : str
            Identifier for the contrast being analyzed.
        threshold : float
            Voxel-level threshold (e.g., z=3.1 corresponds to p<0.001).
        cluster_threshold : int
            Cluster size threshold in voxels.
        """
        logger.info(f"Starting Second-Level Analysis for {contrast_id}")
        
        # For one-sample t-test without explicit design, create a column of ones
        design_matrix = pd.DataFrame([1] * len(maps), columns=['intercept'])
        
        # Initialize and fit model
        model = SecondLevelModel(smoothing_fwhm=None) # Assume input maps already smoothed if needed
        model.fit(maps, design_matrix=design_matrix)
        
        # Compute group contrast
        z_map = model.compute_contrast(output_type='z_score')
        t_map = model.compute_contrast(output_type='stat')
        
        # Save raw results
        group_out_dir = os.path.join(self.output_dir, contrast_id)
        if not os.path.exists(group_out_dir):
            os.makedirs(group_out_dir)
            
        z_map_path = os.path.join(group_out_dir, f"group_{contrast_id}_z_map.nii.gz")
        t_map_path = os.path.join(group_out_dir, f"group_{contrast_id}_t_map.nii.gz")
        z_map.to_filename(z_map_path)
        t_map.to_filename(t_map_path)
        
        # Thresholded map (Cluster-wise correction)
        thresholded_map, threshold = threshold_stats_img(
            z_map, 
            alpha=0.05, 
            height_control='fdr', # or 'bonferroni', or a fixed float for voxel-level
            cluster_threshold=cluster_threshold
        )
        
        thresh_path = os.path.join(group_out_dir, f"group_{contrast_id}_thresholded_fdr_z.nii.gz")
        thresholded_map.to_filename(thresh_path)
        
        logger.info(f"Finished Group Analysis. Results saved to {group_out_dir}")
        return z_map, thresholded_map

if __name__ == "__main__":
    print("SecondLevelManager module ready.")
