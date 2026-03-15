import os
import shutil
import pandas as pd
from nilearn import datasets
from nilearn.image import index_img
from neuro_mod.phase_analysis.first_level import FirstLevelManager
from neuro_mod.phase_analysis.roi_connectivity import ROIManager
from neuro_mod.phase_analysis.report_gen import ReportManager

def verify_end_to_end():
    tmp_dir = "/tmp/neuro_mod_final_test"
    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir)
    
    # SSL Bypass for atlas download issues
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context
        
    # 1. Fetch data
    print("Fetching data...")
    haxby_dataset = datasets.fetch_haxby(subjects=[1])
    bold_img = haxby_dataset.func[0]
    session_target = pd.read_csv(haxby_dataset.session_target[0], sep=' ')
    tr = 2.5
    
    # 2. Phase 7: First-Level GLM
    print("Running Phase 7: GLM...")
    # Use first 100 volumes for speed
    n_scans = 100
    bold_short = index_img(bold_img, slice(0, n_scans))
    
    session_target_short = session_target.iloc[0:n_scans]
    onsets = [i * tr for i in range(len(session_target_short))]
    events_df = pd.DataFrame({'onset': onsets, 'duration': [tr]*len(session_target_short), 'trial_type': session_target_short['labels'].tolist()})
    events_path = os.path.join(tmp_dir, "events.tsv")
    events_df.to_csv(events_path, sep='\t', index=False)
    
    confounds_path = os.path.join(tmp_dir, "confounds.tsv")
    pd.DataFrame({'trans_x': [0]*n_scans}).to_csv(confounds_path, sep='\t', index=False)
    
    fl_manager = FirstLevelManager(bids_dir=tmp_dir, output_dir=os.path.join(tmp_dir, "glm"), t_r=tr, smoothing_fwhm=4)
    model = fl_manager.run_subject_glm(subject_id='sub-01', runs=[bold_short], events_files=[events_path], confounds_files=[confounds_path], contrast_spec={'face': 'face'})
    
    # 3. Phase 9: ROI & Connectivity
    print("Running Phase 9: ROI...")
    roi_manager = ROIManager(output_dir=os.path.join(tmp_dir, "roi"))
    signals_df = roi_manager.extract_from_atlas(bold_short, atlas='harvard_oxford')
    conn_matrix = roi_manager.compute_functional_connectivity(signals_df)
    
    # 4. Phase 10: Reporting
    print("Running Phase 10: Reporting...")
    report_manager = ReportManager(output_dir=os.path.join(tmp_dir, "reports"))
    report_manager.generate_first_level_report(model, contrast_id='face')
    report_manager.plot_connectivity_matrix(conn_matrix, labels=signals_df.columns.tolist())
    
    print(f"End-to-End verification successful. Results are in {tmp_dir}")

if __name__ == "__main__":
    verify_end_to_end()
