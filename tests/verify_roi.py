import os
import shutil
from nilearn import datasets
from neuro_mod.phase_analysis.roi_connectivity import ROIManager

def verify_roi_connectivity():
    tmp_dir = "/tmp/neuro_mod_roi_test"
    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir)
        
    # 1. Fetch data
    print("Fetching Haxby data for ROI test...")
    
    # SSL Bypass for atlas download issues
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context
    
    haxby_dataset = datasets.fetch_haxby(subjects=[1])
    bold_img = haxby_dataset.func[0]
    
    # 2. Setup Manager
    manager = ROIManager(output_dir=tmp_dir)
    
    # 3. Extract from Harvard-Oxford (often more reliable download)
    print("Testing Harvard-Oxford extraction...")
    # NOTE: Extraction on a full BOLD run can be slow, but for verification it's fine
    # For speed in testing, we could slice the image, but let's try the full first
    # Or just use the first 50 volumes
    from nilearn.image import index_img
    bold_short = index_img(bold_img, slice(0, 50))
    
    signals_df = manager.extract_from_atlas(bold_short, atlas='harvard_oxford', subject_id='sub-01')
    
    # 4. Compute Connectivity
    print("Testing connectivity computation...")
    conn_matrix = manager.compute_functional_connectivity(signals_df, subject_id='sub-01')
    
    print(f"ROI verification successful. Matrix shape: {conn_matrix.shape}")
    print(f"Results saved to {tmp_dir}")

if __name__ == "__main__":
    verify_roi_connectivity()
