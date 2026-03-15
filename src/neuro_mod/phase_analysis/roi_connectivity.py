import os
import pandas as pd
import numpy as np
from nilearn.maskers import NiftiLabelsMasker, NiftiSpheresMasker
from nilearn.connectome import ConnectivityMeasure
from nilearn import datasets
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ROIManager:
    """
    Manages ROI extraction and Connectivity analysis.
    """
    def __init__(self, output_dir):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def extract_from_atlas(self, img, atlas='aal', subject_id='sub-01'):
        """
        Extract signals (beta weights or time-series) from an atlas.
        """
        logger.info(f"Extracting signals from {atlas} atlas for {subject_id}")
        
        if atlas == 'aal':
            dataset = datasets.fetch_atlas_aal()
            atlas_filename = dataset.maps
            labels = dataset.labels
        elif atlas == 'harvard_oxford':
            dataset = datasets.fetch_atlas_harvard_oxford('cort-maxprob-thr25-2mm')
            atlas_filename = dataset.maps
            labels = dataset.labels
        else:
            raise ValueError(f"Atlas {atlas} not supported yet.")
            
        masker = NiftiLabelsMasker(labels_img=atlas_filename, standardize=True)
        signals = masker.fit_transform(img)
        
        # Convert to Pandas for easy handling
        # Note: labels[0] is often 'Background'
        # Check lengths to be safe
        n_labels = signals.shape[1]
        df_labels = labels[1:n_labels+1] if len(labels) > n_labels else labels
        
        df = pd.DataFrame(signals, columns=df_labels)
        
        out_path = os.path.join(self.output_dir, f"{subject_id}_{atlas}_extracted.csv")
        df.to_csv(out_path, index=False)
        logger.info(f"Extracted signals saved to {out_path}")
        return df

    def compute_functional_connectivity(self, time_series_df, subject_id='sub-01'):
        """
        Compute functional connectivity (correlation matrix) from time-series.
        """
        logger.info(f"Computing functional connectivity for {subject_id}")
        
        correlation_measure = ConnectivityMeasure(kind='correlation')
        correlation_matrix = correlation_measure.fit_transform([time_series_df.values])[0]
        
        # Save matrix
        out_path = os.path.join(self.output_dir, f"{subject_id}_connectivity_matrix.npy")
        np.save(out_path, correlation_matrix)
        
        logger.info(f"Connectivity matrix saved to {out_path}")
        return correlation_matrix

if __name__ == "__main__":
    print("ROIManager module ready.")
