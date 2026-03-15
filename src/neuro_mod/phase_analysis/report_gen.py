import os
from nilearn.reporting import make_glm_report
from nilearn import plotting
import matplotlib.pyplot as plt
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ReportManager:
    """
    Manages automated generation of HTML reports and statistical plots.
    """
    def __init__(self, output_dir):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def generate_first_level_report(self, model, contrast_id, subject_id='sub-01'):
        """
        Generates an HTML report for a subject-level GLM.
        """
        logger.info(f"Generating First-Level report for {subject_id} - {contrast_id}")
        
        report = make_glm_report(
            model=model,
            contrasts=contrast_id,
            title=f"First Level GLM: {subject_id} - {contrast_id}",
            height_control='fdr',
            alpha=0.05
        )
        
        out_path = os.path.join(self.output_dir, f"{subject_id}_{contrast_id}_report.html")
        report.save_as_html(out_path)
        logger.info(f"Report saved to {out_path}")
        return out_path

    def plot_connectivity_matrix(self, correlation_matrix, labels=None, subject_id='sub-01'):
        """
        Plots a connectivity matrix and saves it as an image.
        """
        logger.info(f"Plotting connectivity matrix for {subject_id}")
        
        plt.figure(figsize=(10, 8))
        plotting.plot_matrix(correlation_matrix, labels=labels, colorbar=True, figure=plt.gcf())
        
        out_path = os.path.join(self.output_dir, f"{subject_id}_connectivity_plot.png")
        plt.savefig(out_path)
        plt.close()
        
        logger.info(f"Connectivity plot saved to {out_path}")
        return out_path

if __name__ == "__main__":
    print("ReportManager module ready.")
