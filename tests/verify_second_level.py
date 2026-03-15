import os
import shutil
import pandas as pd
from nilearn import datasets
from neuro_mod.phase_analysis.first_level import FirstLevelManager
from neuro_mod.phase_analysis.second_level import SecondLevelManager

def verify_second_level():
    tmp_dir = "/tmp/neuro_mod_group_test"
    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir)
    
    # 1. Fetch 2 subjects
    print("Fetching 2 subjects from Haxby dataset...")
    haxby_dataset = datasets.fetch_haxby(subjects=[1, 2])
    
    contrast_maps = []
    tr = 2.5
    
    for i in range(2):
        sub_id = f'sub-0{i+1}'
        print(f"Preparing Phase 7 for {sub_id}...")
        
        func_file = haxby_dataset.func[i]
        session_target = pd.read_csv(haxby_dataset.session_target[i], sep=' ')
        
        # Prepare events
        onsets = [j * tr for j in range(len(session_target))]
        durations = [tr] * len(session_target)
        trial_types = session_target['labels'].tolist()
        
        events_df = pd.DataFrame({
            'onset': onsets,
            'duration': durations,
            'trial_type': trial_types
        })
        
        events_path = os.path.join(tmp_dir, f"{sub_id}_events.tsv")
        events_df.to_csv(events_path, sep='\t', index=False)
        
        # Prepare dummy confounds
        confounds_path = os.path.join(tmp_dir, f"{sub_id}_confounds.tsv")
        dummy_confounds = pd.DataFrame({
            'trans_x': [0] * len(session_target),
            'trans_y': [0] * len(session_target),
            'trans_z': [0] * len(session_target)
        })
        dummy_confounds.to_csv(confounds_path, sep='\t', index=False)
        
        # Run First-Level
        sub_out_dir = os.path.join(tmp_dir, "first_level")
        fl_manager = FirstLevelManager(bids_dir=tmp_dir, output_dir=sub_out_dir, t_r=tr, smoothing_fwhm=4)
        
        # Only face vs rest to be quick
        contrast_spec = {'face': 'face'}
        fl_manager.run_subject_glm(
            subject_id=sub_id,
            runs=[func_file],
            events_files=[events_path],
            confounds_files=[confounds_path],
            contrast_spec=contrast_spec
        )
        
        contrast_maps.append(os.path.join(sub_out_dir, sub_id, f"{sub_id}_face_z_map.nii.gz"))
    
    # 2. Run Second-Level
    print("Running Second-Level Group Analysis...")
    group_out_dir = os.path.join(tmp_dir, "second_level")
    sl_manager = SecondLevelManager(output_dir=group_out_dir)
    sl_manager.run_one_sample_t_test(maps=contrast_maps, contrast_id='face')
    
    print(f"Group verification successful. Results in {group_out_dir}")

if __name__ == "__main__":
    verify_second_level()
