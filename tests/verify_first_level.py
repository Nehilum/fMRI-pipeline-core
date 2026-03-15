import os
import shutil
from nilearn import datasets
from neuro_mod.phase_analysis.first_level import FirstLevelManager
import pandas as pd

def verify_first_level():
    # 1. Fetch small part of Haxby dataset
    print("Fetching Haxby dataset...")
    haxby_dataset = datasets.fetch_haxby(subjects=[1])
    
    # 2. Extract necessary paths
    func_file = haxby_dataset.func[0]
    session_target = pd.read_csv(haxby_dataset.session_target[0], sep=' ')
    
    # Convert Haxby style labels to BIDS-like events.tsv
    # Haxby labels are rows in a text file. We need onset, duration, trial_type
    # TR for Haxby is 2.5s
    tr = 2.5
    onsets = [i * tr for i in range(len(session_target))]
    durations = [tr] * len(session_target)
    trial_types = session_target['labels'].tolist()
    
    events_df = pd.DataFrame({
        'onset': onsets,
        'duration': durations,
        'trial_type': trial_types
    })
    
    # Save a temporary events file
    tmp_dir = "/tmp/neuro_mod_test"
    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir)
        
    events_path = os.path.join(tmp_dir, "sub-01_events.tsv")
    events_df.to_csv(events_path, sep='\t', index=False)
    
    # Haxby dataset doesn't come with fMRIPrep-style confounds in a simple way
    # We'll create a dummy confounds file with zeros for testing logic
    confounds_path = os.path.join(tmp_dir, "sub-01_confounds.tsv")
    dummy_confounds = pd.DataFrame({
        'trans_x': [0] * len(session_target),
        'trans_y': [0] * len(session_target),
        'trans_z': [0] * len(session_target),
        'rot_x': [0] * len(session_target),
        'rot_y': [0] * len(session_target),
        'rot_z': [0] * len(session_target),
        'framewise_displacement': [0] * len(session_target)
    })
    dummy_confounds.to_csv(confounds_path, sep='\t', index=False)
    
    # 3. Setup FirstLevelManager
    output_dir = os.path.join(tmp_dir, "outputs")
    manager = FirstLevelManager(bids_dir=tmp_dir, output_dir=output_dir, t_r=tr, smoothing_fwhm=4)
    
    # 4. Define contrast
    # Use 'face' vs everything else as a test
    # Note: Nilearn GLM handles trial_type names directly
    contrast_spec = {
        'face_vs_others': 'face - (house + scissors + scrambledpix + shoe + bottle + chair + cat)'
    }
    
    # 5. Run GLM
    print("Running Subject GLM...")
    manager.run_subject_glm(
        subject_id='sub-01',
        runs=[func_file],
        events_files=[events_path],
        confounds_files=[confounds_path],
        contrast_spec=contrast_spec
    )
    
    print(f"Verification successful. Results are in {output_dir}")

if __name__ == "__main__":
    verify_first_level()
