import os
import pandas as pd
from nilearn.glm.first_level import FirstLevelModel
from nilearn.reporting import make_glm_report
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FirstLevelManager:
    """
    Manages Subject-Level GLM analysis using Nilearn.
    Expects BIDS-compliant derivatives as input.
    """
    def __init__(self, bids_dir, output_dir, t_r=None, smoothing_fwhm=None):
        self.bids_dir = bids_dir
        self.output_dir = output_dir
        self.t_r = t_r
        self.smoothing_fwhm = smoothing_fwhm
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def run_subject_glm(self, subject_id, runs, events_files, confounds_files, contrast_spec):
        """
        Runs First-Level GLM for a single subject across multiple runs.
        
        Parameters:
        -----------
        subject_id : str
            e.g., 'sub-01'
        runs : list of str
            List of paths to preprocessed BOLD files.
        events_files : list of str
            List of paths to corresponding events.tsv files.
        confounds_files : list of str
            List of paths to corresponding confounds.tsv files.
        contrast_spec : dict
            Dictionary defining contrasts, e.g., {'task_vs_rest': 'task - rest'}
        """
        logger.info(f"Starting First-Level GLM for {subject_id}")
        
        # Initialize model
        # Note: t_r is often extracted from metadata, but can be passed explicitly
        model = FirstLevelModel(
            t_r=self.t_r,
            slice_time_ref=0.5,
            smoothing_fwhm=self.smoothing_fwhm,
            hrf_model='glover',
            drift_model='cosine',
            high_pass=0.01,
            standardize=False, # Usually pre-standardized in fMRIPrep, but depends on workflow
            minimize_memory=True
        )
        
        # Prepare confounds (select relevant ones)
        # In a real scenario, we'd filter common motion params here
        selected_confounds = []
        for cf in confounds_files:
            df = pd.read_csv(cf, sep='\t')
            # Default selection: 6 motion params + FD
            cols = [col for col in df.columns if 'trans_' in col or 'rot_' in col or 'framewise_displacement' in col]
            selected_confounds.append(df[cols].fillna(0))
            
        # Fit model
        model.fit(runs, events_files, confounds=selected_confounds)
        
        # Compute contrasts
        sub_out_dir = os.path.join(self.output_dir, subject_id)
        if not os.path.exists(sub_out_dir):
            os.makedirs(sub_out_dir)
            
        for contrast_id, contrast_val in contrast_spec.items():
            logger.info(f"Computing contrast: {contrast_id}")
            z_map = model.compute_contrast(contrast_val, output_type='z_score')
            stat_map = model.compute_contrast(contrast_val, output_type='stat')
            
            z_map.to_filename(os.path.join(sub_out_dir, f"{subject_id}_{contrast_id}_z_map.nii.gz"))
            stat_map.to_filename(os.path.join(sub_out_dir, f"{subject_id}_{contrast_id}_t_map.nii.gz"))
            
        logger.info(f"Finished First-Level GLM for {subject_id}. Results saved to {sub_out_dir}")
        return model

if __name__ == "__main__":
    # Example usage / placeholder
    print("FirstLevelManager module ready.")
